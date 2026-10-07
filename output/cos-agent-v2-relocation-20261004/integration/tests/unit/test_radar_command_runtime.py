"""Host provenance, durable receipts and uncertain commits for the HTTP backend."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database.radar_operations import RadarIntentDuplicate, RadarOperationRepository
from app.database.schema import metadata
from app.database.threads import AgentThreadRepository
from app.errors import RadarQueryError, RadarStartupError
from app.integrations.radar_commands import CORE_SHA256, RadarCommandRuntime, parameters_hash
from app.observability import bind_correlation_context
from app.security.radar_provenance import RadarMessageSource, bind_radar_source_context
from app.services.radar_service import RadarService


def source(text: str = "Observed 12") -> RadarMessageSource:
    return RadarMessageSource.from_telegram(
        update_id=1,
        chat_id=42,
        message_id=1,
        author_id=42,
        timestamp=datetime.now(UTC).isoformat(),
        text=text,
    )


def capabilities() -> dict[str, object]:
    return {
        "contract_version": "1.0",
        "tbox_version": "3.2.0",
        "ontology_sha256": CORE_SHA256,
        "context": "company:test",
        "person_id": "PER-20261004-ABC123",
        "entity_count": 2,
        "definitions": {
            "capture_issue": {
                "target_types": [],
                "parameters": {
                    key: {}
                    for key in (
                        "title",
                        "case_title",
                        "evidence_title",
                        "source",
                        "priority",
                        "owner_id",
                    )
                },
            }
        },
    }


class Server:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.lost_response = False
        self.malformed_response = False
        self.caps = capabilities()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-host-token"
        if request.url.path.endswith("capabilities/"):
            return httpx.Response(200, json=self.caps)
        payload = json.loads(request.content)
        self.calls.append(payload)
        if request.url.path.endswith("prepare/"):
            receipt = {
                "backend": "command-layer",
                "contract_version": "1.0",
                "command_id": str(uuid4()),
                "intent_hash": "a" * 64,
                "idempotency_key": payload["idempotency_key"],
                "operation": payload["operation"],
                "target_id": payload["target_id"],
                "expected_revision": 0,
                "parameters_hash": parameters_hash(payload["parameters"]),
            }
            return httpx.Response(
                202,
                json={
                    "status": "pending_approval",
                    "operation": payload["operation"],
                    "context": "company:test",
                    "target_id": payload["target_id"],
                    "expected_revision": 0,
                    "parameters": payload["parameters"],
                    "execution_context": receipt,
                },
            )
        if self.lost_response:
            raise httpx.ReadTimeout("response lost after commit")
        if self.malformed_response:
            return httpx.Response(
                200, json={"status": "executed", "code": "ok", "created_ids": [str(uuid4())]}
            )
        return httpx.Response(
            200,
            json={
                "status": "executed",
                "code": "ok",
                "target_id": "MIT-20261004-ABC123",
                "revision": 1,
                "created_ids": ["MIT-20261004-ABC123"],
                "operation_id": payload["command_id"],
            },
        )


def runtime(server: Server) -> RadarCommandRuntime:
    return RadarCommandRuntime(
        base_url="https://radar.test/runtime/v1/",
        token="test-host-token",
        context="company:test",
        person_id="PER-20261004-ABC123",
        allowed_tbox_versions=frozenset({"3.2.0"}),
        client=httpx.Client(transport=httpx.MockTransport(server)),
    )


def prepare(adapter: RadarCommandRuntime) -> dict[str, object]:
    msg = source()
    with (
        bind_correlation_context(run_id=str(uuid4()), thread_id=str(uuid4())),
        bind_radar_source_context(msg),
    ):
        return adapter.prepare_operation(
            "capture_issue",
            {
                "title": "Issue",
                "case_title": "Case",
                "evidence_title": "Source",
                "source": msg.evidence_source(),
            },
            context="company:test",
            target_id=None,
        )


def test_original_run_and_source_are_sent_by_host_only() -> None:
    server = Server()
    adapter = runtime(server)
    run_id, thread_id, msg = str(uuid4()), str(uuid4()), source()
    with (
        bind_correlation_context(run_id=run_id, thread_id=thread_id),
        bind_radar_source_context(msg),
    ):
        prepared = adapter.prepare_operation(
            "capture_issue",
            {
                "title": "Issue",
                "case_title": "Case",
                "evidence_title": "Source",
                "source": msg.evidence_source(),
            },
            context="company:test",
            target_id=None,
        )
    provenance = server.calls[-1]["provenance"]
    assert provenance["run_id"] == run_id and provenance["correlation_id"] == thread_id
    assert provenance["source"] == msg.metadata()
    assert "actor_id" not in provenance and "actor_type" not in provenance
    assert prepared["execution_context"]["idempotency_key"] == server.calls[-1]["idempotency_key"]
    with pytest.raises(RadarQueryError):
        adapter.prepare_operation("capture_issue", {}, context="company:test", target_id=None)


def test_changed_payload_cannot_resume_a_saved_command() -> None:
    server = Server()
    adapter = runtime(server)
    prepared = prepare(adapter)
    receipt = prepared["execution_context"]
    before = len(server.calls)
    with pytest.raises(RadarQueryError) as error:
        adapter.execute_operation(
            "capture_issue",
            context="company:test",
            target_id=None,
            expected_revision=0,
            parameters={**prepared["parameters"], "title": "Changed"},
            idempotency_key=receipt["idempotency_key"],
            execution_context=receipt,
            approval_source=source("sim").metadata(),
        )
    assert error.value.code == "idempotency_conflict" and len(server.calls) == before


def test_vault_proposal_cannot_execute_after_backend_switch() -> None:
    server = Server()
    adapter = runtime(server)
    service = RadarService(
        runtime=adapter, context="company:test", write_operations=frozenset({"capture_issue"})
    )
    result = service.execute_saved_operation(
        operation="capture_issue",
        target_id=None,
        expected_revision=0,
        parameters={},
        idempotency_key="radar:old-vault-proposal",
    )
    assert result["code"] == "write_package_incompatible" and not server.calls


def test_response_loss_preserves_same_receipt_for_recovery() -> None:
    server = Server()
    adapter = runtime(server)
    prepared = prepare(adapter)
    receipt = prepared["execution_context"]
    service = RadarService(
        runtime=adapter, context="company:test", write_operations=frozenset({"capture_issue"})
    )
    args = {
        "operation": "capture_issue",
        "target_id": None,
        "expected_revision": 0,
        "parameters": prepared["parameters"],
        "idempotency_key": receipt["idempotency_key"],
        "execution_context": receipt,
        "approval_source": source("sim").metadata(),
    }
    server.lost_response = True
    result = service.execute_saved_operation(**args)
    assert result["status"] == "failed" and result["code"] == "persistence_failure"
    first = dict(server.calls[-1])
    server.lost_response = False
    result = service.execute_saved_operation(**args)
    assert result["code"] == "ok" and server.calls[-1] == first


def test_receipt_survives_restart_and_semantic_override() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    threads = AgentThreadRepository(engine)
    thread = threads.get_or_create_main_thread(42)
    repository = RadarOperationRepository(engine)
    receipt = prepare(runtime(Server()))["execution_context"]
    args = {
        "thread_id": thread,
        "telegram_user_id": 42,
        "operation": "capture_issue",
        "target_id": None,
        "expected_revision": 0,
        "parameters": {"title": "Issue", "case_title": "Case", "evidence_title": "Source"},
        "summary": {"operation": "capture_issue"},
        "ttl_seconds": 900,
        "context": "company:test",
        "execution_context": receipt,
    }
    proposal = repository.create(**args)
    restored = RadarOperationRepository(engine).pending(thread_id=thread, telegram_user_id=42)
    assert (
        restored.execution_context == receipt
        and restored.idempotency_key == receipt["idempotency_key"]
    )
    assert repository.claim_approval(proposal)
    repository.finish(proposal, {"status": "executed", "code": "ok"})
    new_receipt = {**receipt, "command_id": str(uuid4()), "idempotency_key": f"radar:{uuid4()}"}
    duplicate = repository.create(**{**args, "execution_context": new_receipt})
    assert isinstance(duplicate, RadarIntentDuplicate)
    overridden = repository.consume_override(duplicate, ttl_seconds=900)
    assert (
        overridden.execution_context == new_receipt
        and overridden.idempotency_key == new_receipt["idempotency_key"]
    )


def test_malformed_success_cannot_be_reported_as_no_commit() -> None:
    server = Server()
    adapter = runtime(server)
    prepared = prepare(adapter)
    receipt = prepared["execution_context"]
    service = RadarService(
        runtime=adapter, context="company:test", write_operations=frozenset({"capture_issue"})
    )
    server.malformed_response = True
    result = service.execute_saved_operation(
        operation="capture_issue",
        target_id=None,
        expected_revision=0,
        parameters=prepared["parameters"],
        idempotency_key=receipt["idempotency_key"],
        execution_context=receipt,
        approval_source=source("sim").metadata(),
    )
    assert result["code"] == "persistence_failure"


@pytest.mark.parametrize(
    "field,value",
    [
        ("ontology_sha256", "wrong"),
        ("contract_version", "2.0"),
        ("context", "company:other"),
        ("person_id", "PER-20261004-OTHER1"),
    ],
)
def test_incompatible_backend_fails_closed(field: str, value: str) -> None:
    server = Server()
    server.caps[field] = value
    with pytest.raises(RadarStartupError):
        runtime(server)


def test_command_backend_requires_url_and_token_without_vault() -> None:
    settings = Settings(
        _env_file=None,
        radar_enabled=True,
        radar_backend="command-layer",
        radar_vault_path=None,
        radar_context="company:test",
        radar_person_id="PER-20261004-ABC123",
        telegram_allowed_user_id=42,
        radar_command_url="https://radar.test/runtime/v1/",
        radar_command_token="test-host-token",
    )
    assert settings.radar_configured and settings.radar_vault_path is None
    assert "test-host-token" not in repr(settings)
