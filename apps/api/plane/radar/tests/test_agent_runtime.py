"""Authenticated product facade: authority, bounded context and stable remote intent."""

import json
import os
from uuid import uuid4

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from plane.radar.commands.runtime_control import issue_runtime_credential
from plane.radar.models import ActorGrant, AgentRuntimeRun, Object, RuntimeCredential
from plane.radar.api import agent_views
from .test_runtime_contract import runtime  # noqa: F401
from .test_commands import create
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def product(runtime):  # noqa: F811 - imported pytest fixture
    ctx, _, old, _, person, _ = runtime
    binding, _ = issue_runtime_credential(
        actor=ctx[5],
        workspace=ctx[3],
        actor_id=old.actor_id,
        context=old.context,
        external_author=f"plane:{ctx[0].pk}",
        reviewer_id=ctx[0].pk,
        person_id=person.pk,
        channel="plane",
    )
    client = APIClient()
    client.force_authenticate(user=ctx[0])
    return runtime, binding, client


def endpoint(product, suffix):
    return f"/api/workspaces/{product[0][0][3].slug}/radar/agent-runtime/{suffix}/"


def payload(product, **extra):
    return {"binding_id": str(product[1].pk), "root_ids": [str(product[0][4].pk)], "prompt": "Analyze context", **extra}


def test_session_identity_not_payload_and_retries_preserve_snapshot(product, monkeypatch):
    calls = []

    def remote(path, data, **kwargs):
        calls.append(data)
        return {"contract_version": "1.0", "run_id": data["run_id"], "status": "queued"}

    monkeypatch.setattr(agent_views, "runtime_request", remote)
    api = product[2]
    assert (
        api.post(
            endpoint(product, "runs"),
            {**payload(product), "user_id": str(uuid4())},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key",
        ).status_code
        == 400
    )
    first = api.post(endpoint(product, "runs"), payload(product), format="json", HTTP_IDEMPOTENCY_KEY="key")
    assert first.status_code == 202
    second = api.post(endpoint(product, "runs"), payload(product), format="json", HTTP_IDEMPOTENCY_KEY="key")
    assert first.data == second.data and calls[0] == calls[1]
    assert calls[0]["identity"]["user_id"] == str(product[0][0][0].pk)
    assert calls[0]["identity"]["channel"] == "plane.session"
    assert "telegram" not in json.dumps(calls[0])
    assert AgentRuntimeRun.objects.count() == 1
    assert (
        api.post(
            endpoint(product, "runs"), payload(product, prompt="Different"), format="json", HTTP_IDEMPOTENCY_KEY="key"
        ).status_code
        == 409
    )


def test_recovery_after_response_loss_uses_same_remote_run(product, monkeypatch):
    seen = []
    from plane.radar.agent_runtime import RuntimeUnavailable

    def remote(path, data, **kwargs):
        seen.append(data["run_id"])
        if len(seen) == 1:
            raise RuntimeUnavailable()
        return {"contract_version": "1.0", "run_id": data["run_id"], "status": "completed"}

    monkeypatch.setattr(agent_views, "runtime_request", remote)
    api = product[2]
    assert (
        api.post(endpoint(product, "runs"), payload(product), format="json", HTTP_IDEMPOTENCY_KEY="lost").status_code
        == 503
    )
    assert (
        api.post(endpoint(product, "runs"), payload(product), format="json", HTTP_IDEMPOTENCY_KEY="lost").status_code
        == 202
    )
    assert seen[0] == seen[1] and AgentRuntimeRun.objects.count() == 1


def test_cross_user_and_revocation_prevent_remote_calls(product, monkeypatch):
    def remote(path, data, **kwargs):
        return {"contract_version": "1.0", "run_id": data["run_id"], "status": "interrupted"}

    monkeypatch.setattr(agent_views, "runtime_request", remote)
    api = product[2]
    run = api.post(
        endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="scope"
    ).data["run_id"]
    monkeypatch.setattr(agent_views, "runtime_request", lambda *a, **kw: pytest.fail("Unauthorized remote call"))
    api.force_authenticate(user=product[0][0][1])
    assert api.post(endpoint(product, f"runs/{run}/resume"), {}, format="json").status_code == 404
    assert (
        api.post(
            endpoint(product, "context"), {k: v for k, v in payload(product).items() if k != "prompt"}, format="json"
        ).status_code
        == 404
    )
    api.force_authenticate(user=product[0][0][0])
    fixture_write(lambda: ActorGrant.objects.filter(actor_id=product[1].actor_id).update(is_active=False))
    assert api.post(endpoint(product, f"runs/{run}/status"), {}, format="json").status_code == 403


def test_changed_context_or_policy_blocks_resume(product, monkeypatch):
    monkeypatch.setattr(
        agent_views,
        "runtime_request",
        lambda path, data, **kw: {"contract_version": "1.0", "run_id": data["run_id"], "status": "interrupted"},
    )
    api = product[2]
    run = api.post(
        endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="stale"
    ).data["run_id"]
    monkeypatch.setattr(agent_views, "runtime_request", lambda *a, **kw: pytest.fail("Stale remote call"))
    person = product[0][4]
    fixture_write(lambda: Object.objects.filter(pk=person.pk).update(version=person.version + 1))
    assert api.post(endpoint(product, f"runs/{run}/resume"), {}, format="json").status_code == 409


def test_context_hides_unbound_objects_and_limits_text(product):
    ctx = product[0][0]
    hidden = create(ctx, "objective")
    fixture_write(lambda: Object.objects.filter(pk=product[0][4].pk).update(content="x" * 9000))
    data = {k: v for k, v in payload(product).items() if k != "prompt"}
    response = product[2].post(endpoint(product, "context"), data, format="json")
    assert response.status_code == 200 and response.data["truncated"]
    assert len(response.data["objects"][0]["content"]) == 1500
    assert str(hidden.pk) not in json.dumps(response.data)
    assert (
        product[2].post(endpoint(product, "context"), {**data, "root_ids": [str(hidden.pk)]}, format="json").status_code
        == 404
    )


def test_plane_binding_cannot_impersonate_telegram(product):
    token = "private-plane-test-token"
    import hashlib

    fixture_write(
        lambda: RuntimeCredential.objects.filter(pk=product[1].pk).update(
            token_hash=hashlib.sha256(token.encode()).hexdigest()
        )
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    url = f"/api/workspaces/{product[0][0][3].slug}/radar/runtime/v1/capabilities/"
    assert client.get(url).status_code == 401


def test_real_http_product_cycle(product, monkeypatch):
    url = os.environ.get("RADAR_AGENT_TEST_URL")
    if not url:
        pytest.skip("Set RADAR_AGENT_TEST_URL to the isolated CoS product test server")
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_URL", url)
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_TOKEN", "radar-local-integration-test-key-0001")
    api = product[2]
    first = api.post(
        endpoint(product, "runs"),
        payload(product, start_paused=True, skill="context_summary"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="live",
    )
    assert first.status_code == 202 and first.data["status"] == "interrupted", first.data
    run = first.data["run_id"]
    assert api.post(endpoint(product, f"runs/{run}/resume"), {}, format="json").status_code == 200
    import time

    result = None
    for _ in range(40):
        result = api.post(endpoint(product, f"runs/{run}/status"), {}, format="json")
        if result.data.get("status") == "completed":
            break
        time.sleep(0.05)
    assert result.data["status"] == "completed", result.data
    assert result.data["result"]["sources"][0]["id"] == str(product[0][4].pk)
    stream = api.post(endpoint(product, f"runs/{run}/stream"), {}, format="json")
    assert stream.status_code == 200 and b"event: completed" in stream.content
    replay = api.post(
        endpoint(product, "runs"),
        payload(product, start_paused=True, skill="context_summary"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="live",
    )
    assert replay.data["run_id"] == run and replay.data["result"] == result.data["result"]


@pytest.mark.parametrize("change", ["policy", "binding", "membership", "person", "deleted_person", "schema"])
def test_authority_changes_block_existing_runs(product, monkeypatch, change):
    monkeypatch.setattr(
        agent_views,
        "runtime_request",
        lambda path, data, **kw: {"contract_version": "1.0", "run_id": data["run_id"], "status": "interrupted"},
    )
    api = product[2]
    run = api.post(
        endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="authority"
    ).data["run_id"]
    monkeypatch.setattr(agent_views, "runtime_request", lambda *a, **kw: pytest.fail("Revoked remote call"))
    if change == "policy":
        fixture_write(lambda: ActorGrant.objects.filter(actor_id=product[1].actor_id).update(policy_version=2))
    elif change == "binding":
        fixture_write(lambda: RuntimeCredential.objects.filter(pk=product[1].pk).update(is_active=False))
    elif change == "membership":
        from plane.db.models import WorkspaceMember

        WorkspaceMember.objects.filter(workspace=product[0][0][3], member=product[0][0][0]).update(is_active=False)
    elif change == "deleted_person":
        from django.utils import timezone

        fixture_write(lambda: Object.all_objects.filter(pk=product[1].person_id).update(deleted_at=timezone.now()))
    elif change == "schema":
        from plane.radar.models import ObjectType

        fixture_write(lambda: ObjectType.objects.filter(pk=product[0][4].object_type_id).update(is_active=False))
    else:
        from plane.radar.models import PersonIdentity

        fixture_write(lambda: PersonIdentity.objects.filter(user=product[0][0][0]).update(is_active=False))
    response = api.post(endpoint(product, f"runs/{run}/status"), {}, format="json")
    assert response.status_code in {403, 404, 409}


def test_role_change_invalidates_runtime_authority_without_schema_change(product):
    from plane.db.models import WorkspaceMember
    from plane.radar.agent_runtime import binding_for
    from plane.radar.workspace_schema import schema_revision

    ctx = product[0][0]
    before = binding_for(user=ctx[0], workspace=ctx[3], binding_id=product[1].pk)[2]
    revision = schema_revision(ctx[3])
    WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=20)
    after = binding_for(user=ctx[0], workspace=ctx[3], binding_id=product[1].pk)[2]
    assert after["authorization_hash"] != before["authorization_hash"]
    assert schema_revision(ctx[3]) == revision
