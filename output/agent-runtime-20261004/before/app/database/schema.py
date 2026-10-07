"""SQLAlchemy Core schema for the application's durable audit records."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

metadata = MetaData()

telegram_updates = Table(
    "telegram_updates",
    metadata,
    Column("update_id", Integer, primary_key=True),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("processed_at", DateTime(timezone=True)),
    Column("status", String(32), nullable=False),
)

agent_threads = Table(
    "agent_threads",
    metadata,
    Column("thread_id", String(36), primary_key=True),
    Column("telegram_user_id", Integer, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# The audit records below answer what happened during a run.  These messages
# answer a different question: what may the next turn need to know?  Keeping
# the two models separate prevents a tool trace from becoming model context.
agent_thread_messages = Table(
    "agent_thread_messages",
    metadata,
    Column("message_id", Integer, primary_key=True, autoincrement=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# A pending selection is intentionally separate from the message history. It
# contains only candidates returned by a successful Notion search and can be
# consumed as trusted provenance on the following turn.
pending_task_selections = Table(
    "pending_task_selections",
    metadata,
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), primary_key=True),
    Column("candidates", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# RADAR selections are separate from Notion task provenance.  The candidates
# are a server-owned snapshot of one authorized search, and ``request_text``
# lets a bare “2” resume the business request rather than becoming a new model
# instruction.  Titles exist only so the same numbered question can be shown
# again; ids/revisions remain the machine identity.
pending_radar_selections = Table(
    "pending_radar_selections",
    metadata,
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), primary_key=True),
    Column("purpose", String(24), nullable=False),
    Column("request_text", Text, nullable=False),
    Column("source_context", JSON, nullable=False, server_default=text("'{}'")),
    Column("candidates", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

# Once ids stop appearing in assistant prose, the model needs a bounded and
# trusted bridge for “essa ação” on the next turn.  This row contains only
# entity summaries observed in successful RADAR tool results.  It helps resolve
# conversation, but is deliberately not accepted as mutation provenance.
radar_thread_referents = Table(
    "radar_thread_referents",
    metadata,
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), primary_key=True),
    Column("focused", JSON),
    Column("listed", JSON, nullable=False),
    Column("source_run_id", String(36), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# A pending write approval is the filesystem counterpart of the selection
# above: the request the agent refused, plus the message that produced it, so
# an answered "sim" can replay the original ask with the grant attached. Only
# the application writes here, which is what makes the row trustworthy as
# provenance on the following turn.
pending_write_approvals = Table(
    "pending_write_approvals",
    metadata,
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), primary_key=True),
    Column("requests", JSON, nullable=False),
    Column("request_text", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# A RADAR proposal is a durable command, not conversational history or a
# generic agent approval.  Its saved payload is the *only* object execution may
# consume after a user says yes; the partial unique index leaves an immutable
# terminal record while still allowing just one active proposal per thread.
pending_radar_operations = Table(
    "pending_radar_operations",
    metadata,
    Column("proposal_id", String(36), primary_key=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), nullable=False),
    Column("telegram_user_id", Integer, nullable=False),
    Column("operation", String(48), nullable=False),
    Column("context", String(160)),
    Column("target_id", String(32)),
    Column("expected_revision", Integer, nullable=False),
    Column("parameters", JSON, nullable=False),
    Column("idempotency_key", String(96), nullable=False, unique=True),
    Column("execution_context", JSON),
    Column("summary", JSON, nullable=False),
    Column("source_context", JSON, nullable=False, server_default=text("'{}'")),
    Column("intent_version", String(16)),
    Column("intent_fingerprint", String(80)),
    Column("override_of", String(36)),
    Column("status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("executed_at", DateTime(timezone=True)),
    Column("result", JSON),
)
Index(
    "uq_pending_radar_operations_active_thread",
    pending_radar_operations.c.thread_id,
    unique=True,
    sqlite_where=text("status IN ('pending', 'executing', 'uncertain')"),
    postgresql_where=text("status IN ('pending', 'executing', 'uncertain')"),
)
Index(
    "ix_pending_radar_operations_intent",
    pending_radar_operations.c.telegram_user_id,
    pending_radar_operations.c.intent_fingerprint,
    pending_radar_operations.c.created_at,
)

# A semantic duplicate never becomes an executable proposal.  Instead, the
# application records a bounded, single-use option that only the exact phrase
# "registrar como novo fato" may consume on the following turn.
pending_radar_intent_overrides = Table(
    "pending_radar_intent_overrides",
    metadata,
    Column("override_id", String(36), primary_key=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), nullable=False),
    Column("telegram_user_id", Integer, nullable=False),
    Column("matched_proposal_id", String(36), nullable=False),
    Column("matched_status", String(24), nullable=False),
    Column("intent_fingerprint", String(80), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("summary", JSON, nullable=False),
    Column("status", String(24), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
    Column("proposal_id", String(36)),
)
Index(
    "uq_pending_radar_intent_override_thread",
    pending_radar_intent_overrides.c.thread_id,
    unique=True,
    sqlite_where=text("status = 'pending'"),
    postgresql_where=text("status = 'pending'"),
)

# The agent's virtual filesystem, carried from one turn to the next. It is a
# table of its own rather than a column on `agent_threads` because it is the
# only part of a thread that is read and rewritten wholesale on every turn,
# and it is the only one that grows with what the model writes. Bounds live in
# `app.agent.builtins`; this row is never appended to, always replaced.
agent_thread_files = Table(
    "agent_thread_files",
    metadata,
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), primary_key=True),
    Column("files", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# What the assistant knows about the user between conversations. Deliberately
# not a second copy of the workspace above: the workspace is scratch space the
# model rewrites at will, while a memory is durable, bounded and shown to the
# user in the reply that recorded it.
#
# `normalized_content` exists only for the unique constraint. Deduplication in
# the database rather than in a "if content in entries" check is what makes
# repeating a preference idempotent instead of racy — and repeating himself is
# exactly what the user does when the assistant forgot.
agent_memories = Table(
    "agent_memories",
    metadata,
    Column("memory_id", String(36), primary_key=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("normalized_content", Text, nullable=False),
    # Which run recorded it. A memory entry is the only model-authored text that
    # survives its own run, so it has to stay traceable to the trace that made it.
    Column("source_run_id", String(36)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("thread_id", "normalized_content", name="uq_agent_memory_content"),
)

# Synthetic RADAR sessions are isolated from Telegram users. The public
# simulator identifier maps to an application thread, while the stored
# metadata is limited to the agreed integration contract.
radar_api_sessions = Table(
    "radar_api_sessions",
    metadata,
    Column(
        "thread_id",
        String(36),
        ForeignKey("agent_threads.thread_id"),
        primary_key=True,
    ),
    Column("external_user_id", String(120), nullable=False),
    Column("metadata", JSON, nullable=False),
    Column("idempotency_key", String(128), nullable=False, unique=True),
    Column("request_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# One durable result per logical synthetic message. A lease makes a process
# crash visible as unknown after five minutes instead of silently re-running
# the agent and possibly returning a different answer.
radar_api_messages = Table(
    "radar_api_messages",
    metadata,
    Column("thread_id", String(36), ForeignKey("radar_api_sessions.thread_id"), nullable=False),
    Column("message_id", String(36), nullable=False),
    Column("idempotency_key", String(128), nullable=False, unique=True),
    Column("request_hash", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("run_id", String(36)),
    Column("response_content", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("thread_id", "message_id", name="uq_radar_api_message"),
)

# A scheduled job is a rule, not an instant. `schedule` keeps the parsed rule
# and `timezone` the zone its wall-clock intent belongs to; `next_run_at` is the
# derived UTC instant and is always recomputed from those two, never the other
# way around. Storing a fixed offset instead of the zone name would silently
# shift every future run the first time the zone's offset changes.
scheduled_jobs = Table(
    "scheduled_jobs",
    metadata,
    Column("job_id", String(36), primary_key=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id"), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("title", String(200), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("schedule", JSON, nullable=False),
    Column("timezone", String(64), nullable=False),
    # Null means the job has no future run: a one-shot that already fired, or a
    # rule that was disabled. The dispatcher only ever looks at enabled jobs
    # whose `next_run_at` has arrived, so null is simply never due.
    Column("next_run_at", DateTime(timezone=True)),
    Column("enabled", Boolean, nullable=False),
    # Digest of the last payload delivered, for jobs that only notify on change.
    # Written before the delivery it describes, so a failure cannot make the
    # same content alert forever.
    Column("last_digest", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# The execution ledger. One row per slot a job actually fired for, claimed
# before the work starts, so a crash leaves evidence instead of silence. A
# cancellation disables the rule but keeps these rows; ``claimed`` moves to
# either ``cancelled`` or ``delivering`` atomically before the Telegram request.
#
# The unique constraint on (job_id, scheduled_for) is the idempotency key: it
# is what makes a slot impossible to fire twice, even if two dispatchers were
# ever to run at once. `status` carries `unknown` for the same reason
# `_derive_run_status` does — an execution whose lease expired may have written
# to Notion, and a retry could apply it a second time.
scheduled_job_occurrences = Table(
    "scheduled_job_occurrences",
    metadata,
    Column("occurrence_id", String(36), primary_key=True),
    Column("job_id", String(36), ForeignKey("scheduled_jobs.job_id"), nullable=False),
    Column("scheduled_for", DateTime(timezone=True), nullable=False),
    Column("status", String(32), nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("run_id", String(36)),
    Column("detail", String(200)),
    UniqueConstraint("job_id", "scheduled_for", name="uq_scheduled_occurrence_slot"),
)

agent_runs = Table(
    "agent_runs",
    metadata,
    Column("run_id", String(36), primary_key=True),
    Column("thread_id", String(36), ForeignKey("agent_threads.thread_id")),
    Column("telegram_update_id", Integer, ForeignKey("telegram_updates.update_id")),
    # Who triggered the run. A null `telegram_update_id` used to be the only
    # hint, and it cannot distinguish a scheduled run from a direct call.
    Column("origin", String(16), nullable=False, server_default="telegram"),
    Column("status", String(32), nullable=False),
    Column("reply", Text, nullable=False),
    Column("execution_error", String(128)),
    # Count-only/fingerprinted run telemetry.  It deliberately excludes tool
    # arguments, ABox text and model prose, which remain governed by the more
    # specific tool-call audit projections below.
    Column("metrics", JSON, nullable=False, server_default=text("'{}'")),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
)

tool_calls = Table(
    "tool_calls",
    metadata,
    Column("tool_call_id", String(128), primary_key=True),
    Column("run_id", String(36), ForeignKey("agent_runs.run_id"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("name", String(128), nullable=False),
    Column("requested_arguments", JSON, nullable=False),
    Column("normalized_arguments", JSON),
    Column("result", JSON),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

errors = Table(
    "errors",
    metadata,
    Column("error_id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("agent_runs.run_id"), nullable=False),
    Column("phase", String(64), nullable=False),
    Column("error_type", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

__all__ = [
    "agent_memories",
    "agent_runs",
    "agent_thread_files",
    "agent_thread_messages",
    "agent_threads",
    "errors",
    "metadata",
    "pending_radar_intent_overrides",
    "pending_radar_operations",
    "pending_radar_selections",
    "pending_task_selections",
    "pending_write_approvals",
    "radar_thread_referents",
    "scheduled_job_occurrences",
    "scheduled_jobs",
    "telegram_updates",
    "tool_calls",
]
