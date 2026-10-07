"""Application use case for a Telegram text or voice update."""

from __future__ import annotations

import inspect
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from app.agent.agent import AgentRun, run_agent
from app.agent.builtins import user_supplied_origins
from app.agent.progress import ProgressReporter
from app.application.attachments import (
    TelegramAttachment,
    build_attachment_message,
    receive_attachment,
)
from app.application.progress import (
    RECEIVING_FILE_DRAFT_TEXT,
    THINKING_DRAFT_TEXT,
    TRANSCRIBING_DRAFT_TEXT,
    DraftProgress,
)
from app.application.radar_conversation import (
    asks_for_technical_identifiers,
    focused_reference,
    normalize_human_reference,
    references_from_tool_calls,
    scrub_internal_radar_names,
    selection_is_resolvable,
)
from app.application.radar_conversation import (
    duplicate_intent_reply as radar_duplicate_intent_reply,
)
from app.application.radar_conversation import (
    execution_reply as radar_execution_reply,
)
from app.application.radar_conversation import (
    humanize_reply as humanize_radar_reply,
)
from app.application.radar_conversation import (
    proposal_question as radar_approval_question,
)
from app.application.radar_conversation import (
    selection_reply as radar_selection_reply,
)
from app.application.voice import TelegramAudio, transcribe_voice_message
from app.config import settings
from app.database.radar_operations import RadarOperationRepository
from app.database.repository import AgentRunRepository
from app.database.telegram_updates import TelegramUpdateRepository
from app.database.threads import (
    AgentThreadRepository,
    ConversationMessage,
    PendingRadarSelection,
    PendingTaskSelection,
    RadarConversationReferents,
)
from app.errors import ConfigurationError, TelegramAPIError, UnauthorizedUserError
from app.integrations.telegram_client import TelegramClient
from app.integrations.telegram_format import render_html, split_message
from app.integrations.telegram_rich import render_rich_html, split_rich_message
from app.integrations.transcription import TranscriptionService
from app.observability import bind_correlation_context
from app.schemas.memory import MemoryEntry
from app.security.radar_provenance import RadarMessageSource, bind_radar_source_context
from app.tools.dependencies import memory_service, radar_operation_repository, radar_service

logger = logging.getLogger(__name__)

_TASK_MUTATION_PATTERN = re.compile(
    r"\b(conclu[ai]|complete|finaliz[ae]|marque|adicione como conclu|"
    r"atualiz[ae]|alter[ae]|mude|adi[ae]|renomeie)\b",
    flags=re.IGNORECASE,
)
_SELECTION_PATTERN = re.compile(
    r"^\s*(?:(?:opção|opcao|item)\s*)?(\d{1,2})\s*$",
    flags=re.IGNORECASE,
)
_RADAR_MUTATION_PATTERN = re.compile(
    r"\b(deleg(?:ue|ar|a)|atrib(?:ua|uir|ui)|revis(?:e|ar)|"
    r"registr(?:e|ar|a)\s+(?:uma\s+)?revis|captur(?:e|ar)|"
    r"registr(?:e|ar|a)\s+(?:uma\s+)?(?:ocorr[eê]ncia|issue|medi[cç][aã]o)|"
    r"(?:atualiz(?:e|ar)|medir|me[cç]a)\s+(?:o\s+)?indicador)\b",
    flags=re.IGNORECASE,
)
_RADAR_ORDINALS = {
    "a primeira": 0,
    "o primeiro": 0,
    "primeira": 0,
    "primeiro": 0,
    "a segunda": 1,
    "o segundo": 1,
    "segunda": 1,
    "segundo": 1,
    "a terceira": 2,
    "o terceiro": 2,
    "terceira": 2,
    "terceiro": 2,
    "a quarta": 3,
    "o quarto": 3,
    "quarta": 3,
    "quarto": 3,
    "a quinta": 4,
    "o quinto": 4,
    "quinta": 4,
    "quinto": 4,
}

# A write approval is granted or refused only by an unambiguous whole answer.
# Anything else — including a "sim" buried in a longer sentence — is treated as
# a new request that supersedes the question, never as consent.
_APPROVAL_GRANTED_PATTERN = re.compile(
    r"^\s*(sim|pode|autorizo|autorizado|confirmo|confirmado|ok)\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)
_APPROVAL_REFUSED_PATTERN = re.compile(
    r"^\s*(não|nao|cancela|cancelar|descarta|descartar)\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

# The one instruction that is answered by the application instead of by the
# agent. It has to keep working when the model provider is refusing every call
# — that is precisely when a poisoned or oversized context needs discarding —
# so it is matched here, before any run is started, and never sent to a model.
_CLEAR_COMMAND_PATTERN = re.compile(r"^\s*/(?:clear|limpar)(?:@\w+)?\s*$", flags=re.IGNORECASE)

APPROVAL_REFUSED_REPLY = "Certo, não vou alterar nenhum arquivo."

CLEARED_REPLY = (
    "Contexto limpo: descartei o histórico desta conversa, os arquivos do "
    "workspace (inclusive os que você me mandou) e qualquer pergunta minha em "
    "aberto. O que eu aprendi sobre você continua salvo."
)

# Answering Telegram before the run means a failed run no longer becomes a
# redelivery: the update is spent either way, so the chat has to be told, or
# silence would be the only symptom of a crash.
PROCESSING_FAILED_REPLY = (
    "Não consegui concluir seu pedido — algo falhou aqui do meu lado. Pode mandar de novo?"
)

RADAR_SELECTION_EXPIRED_REPLY = (
    "Essa lista venceu e não vou usar uma referência antiga para agir. "
    "Peça novamente pelo nome do item para eu conferir o estado atual."
)


@dataclass(frozen=True)
class TelegramProcessResult:
    """Safe HTTP-facing outcome of processing one update."""

    status: str
    run_id: str | None = None


@dataclass(frozen=True)
class TelegramAdmission:
    """Whether one update earns a run, decided before any network call.

    ``incoming`` is the admission itself: present means the update was parsed,
    authorized and claimed, and is now owed a run.  Absent means the status is
    already terminal — the update was ignored or is a duplicate — and nothing
    further will happen to it.
    """

    status: str
    incoming: IncomingUpdate | None = None


class InMemoryUpdateDeduplicator:
    """Process-local duplicate guard until Phase 6 persists Telegram updates."""

    def __init__(self) -> None:
        self._seen: set[int] = set()
        self._lock = Lock()

    def already_seen(self, update_id: int) -> bool:
        with self._lock:
            if update_id in self._seen:
                return True
            self._seen.add(update_id)
            return False

    def clear(self) -> None:
        """Clear state for tests and process lifecycle management."""

        with self._lock:
            self._seen.clear()


deduplicator = InMemoryUpdateDeduplicator()
update_repository = TelegramUpdateRepository()
run_repository = AgentRunRepository()
thread_repository = AgentThreadRepository()


def admit_telegram_update(
    update: dict[str, Any],
    *,
    repository: TelegramUpdateRepository | None = None,
) -> TelegramAdmission:
    """Run Receive → Validate → Authorize → Deduplicate, touching no network.

    Split out of the run itself so the webhook can answer Telegram from here.
    Every phase in this function is either pure or a single indexed write, so
    the decision costs milliseconds; everything that can cost a minute — the
    transcript, the download, the agent — lives in :func:`fulfil_telegram_update`
    and now happens after Telegram has already been answered.

    The reason is measured, not theoretical: Telegram closes a webhook
    connection after sixty seconds, and a run reaching a hundred seconds ended
    as ``Read timeout expired`` with the update redelivered, even though the
    reply itself was sent successfully.
    """

    incoming = _extract_update(update)
    if settings.telegram_allowed_user_id is None:
        raise ConfigurationError("TELEGRAM_ALLOWED_USER_ID is not configured.")
    if incoming.user_id != settings.telegram_allowed_user_id:
        error = UnauthorizedUserError()
        logger.warning("telegram.update.unauthorized", extra={"error_type": type(error).__name__})
        return TelegramAdmission(status="ignored")
    # Direct callers may use the in-memory guard in isolated tests. The HTTP
    # adapter supplies the PostgreSQL repository explicitly at runtime.
    claimed = (
        repository.claim(incoming.update_id)
        if repository
        else deduplicator.already_seen(incoming.update_id)
    )
    if not claimed:
        logger.info("telegram.update.duplicate")
        return TelegramAdmission(status="duplicate")
    return TelegramAdmission(status="accepted", incoming=incoming)


async def process_telegram_update(
    update: dict[str, Any],
    *,
    client: TelegramClient | None = None,
    agent_runner: Callable[..., AgentRun] = run_agent,
    repository: TelegramUpdateRepository | None = None,
    audit_repository: AgentRunRepository | None = None,
    conversation_repository: AgentThreadRepository | None = None,
    radar_repository: RadarOperationRepository | None = None,
    transcriber: TranscriptionService | None = None,
) -> TelegramProcessResult:
    """Admit one update and run it to completion, in that order.

    The whole use case end to end, for callers that have no response to hold
    open: tests, and any future transport that is not an HTTP webhook.  The
    webhook itself calls the two halves separately, because the point of the
    split is to answer between them.
    """

    admission = admit_telegram_update(update, repository=repository)
    if admission.incoming is None:
        return TelegramProcessResult(status=admission.status)
    return await fulfil_telegram_update(
        admission.incoming,
        client=client,
        agent_runner=agent_runner,
        repository=repository,
        audit_repository=audit_repository,
        conversation_repository=conversation_repository,
        radar_repository=radar_repository,
        transcriber=transcriber,
    )


async def fulfil_telegram_update(
    incoming: IncomingUpdate,
    *,
    client: TelegramClient | None = None,
    agent_runner: Callable[..., AgentRun] = run_agent,
    repository: TelegramUpdateRepository | None = None,
    audit_repository: AgentRunRepository | None = None,
    conversation_repository: AgentThreadRepository | None = None,
    radar_repository: RadarOperationRepository | None = None,
    transcriber: TranscriptionService | None = None,
) -> TelegramProcessResult:
    """Run Transcribe → Invoke → Respond for an update already admitted.

    Transcription sits after deduplication on purpose: a redelivered update
    must not be paid for twice at the speech endpoint.  Deduplication happened
    in :func:`admit_telegram_update`, which is the only caller that may decide
    an update deserves to reach here.
    """

    update_id, chat_id = incoming.update_id, incoming.chat_id
    text = incoming.text
    audio, attachment, unsupported = incoming.audio, incoming.attachment, incoming.unsupported
    user_id = incoming.user_id

    run_id = str(uuid4())
    # run_agent is synchronous because the Deep Agent executor is sync; run it
    # in the worker pool so the webhook can continue serving requests.
    from starlette.concurrency import run_in_threadpool

    owns_client = client is None
    telegram_client: TelegramClient | None = None
    progress: DraftProgress | None = None
    started_at = time.perf_counter()
    with bind_correlation_context(run_id=run_id):
        try:
            telegram_client = client or _create_client()
            if unsupported is not None:
                # No draft balloon: there is no work to narrate, only a fact to
                # state.  The update is marked processed because it is finished
                # — retrying it would produce this same answer forever.
                await send_reply(telegram_client, chat_id, _unsupported_reply(unsupported))
                if repository:
                    repository.mark_processed(update_id)
                logger.info(
                    "telegram.update.unsupported",
                    extra={
                        "telegram_update_id": update_id,
                        "status": "unsupported",
                        "attachment_kind": unsupported or "empty",
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    },
                )
                return TelegramProcessResult(status="ignored")
            if audio is None and attachment is None and _is_clear_command(text):
                # No draft balloon, for the same reason as above: there is no
                # work to narrate, only a fact to state.
                threads = conversation_repository or thread_repository
                thread_id = threads.get_or_create_main_thread(user_id)
                with bind_correlation_context(thread_id=thread_id):
                    threads.reset(thread_id)
                await send_reply(telegram_client, chat_id, CLEARED_REPLY)
                if repository:
                    repository.mark_processed(update_id)
                logger.info(
                    "telegram.update.cleared",
                    extra={
                        "telegram_update_id": update_id,
                        "status": "cleared",
                        "thread_id": thread_id,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    },
                )
                return TelegramProcessResult(status="cleared")
            # The draft starts before the transcription or the download, not
            # after them: fetching what the user sent is the slowest part of a
            # voice or file update, and it used to be the part the chat sat
            # silent through.
            progress = await DraftProgress.start(
                telegram_client,
                chat_id=chat_id,
                draft_id=update_id,
                initial=_initial_draft_text(audio=audio, attachment=attachment),
            )
            if audio is not None:
                transcript = await transcribe_voice_message(
                    telegram_client,
                    chat_id=chat_id,
                    audio=audio,
                    transcriber=transcriber,
                )
                if transcript is None:
                    # The user already knows why; the update is finished.
                    if repository:
                        repository.mark_processed(update_id)
                    return TelegramProcessResult(status="ignored")
                text = transcript
                progress.announce(THINKING_DRAFT_TEXT)

            threads = conversation_repository or thread_repository
            thread_id = threads.get_or_create_main_thread(user_id)
            with bind_correlation_context(thread_id=thread_id):
                conversation = threads.history(thread_id)
                # Read once, here, so the block the model sees is the store as
                # it stood when the run began — a write made during the run is
                # persisted immediately and shows up on the next one. An
                # attachment is folded in before anything else reads it.
                workspace: Mapping[str, object] | None = threads.workspace(thread_id)
                if attachment is not None:
                    intake = await receive_attachment(
                        telegram_client,
                        chat_id=chat_id,
                        attachment=attachment,
                        workspace=dict(workspace or {}),
                    )
                    if intake is None:
                        # The user already knows why; the update is finished.
                        if repository:
                            repository.mark_processed(update_id)
                        return TelegramProcessResult(status="ignored")
                    workspace = intake.workspace
                    # From here the turn is an ordinary text turn: the message
                    # says what arrived and where it is, and the file itself is
                    # something the agent opens with the tools it already has.
                    text = build_attachment_message(intake, incoming.caption)
                    progress.announce(THINKING_DRAFT_TEXT)
                # A RADAR proposal is answered before the generic approval
                # gate.  Unlike that gate it is never replayed through the
                # model: this path executes the exact stored payload once.
                radar_operations = (
                    radar_repository or radar_operation_repository()
                    if settings.radar_writes_enabled
                    else None
                )
                pending_radar = (
                    radar_operations.pending(thread_id=thread_id, telegram_user_id=user_id)
                    if radar_operations is not None
                    else None
                )
                if pending_radar is not None:
                    decision = _approval_decision(text)
                    if decision is False:
                        if pending_radar.execution_context is not None:
                            radar_service().execute_saved_operation(
                                operation=pending_radar.operation,
                                target_id=pending_radar.target_id,
                                expected_revision=pending_radar.expected_revision,
                                parameters=pending_radar.parameters,
                                idempotency_key=pending_radar.idempotency_key,
                                execution_context=pending_radar.execution_context,
                                approval_source=RadarMessageSource.from_telegram(
                                    update_id=update_id,
                                    chat_id=chat_id,
                                    message_id=incoming.message_id,
                                    author_id=user_id,
                                    timestamp=incoming.timestamp,
                                    text=text,
                                ).metadata(),
                                approve=False,
                            )
                        radar_operations.reject(pending_radar)
                        reply = "Certo, descartei a proposta RADAR. Nenhum registro foi alterado."
                        await progress.aclose()
                        await send_reply(telegram_client, chat_id, reply)
                        threads.save_exchange(thread_id, user_text=text, assistant_reply=reply)
                        if repository:
                            repository.mark_processed(update_id)
                        return TelegramProcessResult(status="processed")
                    if decision is True:
                        if radar_operations.claim_approval(pending_radar):
                            result = radar_service().execute_saved_operation(
                                operation=pending_radar.operation,
                                target_id=pending_radar.target_id,
                                expected_revision=pending_radar.expected_revision,
                                parameters=pending_radar.parameters,
                                idempotency_key=pending_radar.idempotency_key,
                                **(
                                    {
                                        "execution_context": pending_radar.execution_context,
                                        "approval_source": RadarMessageSource.from_telegram(
                                            update_id=update_id,
                                            chat_id=chat_id,
                                            message_id=incoming.message_id,
                                            author_id=user_id,
                                            timestamp=incoming.timestamp,
                                            text=text,
                                        ).metadata(),
                                    }
                                    if pending_radar.execution_context is not None
                                    else {}
                                ),
                            )
                            radar_operations.finish(pending_radar, result)
                            reply = radar_execution_reply(result, pending_radar)
                        else:
                            reply = "Essa proposta RADAR já foi consumida ou expirou; nada foi aplicado."
                        await progress.aclose()
                        await send_reply(telegram_client, chat_id, reply)
                        threads.save_exchange(thread_id, user_text=text, assistant_reply=reply)
                        if repository:
                            repository.mark_processed(update_id)
                        return TelegramProcessResult(status="processed")
                    # An unrelated message must not leave a stale proposal able
                    # to authorize a later bare “sim”.  It becomes the new ask.
                    radar_operations.reject(pending_radar)
                pending_override = (
                    radar_operations.pending_override(thread_id=thread_id, telegram_user_id=user_id)
                    if radar_operations is not None
                    else None
                )
                if pending_override is not None:
                    if normalize_human_reference(text) == "registrar como novo fato":
                        proposal = radar_operations.consume_override(
                            pending_override,
                            ttl_seconds=settings.radar_approval_ttl_seconds,
                        )
                        reply = (
                            radar_approval_question(proposal)
                            if proposal is not None
                            else "A opção de registrar como novo fato expirou; nada foi alterado."
                        )
                        await progress.aclose()
                        await send_reply(telegram_client, chat_id, reply)
                        threads.save_exchange(thread_id, user_text=text, assistant_reply=reply)
                        if repository:
                            repository.mark_processed(update_id)
                        return TelegramProcessResult(status="processed")
                    radar_operations.dismiss_override(pending_override)
                recoverable_radar = (
                    radar_operations.recoverable(thread_id=thread_id, telegram_user_id=user_id)
                    if radar_operations is not None
                    else None
                )
                if recoverable_radar is not None and _approval_decision(text) is True:
                    # The package may have committed before its response or
                    # receipt could be persisted.  Reconciliation is permitted
                    # only with this unchanged payload and idempotency key.
                    if radar_operations.claim_recovery(recoverable_radar):
                        result = radar_service().execute_saved_operation(
                            operation=recoverable_radar.operation,
                            target_id=recoverable_radar.target_id,
                            expected_revision=recoverable_radar.expected_revision,
                            parameters=recoverable_radar.parameters,
                            idempotency_key=recoverable_radar.idempotency_key,
                            **(
                                {
                                    "execution_context": recoverable_radar.execution_context,
                                    "approval_source": RadarMessageSource.from_telegram(
                                        update_id=update_id,
                                        chat_id=chat_id,
                                        message_id=incoming.message_id,
                                        author_id=user_id,
                                        timestamp=incoming.timestamp,
                                        text=text,
                                    ).metadata(),
                                }
                                if recoverable_radar.execution_context is not None
                                else {}
                            ),
                        )
                        if (
                            recoverable_radar.execution_context is not None
                            and result.get("status") != "executed"
                        ):
                            # A blocked reconciliation cannot prove that the original commit failed.
                            # Preserve uncertainty until the same receipt can be checked successfully.
                            result = {
                                "status": "failed",
                                "code": "persistence_failure",
                                "created_ids": [],
                                "target_id": None,
                                "revision": None,
                                "operation_id": None,
                            }
                        radar_operations.finish(recoverable_radar, result)
                        reply = radar_execution_reply(result, recoverable_radar)
                    else:
                        reply = "A reconciliação da proposta RADAR já está em andamento; nada foi repetido."
                    await progress.aclose()
                    await send_reply(telegram_client, chat_id, reply)
                    threads.save_exchange(thread_id, user_text=text, assistant_reply=reply)
                    if repository:
                        repository.mark_processed(update_id)
                    return TelegramProcessResult(status="processed")
                # A pending write approval is answered before anything else:
                # while one is open, this thread already asked a closed
                # question, and the answer decides whether there is a run at
                # all. The row is cleared either way — an approval is consumed
                # once, and an unrelated message supersedes it.
                pending_approval = threads.pending_write_approval(thread_id)
                agent_text = text
                approved_writes: tuple[dict[str, str], ...] = ()
                if pending_approval is not None:
                    decision = _approval_decision(text)
                    threads.clear_pending_write_approval(thread_id)
                    if decision is False:
                        # There is no run to narrate: a refusal is answered
                        # here and now, so the balloon stops before the answer
                        # rather than beside it.
                        await progress.aclose()
                        await send_reply(telegram_client, chat_id, APPROVAL_REFUSED_REPLY)
                        threads.save_exchange(
                            thread_id,
                            user_text=text,
                            assistant_reply=APPROVAL_REFUSED_REPLY,
                        )
                        if repository:
                            repository.mark_processed(update_id)
                        logger.info(
                            "telegram.update.responded",
                            extra={
                                "telegram_update_id": update_id,
                                "status": "approval_refused",
                                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                            },
                        )
                        return TelegramProcessResult(status="processed")
                    if decision is True:
                        # "sim" carries no instruction of its own, so the run
                        # replays the message that was refused, now with the
                        # grant attached.
                        agent_text = pending_approval.request_text
                        approved_writes = pending_approval.requests
                pending_radar_selection = threads.pending_radar_selection(thread_id)
                if pending_radar_selection is not None:
                    # A thread can carry only the question it actually showed.
                    # Clean up rows produced by older versions before a single
                    # number has a chance to select both RADAR and Notion.
                    threads.clear_pending_task_selection(thread_id)
                if pending_radar_selection is not None and pending_radar_selection.expired:
                    # A numbered answer is authority to use one exact snapshot,
                    # so it has the same bounded lifetime as a write proposal.
                    # Once expired, even an otherwise valid ordinal must not be
                    # replayed against the original mutation request.
                    threads.clear_pending_radar_selection(thread_id)
                    if _is_selection_expression(text):
                        await progress.aclose()
                        await send_reply(
                            telegram_client,
                            chat_id,
                            RADAR_SELECTION_EXPIRED_REPLY,
                        )
                        threads.save_exchange(
                            thread_id,
                            user_text=text,
                            assistant_reply=RADAR_SELECTION_EXPIRED_REPLY,
                        )
                        if repository:
                            repository.mark_processed(update_id)
                        return TelegramProcessResult(status="processed")
                    pending_radar_selection = None
                selected_radar = _selected_radar(text, pending_radar_selection)
                if selected_radar is not None and pending_radar_selection is not None:
                    # A number carries no business instruction.  Resume the
                    # exact request that produced the application-owned list,
                    # now with only the selected reference attached.
                    agent_text = pending_radar_selection.request_text
                elif pending_radar_selection is not None and _is_selection_expression(text):
                    # An out-of-range number/ordinal is not a new instruction
                    # and must never fall through to the model as one.
                    reply = radar_selection_reply(
                        pending_radar_selection.candidates,
                        purpose=pending_radar_selection.purpose,
                    )
                    await progress.aclose()
                    await send_reply(telegram_client, chat_id, reply)
                    threads.save_exchange(thread_id, user_text=text, assistant_reply=reply)
                    if repository:
                        repository.mark_processed(update_id)
                    return TelegramProcessResult(status="processed")
                elif pending_radar_selection is not None:
                    # A different message supersedes the closed question.  An
                    # old list can never select a resource for a later ask.
                    threads.clear_pending_radar_selection(thread_id)
                if selected_radar is not None and pending_radar_selection is not None:
                    try:
                        radar_message_source = RadarMessageSource.from_metadata(
                            pending_radar_selection.source_context,
                            text=agent_text,
                        )
                    except (TypeError, ValueError):
                        radar_message_source = None
                else:
                    radar_message_source = RadarMessageSource.from_telegram(
                        update_id=update_id,
                        chat_id=chat_id,
                        message_id=incoming.message_id,
                        author_id=user_id,
                        timestamp=incoming.timestamp,
                        text=agent_text,
                    )
                # A link the user pasted is itself the permission to open it
                # (ADR-013). The origins come from ``agent_text``, which is the
                # text this run actually acts on, so a replayed message keeps
                # the links it originally carried. Anything the model reaches
                # for beyond these origins still has to be approved.
                approved_writes += user_supplied_origins(agent_text)
                memories = memory_service().entries(thread_id)
                pending_selection = threads.pending_task_selection(thread_id)
                selected_task = _selected_task(text, pending_selection)
                if (
                    pending_selection is not None
                    and selected_task is None
                    and _SELECTION_PATTERN.fullmatch(text) is None
                ):
                    # A different request supersedes an unanswered question.
                    # Never let an old choice authorize an unrelated later
                    # mutation.
                    threads.clear_pending_task_selection(thread_id)
                stored_radar_referents = threads.radar_referents(
                    thread_id,
                    max_age_seconds=settings.radar_approval_ttl_seconds,
                )
                logger.info("telegram.update.accepted", extra={"telegram_update_id": update_id})
                # Wall-clock boundaries of the agent execution itself, so the
                # audit records how long the run took and not when the row was
                # written.
                run_started_at = datetime.now(UTC)
                if radar_message_source is None:
                    run = await run_in_threadpool(
                        _invoke_agent,
                        agent_runner,
                        agent_text,
                        run_id,
                        thread_id,
                        conversation,
                        selected_task,
                        selected_radar,
                        stored_radar_referents,
                        approved_writes,
                        workspace,
                        memories,
                        progress.report,
                    )
                else:
                    with bind_radar_source_context(radar_message_source):
                        run = await run_in_threadpool(
                            _invoke_agent,
                            agent_runner,
                            agent_text,
                            run_id,
                            thread_id,
                            conversation,
                            selected_task,
                            selected_radar,
                            stored_radar_referents,
                            approved_writes,
                            workspace,
                            memories,
                            progress.report,
                        )
                run_completed_at = datetime.now(UTC)
                radar_context_references = _radar_context_references(
                    selected_radar,
                    stored_radar_referents,
                )
                if any(call.name.startswith("radar_") for call in run.tool_calls) or (
                    radar_context_references
                ):
                    run = replace(
                        run,
                        reply=humanize_radar_reply(
                            run.reply,
                            run.tool_calls,
                            references=radar_context_references,
                            reveal_identifiers=asks_for_technical_identifiers(agent_text),
                        ),
                    )
                else:
                    # A denial may copy a callable name from the model's tool
                    # definitions without ever making a RADAR call.  The
                    # public-name barrier therefore runs on every reply.
                    run = replace(run, reply=scrub_internal_radar_names(run.reply))
                # A run held for approval already carries its own question; a
                # second one about which task to pick would replace it and lose
                # the only answer this turn can act on.
                task_candidates = (
                    _ambiguous_task_candidates(run)
                    if _looks_like_task_mutation(text) and not run.pending_approvals
                    else ()
                )
                radar_candidates, radar_purpose = (
                    _ambiguous_radar_candidates(run, text=agent_text)
                    if (_looks_like_radar_mutation(agent_text) or _has_radar_proposal_attempt(run))
                    and not run.pending_approvals
                    else ((), "subject")
                )
                if radar_candidates:
                    # Only the list rendered below may become a future numeric
                    # authority. A hidden Notion list from the same model run
                    # is discarded.
                    task_candidates = ()
                if task_candidates:
                    run = replace(run, reply=_selection_reply(task_candidates))
                if radar_candidates:
                    run = replace(
                        run,
                        reply=radar_selection_reply(radar_candidates, purpose=radar_purpose),
                    )
                    if not selection_is_resolvable(radar_candidates):
                        # A number is useful only when every displayed option
                        # is meaningful to the person reading it. Ask for a
                        # human discriminator instead of persisting codes.
                        radar_candidates = ()
                # Stop narrating before the answer lands: a balloon still
                # claiming to be working, next to the finished reply, would be
                # the one part of the chat that is no longer true.
                await progress.aclose()
                pending_radar = (
                    radar_operations.pending(thread_id=thread_id, telegram_user_id=user_id)
                    if radar_operations is not None
                    else None
                )
                if pending_radar is not None:
                    # The model's wording is not the authorization UI.  It may
                    # have stopped after the tool result, but the application
                    # always owns the exact question and its expiration facts.
                    run = replace(run, reply=radar_approval_question(pending_radar))
                    task_candidates = ()
                    radar_candidates = ()
                    threads.clear_pending_task_selection(thread_id)
                    threads.clear_pending_radar_selection(thread_id)
                pending_override = (
                    radar_operations.pending_override(thread_id=thread_id, telegram_user_id=user_id)
                    if radar_operations is not None and pending_radar is None
                    else None
                )
                if pending_override is not None:
                    run = replace(run, reply=radar_duplicate_intent_reply(pending_override))
                    task_candidates = ()
                    radar_candidates = ()
                await send_reply(telegram_client, chat_id, run.reply)
                if audit_repository:
                    audit_repository.save(
                        run,
                        telegram_update_id=update_id,
                        thread_id=thread_id,
                        started_at=run_started_at,
                        completed_at=run_completed_at,
                    )
                # ``None`` means the run produced no state snapshot at all, so
                # there is nothing to learn from it — overwriting the stored
                # workspace with nothing would delete files a previous turn
                # legitimately wrote.
                if run.workspace is not None:
                    threads.save_workspace(thread_id, run.workspace)
                if run.pending_approvals:
                    threads.save_pending_write_approval(
                        thread_id,
                        run.pending_approvals,
                        request_text=agent_text,
                    )
                if task_candidates:
                    threads.save_pending_task_selection(thread_id, task_candidates)
                elif selected_task is not None and _confirmed_task_mutation(run):
                    threads.clear_pending_task_selection(thread_id)
                if radar_candidates and pending_radar is None:
                    threads.save_pending_radar_selection(
                        thread_id,
                        radar_candidates,
                        purpose=radar_purpose,
                        request_text=agent_text,
                        source_context=(
                            radar_message_source.metadata()
                            if radar_message_source is not None
                            else {}
                        ),
                        ttl_seconds=settings.radar_approval_ttl_seconds,
                    )
                elif selected_radar is not None and (
                    pending_radar is not None or _confirmed_radar_reference_use(run, selected_radar)
                ):
                    threads.clear_pending_radar_selection(thread_id)
                radar_references = references_from_tool_calls(run.tool_calls)
                if radar_references:
                    threads.save_radar_referents(
                        thread_id,
                        focused=focused_reference(run.tool_calls, radar_references),
                        listed=radar_references,
                        source_run_id=run.run_id,
                    )
                threads.save_exchange(thread_id, user_text=text, assistant_reply=run.reply)
                if repository:
                    repository.mark_processed(update_id)
                logger.info(
                    "telegram.update.responded",
                    extra={
                        "telegram_update_id": update_id,
                        "status": run.status,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    },
                )
                return TelegramProcessResult(status="processed", run_id=run.run_id)
        except Exception as exc:
            if repository:
                repository.mark_failed(update_id)
            logger.error(
                "telegram.update.failed",
                extra={
                    "telegram_update_id": update_id,
                    "status": "failed",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        finally:
            if progress is not None:
                await progress.aclose()
            if owns_client and telegram_client is not None:
                await telegram_client.close()


async def send_reply(client: TelegramClient, chat_id: int, reply: str) -> None:
    """Deliver a message as richly as this chat accepts, never failing on markup.

    Public because it is the layer's only outbound path: a scheduled
    notification has to reach the chat through exactly the same three rungs as
    a webhook reply, or it would be the one message in the system whose
    formatting can fail differently.

    Three rungs, each one the previously proven behaviour of the rung below:
    a Rich Message with headings, lists and collapsible sections; the classic
    ``parse_mode="HTML"`` message; plain text.  Only ``400`` steps down — an
    authentication or rate-limit failure must still surface.
    """

    remaining = (
        await _send_rich_reply(client, chat_id, reply)
        if settings.telegram_rich_messages_enabled
        else (reply,)
    )
    for chunk in remaining:
        await _send_classic_reply(client, chat_id, chunk)


async def notify_update_failed(chat_id: int, *, client: TelegramClient | None = None) -> None:
    """Tell the chat a run died, because from now on nothing else will.

    While the run happened inside the webhook, a failure became a ``503`` and
    Telegram redelivered the update — the retry was the notification.  Now that
    the update is acknowledged first, that safety net is gone: an exception
    would leave the user watching a draft balloon that simply stops.

    Best effort by construction.  This is the last thing that runs for a failed
    update, so an error raised here has nowhere left to go and is logged
    instead of propagated.
    """

    owns_client = client is None
    telegram_client: TelegramClient | None = None
    try:
        # Building the client is inside the try because it is one of the
        # things that can fail: an unconfigured token raises here, and this
        # function exists precisely to swallow what has nowhere left to go.
        telegram_client = client or _create_client()
        await send_reply(telegram_client, chat_id, PROCESSING_FAILED_REPLY)
    except Exception as exc:  # noqa: BLE001 - nothing above this can act on it
        logger.error(
            "telegram.failure_notice.undeliverable",
            extra={"status": "failed", "exception_type": type(exc).__name__},
        )
    finally:
        if owns_client and telegram_client is not None:
            await telegram_client.close()


async def _send_rich_reply(client: TelegramClient, chat_id: int, reply: str) -> tuple[str, ...]:
    """Deliver what the rich rung accepts, returning the source it did not.

    Returning the remainder rather than a yes/no is what keeps every piece
    delivered exactly once: a refusal in the middle of a long reply hands the
    pieces still owed to the rung below, instead of dropping them or repeating
    what already arrived.

    The attempt is abandoned before the first request when the renderer reports
    that the message would exceed Telegram's block budget — that payload would
    be refused whole, so there is nothing to gain by sending it.
    """

    chunks = split_rich_message(reply)
    rendered = [render_rich_html(chunk) for chunk in chunks]
    if any(html is None for html in rendered):
        logger.info("telegram.reply.rich_skipped", extra={"status": "degraded"})
        return chunks
    for index, html in enumerate(html for html in rendered if html is not None):
        try:
            await client.send_rich_message(chat_id, html)
        except TelegramAPIError as error:
            if error.status_code != 400:
                raise
            # The reply text stays out of the log; only the fact is recorded.
            logger.warning("telegram.reply.rich_rejected", extra={"status": "degraded"})
            return chunks[index:]
    return ()


async def _send_classic_reply(client: TelegramClient, chat_id: int, reply: str) -> None:
    """Deliver the reply formatted, degrading to plain text instead of failing.

    Formatting is a presentation detail: a reply the user can read without
    entities is far better than no reply at all.  Telegram answers ``400`` when
    it cannot parse the markup, and only that case is retried without
    ``parse_mode`` — an authentication or rate-limit failure must still surface.
    Link previews are disabled because a Notion card under every answer buries
    the answer itself.
    """

    for chunk in split_message(reply):
        try:
            await client.send_message(
                chat_id,
                render_html(chunk),
                parse_mode="HTML",
                disable_link_preview=True,
            )
        except TelegramAPIError as error:
            if error.status_code != 400:
                raise
            # The reply text stays out of the log; only the fact is recorded.
            logger.warning("telegram.reply.formatting_rejected", extra={"status": "degraded"})
            await client.send_message(chat_id, chunk, disable_link_preview=True)


def _invoke_agent(
    agent_runner: Callable[..., AgentRun],
    text: str,
    run_id: str,
    thread_id: str,
    conversation: Sequence[ConversationMessage],
    selected_task: dict[str, str] | None,
    selected_radar: dict[str, object] | None,
    radar_referents: RadarConversationReferents | None,
    approved_writes: Sequence[dict[str, str]] = (),
    workspace: Mapping[str, object] | None = None,
    memories: Sequence[MemoryEntry] = (),
    on_progress: ProgressReporter | None = None,
) -> AgentRun:
    """Pass the outer correlation id to the real runner without breaking test fakes."""

    parameters = inspect.signature(agent_runner).parameters
    kwargs: dict[str, object] = {}
    if "on_progress" in parameters and on_progress is not None:
        kwargs["on_progress"] = on_progress
    if "approved_writes" in parameters and approved_writes:
        kwargs["approved_writes"] = tuple(approved_writes)
    if "memories" in parameters and memories:
        kwargs["memories"] = tuple(memories)
    if "workspace" in parameters and workspace:
        kwargs["workspace"] = dict(workspace)
    if "run_id" in parameters:
        kwargs["run_id"] = run_id
    if "thread_id" in parameters:
        kwargs["thread_id"] = thread_id
    if "conversation" in parameters:
        from langchain_core.messages import AIMessage, HumanMessage

        kwargs["conversation"] = tuple(
            HumanMessage(content=item.content)
            if item.role == "user"
            else AIMessage(content=item.content)
            for item in conversation
        )
    if "selected_task" in parameters and selected_task is not None:
        kwargs["selected_task"] = selected_task
    if "selected_radar" in parameters and selected_radar is not None:
        kwargs["selected_radar"] = selected_radar
    if "radar_referents" in parameters and radar_referents is not None:
        kwargs["radar_referents"] = {
            "focused": radar_referents.focused,
            "listed": radar_referents.listed,
        }
    return agent_runner(text, **kwargs)


def _selected_task(
    text: str,
    pending_selection: PendingTaskSelection | None,
) -> dict[str, str] | None:
    """Resolve only a whole-number choice from the candidates we saved ourselves."""

    if pending_selection is None:
        return None
    match = _SELECTION_PATTERN.fullmatch(text)
    if match is None:
        return None
    position = int(match.group(1)) - 1
    if 0 <= position < len(pending_selection.candidates):
        return pending_selection.candidates[position]
    return None


def _selected_radar(
    text: str,
    pending_selection: PendingRadarSelection | None,
) -> dict[str, object] | None:
    """Resolve only an explicit choice from a server-owned RADAR candidate list."""

    if pending_selection is None:
        return None
    position = _selection_position(text)
    if position is not None and 0 <= position < len(pending_selection.candidates):
        return {
            "purpose": pending_selection.purpose,
            "entity": pending_selection.candidates[position],
        }

    # A person may answer with the complete title instead of a number. Accent
    # and case differences are harmless, but a duplicated title remains
    # ambiguous and therefore selects nothing.
    answer = normalize_human_reference(text.strip(" \t\n\r\"'“”"))
    matches = [
        candidate
        for candidate in pending_selection.candidates
        if normalize_human_reference(str(candidate["title"])) == answer
    ]
    if len(matches) == 1:
        return {"purpose": pending_selection.purpose, "entity": matches[0]}
    return None


def _selection_position(text: str) -> int | None:
    numeric = _SELECTION_PATTERN.fullmatch(text)
    if numeric is not None:
        return int(numeric.group(1)) - 1
    normalized = normalize_human_reference(text).strip(" .!")
    normalized = re.sub(r"^(?:opcao|item)\s+", "", normalized)
    normalized = re.sub(r"\s+(?:opcao|item)$", "", normalized)
    return _RADAR_ORDINALS.get(normalized)


def _is_selection_expression(text: str) -> bool:
    """Whether a closed-list answer was attempted, even when it is invalid."""

    if _SELECTION_PATTERN.fullmatch(text):
        return True
    normalized = normalize_human_reference(text).strip(" .!")
    normalized = re.sub(r"^(?:opcao|item)\s+", "", normalized)
    normalized = re.sub(r"\s+(?:opcao|item)$", "", normalized)
    return normalized in _RADAR_ORDINALS


def _approval_decision(text: str) -> bool | None:
    """Read a whole-message yes or no, or ``None`` when the question was dropped.

    Only a message that is *nothing but* an answer counts.  Consent to modify a
    file has to be unambiguous, and a sentence that merely contains "sim" is far
    more likely to be a new request than an authorization.
    """

    if _APPROVAL_GRANTED_PATTERN.fullmatch(text):
        return True
    if _APPROVAL_REFUSED_PATTERN.fullmatch(text):
        return False
    return None


def _looks_like_task_mutation(text: str) -> bool:
    """Conservatively distinguish a change request from a read-only search."""

    return _TASK_MUTATION_PATTERN.search(text) is not None


def _looks_like_radar_mutation(text: str) -> bool:
    """Conservatively detect a RADAR write whose reference may need a choice."""

    return _RADAR_MUTATION_PATTERN.search(text) is not None


def _has_radar_proposal_attempt(run: AgentRun) -> bool:
    """Trust the tool trace, not a finite verb list, to identify a blocked write."""

    return any(call.name.startswith("radar_propose_") for call in run.tool_calls)


def _ambiguous_radar_candidates(
    run: AgentRun,
    *,
    text: str,
) -> tuple[tuple[dict[str, object], ...], str]:
    """Extract one confirmed multi-result RADAR search and its business role."""

    for call in reversed(run.calls_to("radar_search_entities")):
        result = call.result
        if call.status != "succeeded" or not isinstance(result, dict):
            continue
        raw_entities = result.get("entities")
        if not isinstance(raw_entities, list) or len(raw_entities) < 2:
            continue
        candidates: list[dict[str, object]] = []
        for entity in raw_entities:
            if not isinstance(entity, dict):
                return (), "subject"
            entity_id = entity.get("id")
            title = entity.get("title")
            entity_type = entity.get("type")
            status = entity.get("status")
            revision = entity.get("revision")
            if (
                not isinstance(entity_id, str)
                or not isinstance(title, str)
                or not isinstance(entity_type, str)
                or not isinstance(status, str)
                or type(revision) is not int
            ):
                return (), "subject"
            candidates.append(
                {
                    "id": entity_id,
                    "title": title,
                    "type": entity_type,
                    "status": status,
                    "revision": revision,
                }
            )
        return tuple(candidates), _radar_selection_purpose(call.arguments, text=text)
    return (), "subject"


def _radar_selection_purpose(arguments: Mapping[str, object], *, text: str) -> str:
    entity_type = arguments.get("entity_type")
    normalized = normalize_human_reference(text)
    if entity_type == "person" and ("deleg" in normalized or "atrib" in normalized):
        return "executor"
    if entity_type == "person" and any(
        token in normalized for token in ("responsavel", "dono", "owner")
    ):
        return "owner"
    if entity_type == "indicator" and any(
        token in normalized for token in ("medicao", "medir", "meca", "indicador")
    ):
        return "target"
    if entity_type in {"document", "feedback", "indicator", "learning", "meeting"}:
        return "evidence"
    return "target"


def _ambiguous_task_candidates(run: AgentRun) -> tuple[dict[str, str], ...]:
    """Extract id/title pairs only from a confirmed multi-result task search."""

    for call in reversed(run.calls_to("search_tasks")):
        result = call.result
        if call.status != "succeeded" or not isinstance(result, dict):
            continue
        raw_tasks = result.get("tasks")
        if not isinstance(raw_tasks, list) or len(raw_tasks) < 2:
            continue
        candidates: list[dict[str, str]] = []
        for task in raw_tasks:
            if not isinstance(task, dict):
                return ()
            task_id = task.get("id")
            title = task.get("title")
            if not isinstance(task_id, str) or not isinstance(title, str):
                return ()
            candidates.append({"id": task_id, "title": title})
        return tuple(candidates)
    return ()


def _selection_reply(candidates: Sequence[dict[str, str]]) -> str:
    """Render a deterministic, numbered clarification instead of model prose.

    The titles are marked as bold in the same Markdown subset the model uses,
    so this text goes through the single rendering path in
    ``app/integrations/telegram_format``.  A title containing an asterisk keeps
    its markers visible instead of being rendered — a display detail, never a
    rejected message.
    """

    options = "\n".join(
        f"{index}. **{task['title']}**" for index, task in enumerate(candidates, start=1)
    )
    return f"Encontrei {len(candidates)} tarefas relacionadas:\n{options}\n\nResponda apenas com o número da tarefa."


def _confirmed_task_mutation(run: AgentRun) -> bool:
    """A selection is consumed only after the requested write is confirmed."""

    return any(call.name in {"update_task", "complete_task"} and call.ok for call in run.tool_calls)


def _confirmed_radar_reference_use(
    run: AgentRun,
    selected: Mapping[str, object],
) -> bool:
    """Consume a choice only after a confirmed tool observation used its id."""

    entity = selected.get("entity")
    entity_id = entity.get("id") if isinstance(entity, Mapping) else None
    if not isinstance(entity_id, str):
        return False
    for call in run.tool_calls:
        if not call.name.startswith("radar_") or call.status != "succeeded":
            continue
        if entity_id in call.arguments.values():
            return True
    return False


def _radar_context_references(
    selected: Mapping[str, object] | None,
    referents: RadarConversationReferents | None,
) -> tuple[dict[str, object], ...]:
    """Collect trusted names used only to keep the public reply human-readable."""

    candidates: list[Mapping[str, object]] = []
    if selected is not None:
        entity = selected.get("entity")
        if isinstance(entity, Mapping):
            candidates.append(entity)
    if referents is not None:
        if referents.focused is not None:
            candidates.append(referents.focused)
        candidates.extend(referents.listed)

    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in candidates:
        entity_id = candidate.get("id")
        if not isinstance(entity_id, str) or entity_id in seen:
            continue
        seen.add(entity_id)
        result.append(dict(candidate))
    return tuple(result[:10])


def _initial_draft_text(
    *,
    audio: TelegramAudio | None,
    attachment: TelegramAttachment | None,
) -> str:
    """Name the wait the user is actually in before the run begins."""

    if audio is not None:
        return TRANSCRIBING_DRAFT_TEXT
    if attachment is not None:
        return RECEIVING_FILE_DRAFT_TEXT
    return THINKING_DRAFT_TEXT


def _create_client() -> TelegramClient:
    from app.integrations.telegram_client import create_telegram_client

    return create_telegram_client()


@dataclass(frozen=True)
class IncomingUpdate:
    """The parts of one Telegram update this application acts on."""

    update_id: int
    user_id: int
    chat_id: int
    message_id: int
    timestamp: str
    text: str = ""
    audio: TelegramAudio | None = None
    attachment: TelegramAttachment | None = None
    caption: str = ""
    unsupported: str | None = None


def _extract_update(update: dict[str, Any]) -> IncomingUpdate:
    """Validate the subset of a Telegram message the assistant understands.

    Three shapes carry a request.  Plain ``text`` is one.  A voice message is
    another, and reaches this point with an empty ``text`` that the transcript
    replaces once the recording has been read.  A document or a photo is the
    third: the file becomes a stored attachment and the ``caption`` becomes the
    instruction that came with it — which is why the caption is read here and
    nowhere else.  Acting on the words around a file *without* the file would
    answer a question the user did not ask; now that the file itself is
    readable, the two travel together.

    Anything else the chat can carry — a video, a sticker, a service message
    with no text at all — comes back as the ``unsupported`` kind rather than as
    an exception.  That distinction is the whole point: Telegram retries any
    update the webhook does not answer ``2xx``, and it retries it *ahead of
    everything sent afterwards*, so raising here once cost fourteen hours of
    silence in which five later messages sat undelivered behind a single PDF.
    An update we will never be able to act on has to be answered and closed,
    never refused.

    A payload we cannot even identify a chat in still raises: there is nobody
    to answer, retrying cannot help either, and it is not a shape Telegram
    produces — so it stays loud instead of being swallowed.
    """

    update_id = update.get("update_id")
    message = update.get("message")
    if (
        not isinstance(update_id, int)
        or isinstance(update_id, bool)
        or not isinstance(message, dict)
    ):
        raise TypeError("Telegram update must contain an integer update_id and message.")
    sender = message.get("from")
    chat = message.get("chat")
    text = message.get("text")
    caption = message.get("caption")
    message_id = message.get("message_id")
    message_date = message.get("date")
    user_id = sender.get("id") if isinstance(sender, dict) else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if not all(
        isinstance(value, int) and not isinstance(value, bool) for value in (user_id, chat_id)
    ):
        raise TypeError("Telegram message must contain integer sender and chat ids.")
    if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
        # Telegram always supplies this. The fallback keeps old stored/test
        # payloads processable without pretending their source was model-authored.
        message_id = update_id if update_id > 0 else 1
    timestamp = (
        datetime.fromtimestamp(message_date, UTC).isoformat().replace("+00:00", "Z")
        if isinstance(message_date, int) and not isinstance(message_date, bool)
        else datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    identity = {
        "update_id": update_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "timestamp": timestamp,
    }

    audio = TelegramAudio.from_message(message)
    if audio is not None:
        return IncomingUpdate(**identity, audio=audio)
    attachment = TelegramAttachment.from_message(message)
    if attachment is not None:
        return IncomingUpdate(
            **identity,
            attachment=attachment,
            caption=caption.strip() if isinstance(caption, str) else "",
        )
    if not isinstance(text, str) or not text.strip():
        return IncomingUpdate(**identity, unsupported=_unsupported_kind(message))
    return IncomingUpdate(**identity, text=text.strip())


#: Attachment fields, in the order they are reported, mapped to how the reply
#: names them.  ``document`` and ``photo`` are absent because they are read
#: now; what remains is what has no reader — a video the model cannot watch, a
#: sticker with nothing to say, a poll that is not a request.
_UNSUPPORTED_KINDS: tuple[tuple[str, str], ...] = (
    ("video", "vídeo"),
    ("video_note", "vídeo"),
    ("animation", "GIF"),
    ("sticker", "figurinha"),
    ("location", "localização"),
    ("contact", "contato"),
    ("poll", "enquete"),
)


def _unsupported_kind(message: dict[str, Any]) -> str:
    """Name what arrived, falling back to the empty message that carried it."""

    for field, label in _UNSUPPORTED_KINDS:
        if message.get(field):
            return label
    return ""


def _is_clear_command(text: str | None) -> bool:
    """Whether the whole message is the reset command and nothing else.

    Anchored on both ends on purpose: "/clear" inside a sentence is the user
    talking about the command, and discarding a conversation is not something
    to infer from a mention of it.
    """

    return bool(text) and _CLEAR_COMMAND_PATTERN.match(text or "") is not None


def _unsupported_reply(kind: str) -> str:
    """Say plainly what was not read, so nobody waits on an answer never coming."""

    if not kind:
        return (
            "Recebi uma mensagem sem texto e não consigo agir sobre ela. "
            "Me manda por texto ou áudio o que você precisa?"
        )
    return (
        f"Ainda não consigo ler {kind}. Entendo texto, áudio e arquivos (PDF, imagem, "
        "texto, planilha, documento e apresentação) — se puder, me mande de uma dessas formas."
    )


__all__ = [
    "APPROVAL_REFUSED_REPLY",
    "CLEARED_REPLY",
    "PROCESSING_FAILED_REPLY",
    "THINKING_DRAFT_TEXT",
    "InMemoryUpdateDeduplicator",
    "IncomingUpdate",
    "TelegramAdmission",
    "TelegramProcessResult",
    "admit_telegram_update",
    "deduplicator",
    "fulfil_telegram_update",
    "notify_update_failed",
    "process_telegram_update",
    "thread_repository",
]
