"""Durable, single-use approval and semantic-intent records for RADAR writes.

A RADAR approval executes the exact persisted business payload with a stable
idempotency key. A recent semantic duplicate is stored separately and cannot
execute unless the user consumes its one-use explicit override.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database.schema import (
    metadata,
    pending_radar_intent_overrides,
    pending_radar_operations,
)

INTENT_FINGERPRINT_VERSION = "v1"
_ACTIVE_STATUSES = ("pending", "executing", "uncertain")
_DEDUP_STATUSES = (*_ACTIVE_STATUSES, "executed")
_PROVENANCE_PARAMETERS = frozenset({"source", "evidence_source", "evidence_text"})


class ActiveRadarProposalError(RuntimeError):
    """Raised when a thread already owns an undecided RADAR proposal."""


@dataclass(frozen=True)
class RadarOperationProposal:
    """Normalized payload reconstructed only from application-owned columns."""

    proposal_id: str
    thread_id: str
    telegram_user_id: int
    operation: str
    target_id: str | None
    expected_revision: int
    parameters: dict[str, object]
    idempotency_key: str
    summary: dict[str, object]
    status: str
    expires_at: datetime
    result: dict[str, object] | None = None
    context: str = ""
    source_context: dict[str, object] | None = None
    intent_fingerprint: str | None = None
    override_of: str | None = None
    execution_context: dict[str, object] | None = None


@dataclass(frozen=True)
class RadarIntentDuplicate:
    """A recent semantic match that deliberately did not become a proposal."""

    override_id: str
    thread_id: str
    telegram_user_id: int
    matched_proposal_id: str
    matched_status: str
    intent_fingerprint: str
    summary: dict[str, object]
    expires_at: datetime


class RadarOperationRepository:
    """Own proposal, approval, semantic-deduplication and override state."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(settings.database_url, pool_pre_ping=True)

    def initialize(self) -> None:
        """Create tables for SQLite tests; production uses the migration."""

        metadata.create_all(
            self._engine,
            tables=[pending_radar_operations, pending_radar_intent_overrides],
            checkfirst=True,
        )

    def create(
        self,
        *,
        thread_id: str,
        telegram_user_id: int,
        operation: str,
        target_id: str | None,
        expected_revision: int,
        parameters: dict[str, object],
        summary: dict[str, object],
        ttl_seconds: int,
        context: str = "",
        source_context: Mapping[str, object] | None = None,
        dedup_window_seconds: int = 86_400,
        execution_context: Mapping[str, object] | None = None,
    ) -> RadarOperationProposal | RadarIntentDuplicate:
        """Persist a proposal, or a non-executable duplicate with one-use override."""

        self.initialize()
        now = datetime.now(UTC)
        source = dict(source_context or {})
        fingerprint = semantic_intent_fingerprint(
            telegram_user_id=telegram_user_id,
            context=context,
            operation=operation,
            target_id=target_id,
            parameters=parameters,
            source_context=source,
        )
        values = _proposal_values(
            thread_id=thread_id,
            telegram_user_id=telegram_user_id,
            operation=operation,
            context=context,
            target_id=target_id,
            expected_revision=expected_revision,
            parameters=parameters,
            summary=summary,
            source_context=source,
            intent_fingerprint=fingerprint,
            ttl_seconds=ttl_seconds,
            now=now,
            execution_context=execution_context,
        )
        try:
            with self._engine.begin() as connection:
                duplicate = _recent_duplicate(
                    connection,
                    telegram_user_id=telegram_user_id,
                    intent_fingerprint=fingerprint,
                    since=now - timedelta(seconds=dedup_window_seconds),
                )
                if duplicate is not None:
                    return _stage_duplicate(
                        connection,
                        values=values,
                        matched=dict(duplicate),
                        ttl_seconds=ttl_seconds,
                        now=now,
                    )
                connection.execute(pending_radar_operations.insert().values(**values))
        except IntegrityError as exc:
            # An identical concurrent attempt can win between SELECT and
            # INSERT. Re-read it and produce the same safe duplicate outcome.
            with self._engine.begin() as connection:
                duplicate = _recent_duplicate(
                    connection,
                    telegram_user_id=telegram_user_id,
                    intent_fingerprint=fingerprint,
                    since=now - timedelta(seconds=dedup_window_seconds),
                )
                if duplicate is not None:
                    return _stage_duplicate(
                        connection,
                        values=values,
                        matched=dict(duplicate),
                        ttl_seconds=ttl_seconds,
                        now=now,
                    )
            raise ActiveRadarProposalError("thread_has_active_proposal") from exc
        return _proposal(values)

    def pending(self, *, thread_id: str, telegram_user_id: int) -> RadarOperationProposal | None:
        """Return the current proposal, expiring it atomically before exposure."""

        self.initialize()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(pending_radar_operations)
                .where(
                    pending_radar_operations.c.thread_id == thread_id,
                    pending_radar_operations.c.telegram_user_id == telegram_user_id,
                    pending_radar_operations.c.status == "pending",
                    pending_radar_operations.c.expires_at <= now,
                )
                .values(status="expired", decided_at=now)
            )
            row = (
                connection.execute(
                    select(pending_radar_operations).where(
                        pending_radar_operations.c.thread_id == thread_id,
                        pending_radar_operations.c.telegram_user_id == telegram_user_id,
                        pending_radar_operations.c.status == "pending",
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _proposal(dict(row)) if row is not None else None

    def pending_override(
        self, *, thread_id: str, telegram_user_id: int
    ) -> RadarIntentDuplicate | None:
        """Return the live one-use override option for a semantic duplicate."""

        self.initialize()
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            connection.execute(
                update(pending_radar_intent_overrides)
                .where(
                    pending_radar_intent_overrides.c.thread_id == thread_id,
                    pending_radar_intent_overrides.c.telegram_user_id == telegram_user_id,
                    pending_radar_intent_overrides.c.status == "pending",
                    pending_radar_intent_overrides.c.expires_at <= now,
                )
                .values(status="expired", decided_at=now)
            )
            row = (
                connection.execute(
                    select(pending_radar_intent_overrides).where(
                        pending_radar_intent_overrides.c.thread_id == thread_id,
                        pending_radar_intent_overrides.c.telegram_user_id == telegram_user_id,
                        pending_radar_intent_overrides.c.status == "pending",
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _duplicate(dict(row)) if row is not None else None

    def dismiss_override(self, duplicate: RadarIntentDuplicate) -> bool:
        """Consume an override option when another message supersedes it."""

        with self._engine.begin() as connection:
            changed = connection.execute(
                update(pending_radar_intent_overrides)
                .where(
                    pending_radar_intent_overrides.c.override_id == duplicate.override_id,
                    pending_radar_intent_overrides.c.status == "pending",
                )
                .values(status="superseded", decided_at=datetime.now(UTC))
            ).rowcount
        return bool(changed)

    def consume_override(
        self, duplicate: RadarIntentDuplicate, *, ttl_seconds: int
    ) -> RadarOperationProposal | None:
        """Atomically turn one explicit override into one approval proposal."""

        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(pending_radar_intent_overrides).where(
                        pending_radar_intent_overrides.c.override_id == duplicate.override_id,
                        pending_radar_intent_overrides.c.thread_id == duplicate.thread_id,
                        pending_radar_intent_overrides.c.telegram_user_id
                        == duplicate.telegram_user_id,
                        pending_radar_intent_overrides.c.status == "pending",
                        pending_radar_intent_overrides.c.expires_at > now,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            active = connection.execute(
                select(pending_radar_operations.c.proposal_id).where(
                    pending_radar_operations.c.thread_id == duplicate.thread_id,
                    pending_radar_operations.c.status.in_(_ACTIVE_STATUSES),
                )
            ).first()
            if active is not None:
                return None
            payload = row.payload
            if not isinstance(payload, dict) or not isinstance(row.summary, dict):
                return None
            override_fingerprint = (
                f"{INTENT_FINGERPRINT_VERSION}o:"
                + hashlib.sha256(f"{row.intent_fingerprint}:{row.override_id}".encode()).hexdigest()
            )
            values = _proposal_values(
                thread_id=str(payload["thread_id"]),
                telegram_user_id=int(payload["telegram_user_id"]),
                operation=str(payload["operation"]),
                context=str(payload.get("context", "")),
                target_id=str(payload["target_id"]) if payload.get("target_id") else None,
                expected_revision=int(payload["expected_revision"]),
                parameters=dict(payload["parameters"]),
                summary=dict(row.summary),
                source_context=dict(payload.get("source_context") or {}),
                intent_fingerprint=override_fingerprint,
                ttl_seconds=ttl_seconds,
                now=now,
                override_of=str(row.matched_proposal_id),
                execution_context=payload.get("execution_context"),
            )
            connection.execute(pending_radar_operations.insert().values(**values))
            changed = connection.execute(
                update(pending_radar_intent_overrides)
                .where(
                    pending_radar_intent_overrides.c.override_id == duplicate.override_id,
                    pending_radar_intent_overrides.c.status == "pending",
                )
                .values(status="consumed", decided_at=now, proposal_id=values["proposal_id"])
            ).rowcount
            if not changed:
                raise RuntimeError("radar_override_already_consumed")
        return _proposal(values)

    def reject(self, proposal: RadarOperationProposal) -> bool:
        """Consume one pending proposal without touching the RADAR runtime."""

        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            changed = connection.execute(
                update(pending_radar_operations)
                .where(
                    pending_radar_operations.c.proposal_id == proposal.proposal_id,
                    pending_radar_operations.c.thread_id == proposal.thread_id,
                    pending_radar_operations.c.telegram_user_id == proposal.telegram_user_id,
                    pending_radar_operations.c.status == "pending",
                )
                .values(status="rejected", decided_at=now)
            ).rowcount
        return bool(changed)

    def claim_approval(self, proposal: RadarOperationProposal) -> bool:
        """Turn pending into executing exactly once, only while still unexpired."""

        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            changed = connection.execute(
                update(pending_radar_operations)
                .where(
                    pending_radar_operations.c.proposal_id == proposal.proposal_id,
                    pending_radar_operations.c.thread_id == proposal.thread_id,
                    pending_radar_operations.c.telegram_user_id == proposal.telegram_user_id,
                    pending_radar_operations.c.status == "pending",
                    pending_radar_operations.c.expires_at > now,
                )
                .values(status="executing", decided_at=now)
            ).rowcount
        return bool(changed)

    def finish(self, proposal: RadarOperationProposal, result: dict[str, object]) -> None:
        """Persist a safe terminal result after the idempotent package call."""

        status = result.get("status")
        terminal = (
            "executed"
            if status == "executed"
            else "conflict"
            if status == "conflict"
            else "uncertain"
            if result.get("code") == "persistence_failure"
            else "failed"
        )
        with self._engine.begin() as connection:
            connection.execute(
                update(pending_radar_operations)
                .where(
                    pending_radar_operations.c.proposal_id == proposal.proposal_id,
                    pending_radar_operations.c.status == "executing",
                )
                .values(status=terminal, executed_at=datetime.now(UTC), result=_safe_result(result))
            )

    def recoverable(
        self, *, thread_id: str, telegram_user_id: int
    ) -> RadarOperationProposal | None:
        """Return an uncertain attempt that may only retry with its same key."""

        self.initialize()
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(pending_radar_operations).where(
                        pending_radar_operations.c.thread_id == thread_id,
                        pending_radar_operations.c.telegram_user_id == telegram_user_id,
                        pending_radar_operations.c.status == "uncertain",
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _proposal(dict(row)) if row is not None else None

    def claim_recovery(self, proposal: RadarOperationProposal) -> bool:
        """Claim a saved uncertain proposal for idempotent reconciliation."""

        with self._engine.begin() as connection:
            changed = connection.execute(
                update(pending_radar_operations)
                .where(
                    pending_radar_operations.c.proposal_id == proposal.proposal_id,
                    pending_radar_operations.c.status == "uncertain",
                )
                .values(status="executing")
            ).rowcount
        return bool(changed)

    def close(self) -> None:
        self._engine.dispose()


def semantic_intent_fingerprint(
    *,
    telegram_user_id: int,
    context: str,
    operation: str,
    target_id: str | None,
    parameters: Mapping[str, object],
    source_context: Mapping[str, object],
) -> str:
    """Hash normalized business intent and immutable source identity."""

    business_parameters = {
        key: _normalize(item)
        for key, item in parameters.items()
        if key not in _PROVENANCE_PARAMETERS
    }
    source_hash = source_context.get("text_sha256")
    canonical = {
        "actor": telegram_user_id,
        "context": context.strip(),
        "operation": operation.strip(),
        "target": target_id,
        "parameters": business_parameters,
        "source_text_sha256": source_hash if isinstance(source_hash, str) else None,
        "version": INTENT_FINGERPRINT_VERSION,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return f"{INTENT_FINGERPRINT_VERSION}:{digest}"


def _normalize(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _proposal_values(
    *,
    thread_id: str,
    telegram_user_id: int,
    operation: str,
    context: str,
    target_id: str | None,
    expected_revision: int,
    parameters: Mapping[str, object],
    summary: Mapping[str, object],
    source_context: Mapping[str, object],
    intent_fingerprint: str,
    ttl_seconds: int,
    now: datetime,
    override_of: str | None = None,
    execution_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    proposal_id = str(uuid4())
    return {
        "proposal_id": proposal_id,
        "thread_id": thread_id,
        "telegram_user_id": telegram_user_id,
        "operation": operation,
        "context": context,
        "target_id": target_id,
        "expected_revision": expected_revision,
        "parameters": dict(parameters),
        "idempotency_key": str(execution_context["idempotency_key"])
        if execution_context
        else f"radar:{proposal_id}",
        "execution_context": dict(execution_context) if execution_context else None,
        "summary": dict(summary),
        "source_context": dict(source_context),
        "intent_version": INTENT_FINGERPRINT_VERSION,
        "intent_fingerprint": intent_fingerprint,
        "override_of": override_of,
        "status": "pending",
        "created_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "decided_at": None,
        "executed_at": None,
        "result": None,
    }


def _recent_duplicate(
    connection: Connection,
    *,
    telegram_user_id: int,
    intent_fingerprint: str,
    since: datetime,
):
    return (
        connection.execute(
            select(pending_radar_operations)
            .where(
                pending_radar_operations.c.telegram_user_id == telegram_user_id,
                pending_radar_operations.c.intent_fingerprint == intent_fingerprint,
                pending_radar_operations.c.status.in_(_DEDUP_STATUSES),
                pending_radar_operations.c.created_at >= since,
            )
            .order_by(pending_radar_operations.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )


def _stage_duplicate(
    connection: Connection,
    *,
    values: Mapping[str, object],
    matched: Mapping[str, object],
    ttl_seconds: int,
    now: datetime,
) -> RadarIntentDuplicate:
    connection.execute(
        update(pending_radar_intent_overrides)
        .where(
            pending_radar_intent_overrides.c.thread_id == values["thread_id"],
            pending_radar_intent_overrides.c.status == "pending",
        )
        .values(status="superseded", decided_at=now)
    )
    override_values = {
        "override_id": str(uuid4()),
        "thread_id": values["thread_id"],
        "telegram_user_id": values["telegram_user_id"],
        "matched_proposal_id": matched["proposal_id"],
        "matched_status": matched["status"],
        "intent_fingerprint": values["intent_fingerprint"],
        "payload": {
            key: values[key]
            for key in (
                "thread_id",
                "telegram_user_id",
                "operation",
                "context",
                "target_id",
                "expected_revision",
                "parameters",
                "source_context",
                "execution_context",
            )
        },
        "summary": dict(matched["summary"]),
        "status": "pending",
        "created_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "decided_at": None,
        "proposal_id": None,
    }
    connection.execute(pending_radar_intent_overrides.insert().values(**override_values))
    return _duplicate(override_values)


def _proposal(values: Mapping[str, object]) -> RadarOperationProposal:
    parameters = values.get("parameters")
    summary = values.get("summary")
    result = values.get("result")
    expires_at = values.get("expires_at")
    source_context = values.get("source_context")
    if (
        not isinstance(parameters, dict)
        or not isinstance(summary, dict)
        or not isinstance(expires_at, datetime)
    ):
        raise TypeError("Invalid persisted RADAR proposal")
    return RadarOperationProposal(
        proposal_id=str(values["proposal_id"]),
        thread_id=str(values["thread_id"]),
        telegram_user_id=int(values["telegram_user_id"]),
        operation=str(values["operation"]),
        target_id=str(values["target_id"]) if values.get("target_id") is not None else None,
        expected_revision=int(values["expected_revision"]),
        parameters=dict(parameters),
        idempotency_key=str(values["idempotency_key"]),
        summary=dict(summary),
        status=str(values["status"]),
        expires_at=expires_at,
        result=dict(result) if isinstance(result, dict) else None,
        context=str(values.get("context") or ""),
        source_context=dict(source_context) if isinstance(source_context, dict) else None,
        intent_fingerprint=(
            str(values["intent_fingerprint"])
            if values.get("intent_fingerprint") is not None
            else None
        ),
        override_of=str(values["override_of"]) if values.get("override_of") else None,
        execution_context=dict(values["execution_context"])
        if isinstance(values.get("execution_context"), dict)
        else None,
    )


def _duplicate(values: Mapping[str, object]) -> RadarIntentDuplicate:
    summary = values.get("summary")
    expires_at = values.get("expires_at")
    if not isinstance(summary, dict) or not isinstance(expires_at, datetime):
        raise TypeError("Invalid persisted RADAR intent override")
    return RadarIntentDuplicate(
        override_id=str(values["override_id"]),
        thread_id=str(values["thread_id"]),
        telegram_user_id=int(values["telegram_user_id"]),
        matched_proposal_id=str(values["matched_proposal_id"]),
        matched_status=str(values.get("matched_status") or "executed"),
        intent_fingerprint=str(values["intent_fingerprint"]),
        summary=dict(summary),
        expires_at=expires_at,
    )


def _safe_result(result: dict[str, object]) -> dict[str, object]:
    """Keep stable package evidence, excluding package messages and ABox prose."""

    return {
        key: result.get(key)
        for key in ("status", "code", "target_id", "revision", "created_ids", "operation_id")
        if key in result
    }


__all__ = [
    "INTENT_FINGERPRINT_VERSION",
    "ActiveRadarProposalError",
    "RadarIntentDuplicate",
    "RadarOperationProposal",
    "RadarOperationRepository",
    "semantic_intent_fingerprint",
]
