"""Telegram resolves RADAR proposals without replaying an LLM request."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.application.telegram import process_telegram_update
from app.config import settings
from app.database.radar_operations import RadarOperationRepository
from app.database.schema import metadata
from app.database.telegram_updates import TelegramUpdateRepository
from app.database.threads import AgentThreadRepository
from app.schemas.radar import RadarPreflightReport
from app.tools import close_radar_service, configure_radar_service


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_: object) -> dict[str, object]:
        self.sent.append((chat_id, text))
        return {"message_id": 1}

    async def send_rich_message_draft(self, *_: object, **__: object) -> None:
        pass

    async def send_rich_message(self, *_: object, **__: object) -> dict[str, object]:
        return {"message_id": 1}


class FakeRadarExecutor:
    write_ready = True

    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result or {
            "status": "executed",
            "code": "ok",
            "target_id": "ACT-20260912-ABC123",
            "revision": 2,
            "created_ids": [],
            "operation_id": "operation-1",
        }

    def execute_saved_operation(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return self.result

    def close(self) -> None:
        pass


@pytest.fixture
def stores():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    threads = AgentThreadRepository(engine)
    thread_id = threads.get_or_create_main_thread(42)
    proposals = RadarOperationRepository(engine)
    updates = TelegramUpdateRepository(engine)
    updates.initialize()
    yield threads, thread_id, proposals, updates
    proposals.close()
    threads.close()
    updates.close()
    engine.dispose()


def _proposal(store: RadarOperationRepository, thread_id: str):
    return store.create(
        thread_id=thread_id,
        telegram_user_id=42,
        operation="review",
        target_id="ACT-20260912-ABC123",
        expected_revision=1,
        parameters={"assessment": "Revisado", "evidence_id": "EVI-20260912-ABC123"},
        summary={
            "version": 2,
            "operation": "review",
            "target": {"title": "Revisar riscos do RADAR", "type": "action"},
            "evidence": {"title": "Ata da revisão diária", "type": "meeting"},
            "assessment": "Revisado",
        },
        ttl_seconds=300,
    )


def _update(update_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {"from": {"id": 42}, "chat": {"id": 42}, "text": text},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["sim", "não"])
async def test_command_receipt_and_confirmation_source_are_preserved(monkeypatch, stores, decision):
    from datetime import UTC, datetime
    from uuid import uuid4

    threads, thread_id, proposals, updates = stores
    receipt = {
        "backend": "command-layer",
        "command_id": str(uuid4()),
        "idempotency_key": f"radar:{uuid4()}",
        "intent_hash": "a" * 64,
    }
    proposal = proposals.create(
        thread_id=thread_id,
        telegram_user_id=42,
        operation="review",
        target_id="ACT-20260912-ABC123",
        expected_revision=1,
        parameters={"assessment": "Reviewed", "evidence_id": "DOC-20260912-ABC123"},
        summary={
            "version": 2,
            "operation": "review",
            "target": {"title": "Action", "type": "action"},
        },
        ttl_seconds=300,
        execution_context=receipt,
    )
    executor = FakeRadarExecutor()
    configure_radar_service(executor, report=RadarPreflightReport(state="ready"))
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 42)
    monkeypatch.setattr(settings, "radar_writes_enabled", True)
    monkeypatch.setattr(settings, "telegram_rich_messages_enabled", False)
    update = _update(8301, decision)
    update["message"].update(message_id=11, date=int(datetime.now(UTC).timestamp()))

    def forbidden_agent(*args, **kwargs):
        raise AssertionError("confirmation must not invoke the model")

    try:
        result = await process_telegram_update(
            update,
            client=FakeTelegram(),
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
    finally:
        close_radar_service()
    assert result.status == "processed" and len(executor.calls) == 1
    call = executor.calls[0]
    assert (
        call["execution_context"] == receipt and call["idempotency_key"] == proposal.idempotency_key
    )
    assert call["approval_source"]["author"] == "telegram:42"
    assert (
        call["approval_source"]["update_id"] == 8301 and call["approval_source"]["message_id"] == 11
    )
    assert call.get("approve", True) is (decision == "sim")


@pytest.mark.asyncio
async def test_blocked_command_reconciliation_stays_uncertain(monkeypatch, stores):
    from datetime import UTC, datetime
    from uuid import uuid4

    threads, thread_id, proposals, updates = stores
    receipt = {
        "backend": "command-layer",
        "command_id": str(uuid4()),
        "idempotency_key": f"radar:{uuid4()}",
        "intent_hash": "a" * 64,
    }
    proposal = proposals.create(
        thread_id=thread_id,
        telegram_user_id=42,
        operation="review",
        target_id="ACT-20260912-ABC123",
        expected_revision=1,
        parameters={"assessment": "Reviewed", "evidence_id": "DOC-20260912-ABC123"},
        summary={
            "version": 2,
            "operation": "review",
            "target": {"title": "Action", "type": "action"},
        },
        ttl_seconds=300,
        execution_context=receipt,
    )
    assert proposals.claim_approval(proposal)
    proposals.finish(proposal, {"status": "failed", "code": "persistence_failure"})
    executor = FakeRadarExecutor(result={"status": "rejected", "code": "not_authorized"})
    configure_radar_service(executor, report=RadarPreflightReport(state="ready"))
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 42)
    monkeypatch.setattr(settings, "radar_writes_enabled", True)
    monkeypatch.setattr(settings, "telegram_rich_messages_enabled", False)
    update = _update(8302, "sim")
    update["message"].update(message_id=12, date=int(datetime.now(UTC).timestamp()))

    def forbidden_agent(*args, **kwargs):
        raise AssertionError("reconciliation must not call a model")

    try:
        await process_telegram_update(
            update,
            client=FakeTelegram(),
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
    finally:
        close_radar_service()
    restored = proposals.recoverable(thread_id=thread_id, telegram_user_id=42)
    assert restored is not None and restored.status == "uncertain"
    assert (
        restored.execution_context == receipt
        and restored.idempotency_key == receipt["idempotency_key"]
    )


@pytest.mark.asyncio
async def test_yes_executes_the_saved_payload_once_without_invoking_the_agent(
    monkeypatch: pytest.MonkeyPatch, stores
) -> None:
    threads, thread_id, proposals, updates = stores
    proposal = _proposal(proposals, thread_id)
    executor = FakeRadarExecutor()
    configure_radar_service(executor, report=RadarPreflightReport(state="ready"))  # type: ignore[arg-type]
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 42)
    monkeypatch.setattr(settings, "radar_writes_enabled", True)
    monkeypatch.setattr(settings, "telegram_rich_messages_enabled", False)
    client = FakeTelegram()

    def forbidden_agent(*_: object, **__: object):
        raise AssertionError("approval must not reconstruct the request with an agent")

    try:
        first = await process_telegram_update(
            _update(8101, "sim"),
            client=client,
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
        duplicate = await process_telegram_update(
            _update(8101, "sim"),
            client=client,
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
    finally:
        close_radar_service()

    assert first.status == "processed"
    assert duplicate.status == "duplicate"
    assert executor.calls == [
        {
            "operation": proposal.operation,
            "target_id": proposal.target_id,
            "expected_revision": proposal.expected_revision,
            "parameters": proposal.parameters,
            "idempotency_key": proposal.idempotency_key,
        }
    ]
    assert "Revisar riscos do RADAR" in client.sent[0][1]
    assert "registrada" in client.sent[0][1]
    assert "ACT-" not in client.sent[0][1]
    assert "Revisão: 2" not in client.sent[0][1]
    assert proposals.pending(thread_id=thread_id, telegram_user_id=42) is None


@pytest.mark.asyncio
async def test_no_or_a_revision_conflict_never_reprepares_a_proposal(
    monkeypatch: pytest.MonkeyPatch, stores
) -> None:
    threads, thread_id, proposals, updates = stores
    _proposal(proposals, thread_id)
    executor = FakeRadarExecutor(result={"status": "conflict", "code": "revision_conflict"})
    configure_radar_service(executor, report=RadarPreflightReport(state="ready"))  # type: ignore[arg-type]
    monkeypatch.setattr(settings, "telegram_allowed_user_id", 42)
    monkeypatch.setattr(settings, "radar_writes_enabled", True)
    monkeypatch.setattr(settings, "telegram_rich_messages_enabled", False)
    client = FakeTelegram()

    def forbidden_agent(*_: object, **__: object):
        raise AssertionError("approval must not invoke an agent")

    try:
        refused = await process_telegram_update(
            _update(8201, "não"),
            client=client,
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
        assert refused.status == "processed"
        assert executor.calls == []
        _proposal(proposals, thread_id)
        conflicted = await process_telegram_update(
            _update(8202, "sim"),
            client=client,
            agent_runner=forbidden_agent,
            repository=updates,
            conversation_repository=threads,
            radar_repository=proposals,
        )
    finally:
        close_radar_service()

    assert conflicted.status == "processed"
    assert len(executor.calls) == 1
    assert "não refiz a operação automaticamente" in client.sent[-1][1]
    assert "ACT-" not in client.sent[-1][1]
