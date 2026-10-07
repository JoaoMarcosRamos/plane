"""Config lifecycle, grant ceilings and execution scope, without a provider."""

from copy import deepcopy
import os
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.db.models import WorkspaceMember
from plane.radar.api import agent_views
from plane.radar.commands.runtime_control import bind_runtime_object
from plane.radar.models import (
    ActorGrant,
    AgentConfiguration,
    AgentRuntimeRun,
    Object,
    Provenance,
    Relation,
    RelationType,
)
from .test_agent_runtime import product as product_fixture, endpoint, payload
from .test_runtime_contract import runtime  # noqa: F401
from .test_commands import create
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


product = product_fixture


def config_url(product, detail=True):
    return f"/api/workspaces/{product[0][0][3].slug}/radar/agent-config/" + (f"{product[1].pk}/" if detail else "")


def config_payload(product):
    snapshot = product[2].get(config_url(product)).data["configuration"]
    return {
        "expected_version": snapshot["version"],
        **{key: snapshot[key] for key in ("identity", "role", "policies", "permissions")},
    }


def test_defaults_are_structured_read_only_and_secret_free(product):
    api = product[2]
    result = api.get(config_url(product))
    assert result.status_code == 200 and result.data["can_edit"]
    assert result.data["configuration"]["version"] == 0
    assert result.data["configuration"]["policies"] == {
        "guidelines": [],
        "require_human_approval": True,
        "read_only": True,
    }
    assert set(result.data["configuration"]) == {
        "schema_version",
        "version",
        "identity",
        "role",
        "policies",
        "permissions",
    }
    assert "token" not in str(result.data) and "external_author" not in result.data
    assert AgentConfiguration.objects.count() == 0
    assert len(api.get(config_url(product, False)).data) == 1  # Telegram binding excluded.


def test_save_reload_version_and_provenance_without_domain_write(product):
    api = product[2]
    data = config_payload(product)
    data["identity"] = {"name": "Strategy copilot", "soul": "Ask for evidence."}
    data["role"] = {"name": "Risk analyst", "purpose": "Explain tradeoffs."}
    data["policies"]["guidelines"] = ["Disclose uncertainty"]
    before = list(Object.objects.values("id", "version", "content"))
    first = api.put(config_url(product), data, format="json")
    assert first.status_code == 200, first.data
    assert first.data["configuration"]["version"] == 1
    assert api.get(config_url(product)).data == first.data
    assert list(Object.objects.values("id", "version", "content")) == before
    config = AgentConfiguration.objects.get(binding=product[1])
    assert config.created_by_id == config.updated_by_id == product[0][0][0].pk
    assert (
        config.last_provenance_id
        and Provenance.objects.get(pk=config.last_provenance_id).command_name == "AgentConfigurationConfigured"
    )
    data["expected_version"] = 1
    data["identity"]["name"] = "Updated"
    assert api.put(config_url(product), data, format="json").data["configuration"]["version"] == 2
    assert api.put(config_url(product), data, format="json").status_code == 409
    assert api.get(config_url(product)).data["configuration"]["identity"]["name"] == "Updated"
    assert AgentConfiguration.objects.count() == 1


@pytest.mark.parametrize(
    "case",
    [
        "extra",
        "nested_extra",
        "markdown",
        "approval",
        "read_only",
        "bool_string",
        "empty_name",
        "oversize",
        "duplicate",
        "foreign_object",
        "command",
        "version_string",
    ],
)
def test_invalid_configuration_rejected_atomically(product, case):
    data = config_payload(product)
    if case == "extra":
        data["agent_id"] = str(uuid4())
    elif case == "nested_extra":
        data["identity"]["tools"] = ["shell"]
    elif case == "markdown":
        data["role"] = "# Role"
    elif case == "approval":
        data["policies"]["require_human_approval"] = False
    elif case == "read_only":
        data["policies"]["read_only"] = False
    elif case == "bool_string":
        data["policies"]["read_only"] = "true"
    elif case == "empty_name":
        data["identity"]["name"] = "   "
    elif case == "oversize":
        data["policies"]["guidelines"] = ["x" * 501]
    elif case == "duplicate":
        data["permissions"]["fields"] = ["title", "title"]
    elif case == "foreign_object":
        data["permissions"]["object_ids"] = [str(uuid4())]
    elif case == "command":
        data["permissions"]["commands"] = ["ApproveDecision"]
    else:
        data["expected_version"] = "0"
    response = product[2].put(config_url(product), data, format="json")
    assert response.status_code in {400, 403}, response.data
    assert AgentConfiguration.objects.count() == 0


def test_only_own_admin_binding_is_editable_and_revocation_hides_it(product):
    ctx = product[0][0]
    data = config_payload(product)
    api = product[2]
    api.force_authenticate(user=ctx[1])
    assert api.get(config_url(product)).status_code == 404
    assert api.get(config_url(product, False)).data == []
    assert api.put(config_url(product), data, format="json").status_code == 403
    api.force_authenticate(user=ctx[0])
    ctx[3].owner = ctx[1]
    ctx[3].save()
    assert api.get(config_url(product)).data["can_edit"] is False
    assert api.put(config_url(product), data, format="json").status_code == 403
    WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=20)
    assert api.put(config_url(product), data, format="json").status_code == 200
    fixture_write(lambda: ActorGrant.objects.filter(actor_id=product[1].actor_id).update(is_active=False))
    assert api.get(config_url(product)).status_code == 403
    assert api.get(config_url(product, False)).data == []


@pytest.mark.parametrize("key", ["object_types", "fields"])
def test_configuration_cannot_expand_explicit_ceiling(product, key):
    fixture_write(
        lambda: ActorGrant.objects.filter(actor_id=product[1].actor_id).update(
            **{key: ["person" if key == "object_types" else "title"]}
        )
    )
    data = config_payload(product)
    data["permissions"][key] = ["*"]
    assert product[2].put(config_url(product), data, format="json").status_code == 403


def test_permissions_filter_objects_relations_and_fields_before_run(product, monkeypatch):
    ctx = product[0][0]
    person, other = product[0][4:6]
    risk = create(ctx, "risk", description="Risk description")
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=risk.pk, external_id="RSK-20261004-ABC123", context=product[1].context
    )
    kind = RelationType.objects.get(workspace=ctx[3], key="owned_by")
    fixture_write(lambda: Relation.objects.create(workspace=ctx[3], relation_type=kind, source=risk, target=person))
    fixture_write(lambda: Object.objects.filter(pk=person.pk).update(content="private notes"))
    data = config_payload(product)
    data["permissions"] = {
        "commands": [],
        "object_types": ["person"],
        "fields": ["title"],
        "object_ids": [str(person.pk)],
    }
    assert product[2].put(config_url(product), data, format="json").status_code == 200
    context = product[2].post(
        endpoint(product, "context"), {"binding_id": str(product[1].pk), "root_ids": [str(person.pk)]}, format="json"
    )
    assert context.status_code == 200
    assert len(context.data["objects"]) == 1 and context.data["relations"] == []
    assert context.data["objects"][0]["content"] == "" and context.data["objects"][0]["properties"] == {}
    for hidden in (risk, other):
        assert (
            product[2]
            .post(
                endpoint(product, "context"),
                {"binding_id": str(product[1].pk), "root_ids": [str(hidden.pk)]},
                format="json",
            )
            .status_code
            == 404
        )
    seen = []
    monkeypatch.setattr(
        agent_views,
        "runtime_request",
        lambda path, request, **kw: (
            seen.append(deepcopy(request)) or {"run_id": request["run_id"], "status": "interrupted"}
        ),
    )
    response = product[2].post(
        endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="config"
    )
    assert response.status_code == 202
    assert seen[0]["agent_config"]["version"] == 1 and seen[0]["agent_config"]["permissions"]["fields"] == ["title"]


def test_config_edit_invalidates_run_and_preserves_saved_intent(product, monkeypatch):
    seen = []
    monkeypatch.setattr(
        agent_views,
        "runtime_request",
        lambda path, request, **kw: (
            seen.append(deepcopy(request)) or {"run_id": request["run_id"], "status": "interrupted"}
        ),
    )
    api = product[2]
    run = api.post(
        endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="old"
    ).data["run_id"]
    previous = deepcopy(AgentRuntimeRun.objects.get(pk=run).request_data)
    data = config_payload(product)
    data["identity"]["name"] = "New identity"
    assert api.put(config_url(product), data, format="json").status_code == 200
    monkeypatch.setattr(agent_views, "runtime_request", lambda *a, **kw: pytest.fail("Stale remote execution"))
    for operation in ("status", "stream", "resume"):
        assert api.post(endpoint(product, f"runs/{run}/{operation}"), {}, format="json").status_code == 409
    assert (
        api.post(
            endpoint(product, "runs"), payload(product, start_paused=True), format="json", HTTP_IDEMPOTENCY_KEY="old"
        ).status_code
        == 409
    )
    assert AgentRuntimeRun.objects.get(pk=run).request_data == previous


def test_reduced_grant_is_intersected_even_with_old_wildcard_configuration(product):
    data = config_payload(product)
    assert product[2].put(config_url(product), data, format="json").status_code == 200
    fixture_write(
        lambda: ActorGrant.objects.filter(actor_id=product[1].actor_id).update(
            object_types=["person"], fields=["title"], commands=["LinkObjects"], policy_version=2
        )
    )
    entry = product[2].get(config_url(product)).data
    assert entry["configuration"]["permissions"]["fields"] == ["*"]
    assert entry["effective_permissions"]["fields"] == ["title"]
    assert entry["effective_permissions"]["commands"] == ["LinkObjects"]


def test_cross_workspace_and_guest_do_not_read_configuration(product):
    ctx = product[0][0]
    api = APIClient()
    api.force_authenticate(user=ctx[2])
    assert api.get(f"/api/workspaces/{ctx[4].slug}/radar/agent-config/{product[1].pk}/").status_code in {403, 404}
    WorkspaceMember.objects.create(workspace=ctx[3], member=ctx[2], role=5)
    assert api.get(config_url(product)).status_code == 403


def test_configured_http_cycle_preserves_identity_policy_and_scope(product, monkeypatch):
    from django.conf import settings
    import time

    url = os.environ.get("RADAR_AGENT_TEST_URL")
    if not url:
        pytest.skip("Set RADAR_AGENT_TEST_URL to the isolated CoS server")
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_URL", url)
    monkeypatch.setattr(settings, "RADAR_AGENT_RUNTIME_TOKEN", "radar-local-integration-test-key-0001")
    api = product[2]
    data = config_payload(product)
    data["identity"]["name"] = "Evidence copilot"
    data["permissions"]["fields"] = ["title"]
    data["permissions"]["object_ids"] = [str(product[0][4].pk)]
    assert api.put(config_url(product), data, format="json").status_code == 200
    first = api.post(
        endpoint(product, "runs"),
        payload(product, start_paused=True),
        format="json",
        HTTP_IDEMPOTENCY_KEY="configured-http",
    )
    assert first.status_code == 202, first.data
    run_id = first.data["run_id"]
    assert api.post(endpoint(product, f"runs/{run_id}/resume"), {}, format="json").status_code == 200
    for _ in range(40):
        result = api.post(endpoint(product, f"runs/{run_id}/status"), {}, format="json")
        if result.data["status"] == "completed":
            break
        time.sleep(0.05)
    assert result.data["status"] == "completed", result.data
    assert "Evidence copilot" in result.data["result"]["text"]
    assert result.data["result"]["sources"] == [{"id": str(product[0][4].pk), "version": product[0][4].version}]
