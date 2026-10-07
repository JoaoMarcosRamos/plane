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
