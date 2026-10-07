"""Contract and integration tests for the actual CoS adapter and shared dispatcher."""

import hashlib
import json
import os
import sys
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from plane.radar.commands import configure_person_identity, register_actor_grant
from plane.radar.commands.runtime_control import bind_runtime_object, issue_runtime_credential
from plane.radar.commands.operations import OPERATIONS
from plane.radar.models import (
    ActorGrant,
    CommandApproval,
    CommandExecution,
    DomainEvent,
    Object,
    OperationalRecord,
    Provenance,
    Relation,
    RuntimeObjectIdentity,
)
from .test_commands import create, execute
from plane.radar.commands import initialize_semantic_model
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def message(text="Capture this issue", author="telegram:42", update=1):
    return {
        "update_id": update,
        "chat_id": 42,
        "message_id": update,
        "author": author,
        "timestamp": (timezone.now() - timedelta(seconds=5)).isoformat(),
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def evidence_source(source):
    return (
        f"telegram:update={source['update_id']};chat={source['chat_id']};message={source['message_id']};"
        f"author={source['author']};timestamp={source['timestamp']};sha256={source['text_sha256']}"
    )


@pytest.fixture
def runtime(context):
    ctx = context
    initialize_semantic_model(actor=ctx[5], workspace=ctx[3])
    person = create(ctx, "person")
    executor = create(ctx, "person")
    configure_person_identity(actor=ctx[5], workspace=ctx[3], user_id=ctx[0].pk, person_id=person.pk)
    ids = {}
    for obj, code in ((person, "PER-20261004-ABC123"), (executor, "PER-20261004-ABC124")):
        bind_runtime_object(actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id=code, context="company:test")
        ids[obj.pk] = code
    agent = uuid4()
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type="agent",
        actor_id=agent,
        delegator_id=ctx[0].pk,
        commands=[*OPERATIONS.values(), "LinkObjects", "CreateObject"],
        object_types=["*"],
        fields=["*"],
    )
    credential, token = issue_runtime_credential(
        actor=ctx[5],
        workspace=ctx[3],
        actor_id=agent,
        context="company:test",
        external_author="telegram:42",
        reviewer_id=ctx[0].pk,
        person_id=person.pk,
    )
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return ctx, api, credential, token, person, executor


def endpoint(runtime, path):
    return f"/api/workspaces/{runtime[0][3].slug}/radar/runtime/v1/{path}/"


def prepare(runtime, operation="capture_issue", target=None, parameters=None, source=None, **extra):
    source = source or message()
    data = {
        "operation": operation,
        "parameters": parameters
        or {"title": "Issue", "case_title": "Case", "evidence_title": "Source", "source": evidence_source(source)},
        "target_id": target,
        "idempotency_key": str(uuid4()),
        "provenance": {
            "run_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "reason": "Test integration",
            "source": source,
        },
        **extra,
    }
    return runtime[1].post(endpoint(runtime, "prepare"), data, format="json")


def resolve(runtime, prepared, approve=True):
    receipt = prepared["execution_context"]
    return runtime[1].post(
        endpoint(runtime, "resolve"),
        {
            "command_id": receipt["command_id"],
            "intent_hash": receipt["intent_hash"],
            "idempotency_key": receipt["idempotency_key"],
            "approve": approve,
            "rationale": "Human confirmed" if approve else "Human rejected",
            "source": message("sim" if approve else "não", update=2),
        },
        format="json",
    )


def bind(runtime, obj, prefix):
    code = f"{prefix}-20261004-{uuid4().hex[:6].upper()}"
    bind_runtime_object(
        actor=runtime[0][5], workspace=runtime[0][3], object_id=obj.pk, external_id=code, context="company:test"
    )
    return code


def test_prepare_approve_replay_preserves_actor_and_only_domain_ids(runtime):
    count = Object.objects.count()
    pending = prepare(runtime)
    assert pending.status_code == 202, pending.data
    assert Object.objects.count() == count
    stored = CommandExecution.objects.get(pk=pending.data["execution_context"]["command_id"])
    original = stored.actor_context
    result = resolve(runtime, pending.data)
    assert result.status_code == 200, result.data
    assert result.data["code"] == "ok" and len(result.data["created_ids"]) == 3
    assert set(result.data["created_ids"]) == set(
        RuntimeObjectIdentity.objects.filter(object__created_provenance__command_id=stored.pk).values_list(
            "external_id", flat=True
        )
    )
    provenance = Provenance.objects.get(command_id=stored.pk, outcome="executed")
    assert provenance.actor_type == "agent" and provenance.actor_id == runtime[2].actor_id
    assert str(provenance.run_id) == original["run_id"]
    assert provenance.context["approver_id"] == str(runtime[0][0].pk)
    assert provenance.context["actor"]["metadata"]["message"] == original["metadata"]["message"]
    before = Object.objects.count(), Provenance.objects.count(), DomainEvent.objects.count()
    replay = resolve(runtime, pending.data)
    assert replay.data == result.data
    assert before == (Object.objects.count(), Provenance.objects.count(), DomainEvent.objects.count())
    query = runtime[1].post(
        endpoint(runtime, "query"),
        {"method": "read_entity", "parameters": {"entity_id": result.data["target_id"]}},
        format="json",
    )
    assert query.data["metadata"]["revision"] == result.data["revision"] == 1


@pytest.mark.parametrize("failure", ["reject", "expire", "grant", "version", "forged_hash", "credential", "scope"])
def test_invalid_approval_cannot_mutate_domain(runtime, failure):
    action = create(runtime[0], "action", description="Deliver")
    code = bind(runtime, action, "ACT")
    execute(
        runtime[0],
        "LinkObjects",
        {
            "source_id": str(action.pk),
            "target_id": str(runtime[4].pk),
            "relation_type_id": str(
                __import__("plane.radar.models", fromlist=["RelationType"])
                .RelationType.objects.get(workspace=runtime[0][3], key="owned_by")
                .pk
            ),
        },
    )
    executor_code = RuntimeObjectIdentity.objects.get(object=runtime[5]).external_id
    pending = prepare(
        runtime,
        "delegate",
        code,
        {"executor_id": executor_code, "due_at": (timezone.now() + timedelta(days=2)).isoformat()},
    )
    assert pending.status_code == 202, pending.data
    count = Object.objects.count()
    command_id = pending.data["execution_context"]["command_id"]
    if failure == "expire":
        fixture_write(
            lambda: CommandApproval.objects.filter(execution_id=command_id).update(
                expires_at=timezone.now() - timedelta(seconds=1)
            )
        )
    if failure == "grant":
        fixture_write(lambda: ActorGrant.objects.filter(actor_id=runtime[2].actor_id).update(is_active=False))
    if failure == "version":
        fixture_write(lambda: Object.objects.filter(pk=runtime[5].pk).update(version=2))
    if failure == "forged_hash":
        pending.data["execution_context"]["intent_hash"] = "0" * 64
    if failure == "credential":
        runtime[2].is_active = False
        fixture_write(lambda: runtime[2].save())
    if failure == "scope":
        runtime[2].object_ids = [code, RuntimeObjectIdentity.objects.get(object=runtime[4]).external_id]
        fixture_write(lambda: runtime[2].save())
    result = resolve(runtime, pending.data, approve=failure != "reject")
    assert failure == "reject" and result.status_code == 200 or result.status_code in {401, 403, 409}
    assert Object.objects.count() == count and not OperationalRecord.objects.filter(object=action).exists()
    assert not Relation.objects.filter(source=action, relation_type__key="assigned_to").exists()


def test_delegate_supersedes_commitment_and_requires_owner(runtime):
    from plane.radar.models import RelationType

    action = create(runtime[0], "action", description="Deliver")
    action_id = bind(runtime, action, "ACT")
    executor_id = RuntimeObjectIdentity.objects.get(object=runtime[5]).external_id
    parameters = {
        "executor_id": executor_id,
        "due_at": (timezone.now() + timedelta(days=2)).isoformat(),
        "next_review_at": (timezone.now() + timedelta(days=1)).isoformat(),
    }
    assert prepare(runtime, "delegate", action_id, parameters).status_code == 403
    execute(
        runtime[0],
        "LinkObjects",
        {
            "source_id": str(action.pk),
            "target_id": str(runtime[4].pk),
            "relation_type_id": str(RelationType.objects.get(workspace=runtime[0][3], key="owned_by").pk),
        },
    )
    commitment = create(runtime[0], "commitment")
    # Historical accepted terms, as they would exist after an explicit data import.
    from plane.radar.models import PropertyValue

    fixture_write(
        lambda: PropertyValue.objects.filter(object=commitment, definition__key="status").update(value="confirmed")
    )
    execute(
        runtime[0],
        "LinkObjects",
        {
            "source_id": str(commitment.pk),
            "target_id": str(action.pk),
            "relation_type_id": str(RelationType.objects.get(workspace=runtime[0][3], key="commits_to").pk),
        },
    )
    bind(runtime, commitment, "CMT")
    pending = prepare(runtime, "delegate", action_id, parameters)
    assert pending.status_code == 202, pending.data
    result = resolve(runtime, pending.data)
    assert result.status_code == 200, result.data
    from plane.radar.commands.handlers import effective_values

    assert effective_values(commitment)["status"] == "superseded"
    terms = OperationalRecord.objects.get(object=action).data["assignment"]
    assert terms["state"] == "proposed" and terms["accepted_at"] is None


def test_measurement_review_and_temporal_rules(runtime):
    from plane.radar.commands.handlers import effective_values

    indicator = create(runtime[0], "indicator")
    external = bind(runtime, indicator, "IND")
    source = message("Observed 12")
    parameters = {
        "value": 12,
        "measured_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        "evidence_title": "Observation",
        "evidence_source": evidence_source(source),
        "evidence_text": "Observed 12",
    }
    pending = prepare(runtime, "record_measurement", external, parameters, source)
    assert pending.status_code == 202, pending.data
    result = resolve(runtime, pending.data)
    assert result.status_code == 200, result.data
    assert effective_values(indicator)["current"] == 12
    assert (
        prepare(runtime, "record_measurement", external, parameters, source).data["code"] == "measurement_out_of_order"
    )
    parameters["measured_at"] = (timezone.now() + timedelta(days=1)).isoformat()
    assert prepare(runtime, "record_measurement", external, parameters, source).data["code"] == "measurement_in_future"
    evidence_id = result.data["created_ids"][0]
    risk = create(runtime[0], "risk", description="Exposure")
    risk_id = bind(runtime, risk, "RSK")
    reviewed = prepare(
        runtime,
        "review",
        risk_id,
        {"assessment": "Resolved with evidence", "evidence_id": evidence_id, "disposition": "resolved"},
    )
    assert reviewed.status_code == 202, reviewed.data
    assert resolve(runtime, reviewed.data).status_code == 200
    assert effective_values(risk)["status"] == "closed"


def test_authenticated_scope_and_source_cannot_be_supplied_by_payload(runtime):
    caps = runtime[1].get(endpoint(runtime, "capabilities"))
    assert caps.status_code == 200 and set(caps.data["definitions"]) == set(OPERATIONS)
    assert prepare(runtime, source=message(author="telegram:99")).status_code == 403
    assert prepare(runtime, actor_type="human").status_code == 400
    foreign = create(runtime[0], "indicator")
    query = runtime[1].post(
        endpoint(runtime, "query"),
        {"method": "read_entity", "parameters": {"entity_id": str(foreign.pk)}},
        format="json",
    )
    assert query.status_code == 404
    source = message()
    assert (
        prepare(
            runtime,
            parameters={
                "title": "Issue",
                "case_title": "Case",
                "evidence_title": "Evidence",
                "source": "model-invented",
            },
            source=source,
        ).data["code"]
        == "evidence_source_conflict"
    )


def test_actual_cos_http_adapter_prepares_and_replays(runtime):
    cos_source = os.environ.get("RADAR_COS_SOURCE")
    if not cos_source:
        pytest.skip("Set RADAR_COS_SOURCE to run the cross-repository contract test.")
    sys.path.insert(0, cos_source)
    import httpx
    from app.integrations.radar_commands import RadarCommandRuntime
    from app.observability import bind_correlation_context
    from app.security.radar_provenance import RadarMessageSource, bind_radar_source_context

    def transport(request):
        headers = {"HTTP_AUTHORIZATION": request.headers["authorization"]}
        if request.method == "GET":
            response = APIClient().get(request.url.path, **headers)
        else:
            response = APIClient().post(request.url.path, json.loads(request.content), format="json", **headers)
        return httpx.Response(response.status_code, json=response.data)

    adapter = RadarCommandRuntime(
        base_url="http://radar.test" + endpoint(runtime, "").rstrip("/") + "/",
        token=runtime[3],
        context="company:test",
        person_id=RuntimeObjectIdentity.objects.get(object=runtime[4]).external_id,
        allowed_tbox_versions=frozenset({"3.2.0"}),
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    source = RadarMessageSource.from_metadata(message(), text="Capture this issue")
    parameters = {
        "title": "CoS issue",
        "case_title": "CoS case",
        "evidence_title": "Telegram",
        "source": source.evidence_source(),
    }
    with bind_correlation_context(run_id=str(uuid4()), thread_id=str(uuid4())), bind_radar_source_context(source):
        prepared = adapter.prepare_operation("capture_issue", parameters, context="company:test", target_id=None)
    receipt = prepared["execution_context"]
    arguments = dict(
        context="company:test",
        target_id=None,
        expected_revision=prepared["expected_revision"],
        parameters=parameters,
        idempotency_key=receipt["idempotency_key"],
        execution_context=receipt,
        approval_source=message("sim", update=2),
    )
    first = adapter.execute_operation("capture_issue", **arguments)
    second = adapter.execute_operation("capture_issue", **arguments)
    assert first == second and first["code"] == "ok" and len(first["created_ids"]) == 3
    assert adapter.read_entity(first["target_id"], context="company:test")["metadata"]["title"] == "CoS issue"
    from plane.radar.models import RelationType

    action = create(runtime[0], "action", description="Deliver")
    execute(
        runtime[0],
        "LinkObjects",
        {
            "source_id": str(action.pk),
            "target_id": str(runtime[4].pk),
            "relation_type_id": str(RelationType.objects.get(workspace=runtime[0][3], key="owned_by").pk),
        },
    )
    action_id = bind(runtime, action, "ACT")
    indicator = create(runtime[0], "indicator")
    indicator_id = bind(runtime, indicator, "IND")
    document_id = next(pk for pk in first["created_ids"] if pk.startswith("DOC-"))
    operations = [
        (
            "delegate",
            action_id,
            {
                "executor_id": RuntimeObjectIdentity.objects.get(object=runtime[5]).external_id,
                "due_at": (timezone.now() + timedelta(days=2)).isoformat(),
            },
        ),
        (
            "record_measurement",
            indicator_id,
            {"value": 12, "measured_at": (timezone.now() - timedelta(hours=1)).isoformat(), "evidence_id": document_id},
        ),
        (
            "review",
            first["target_id"],
            {"assessment": "Resolved", "evidence_id": document_id, "disposition": "resolved"},
        ),
    ]
    for operation, target, params in operations:
        with bind_correlation_context(run_id=str(uuid4()), thread_id=str(uuid4())), bind_radar_source_context(source):
            pending = adapter.prepare_operation(operation, params, context="company:test", target_id=target)
        receipt = pending["execution_context"]
        done = adapter.execute_operation(
            operation,
            context="company:test",
            target_id=target,
            expected_revision=pending["expected_revision"],
            parameters=params,
            idempotency_key=receipt["idempotency_key"],
            execution_context=receipt,
            approval_source=message("sim", update=2),
        )
        assert done["code"] == "ok" and done["target_id"] == target
    from plane.radar.models import ObjectType

    common = {
        "command_name": "CreateObject",
        "command_version": 1,
        "idempotency_key": str(uuid4()),
        "expected_versions": {},
        "reason": "Shared catalog",
        "input": {
            "object_type_id": str(ObjectType.objects.get(workspace=runtime[0][3], key="objective").pk),
            "title": "CoS objective",
            "properties": {},
        },
        "assertion": {"kind": "asserted", "evidence_ids": []},
    }
    with bind_correlation_context(run_id=str(uuid4()), thread_id=str(uuid4())), bind_radar_source_context(source):
        pending_command = adapter.prepare_command(common)
    command_result = adapter.resolve_command(pending_command, approve=True, approval_source=message("sim", update=2))
    assert command_result["code"] == "ok" and len(command_result["created_ids"]) == 1
    adapter.close()


def test_ui_and_runtime_command_port_use_the_same_catalog(runtime):
    from plane.radar.models import ObjectType

    common_input = {
        "object_type_id": str(ObjectType.objects.get(workspace=runtime[0][3], key="objective").pk),
        "title": "Shared objective",
        "properties": {},
    }
    human = execute(runtime[0], "CreateObject", common_input)
    assert human["status"] == "executed"
    source = message()
    envelope = {
        "command_name": "CreateObject",
        "command_version": 1,
        "idempotency_key": str(uuid4()),
        "expected_versions": {},
        "reason": "Common command",
        "input": common_input,
        "assertion": {"kind": "asserted", "evidence_ids": []},
    }
    pending = runtime[1].post(
        endpoint(runtime, "commands/prepare"),
        {
            "envelope": envelope,
            "provenance": {
                "run_id": str(uuid4()),
                "correlation_id": str(uuid4()),
                "reason": "Common command",
                "source": source,
            },
        },
        format="json",
    )
    assert pending.status_code == 202, pending.data
    resolved = runtime[1].post(
        endpoint(runtime, "resolve"),
        {
            **{k: pending.data[k] for k in ("command_id", "intent_hash", "idempotency_key")},
            "approve": True,
            "rationale": "Confirmed",
            "source": message("sim", update=2),
        },
        format="json",
    )
    assert resolved.status_code == 200, resolved.data
    assert len(resolved.data["created_ids"]) == 1
    histories = Provenance.objects.filter(command_name="CreateObject", outcome="executed").values_list(
        "actor_type", flat=True
    )
    assert {"human", "agent"}.issubset(set(histories))


def test_commitment_identity_requires_its_mandatory_action(runtime):
    from rest_framework.exceptions import ValidationError
    from plane.radar.models import RelationType

    commitment = create(runtime[0], "commitment")
    with pytest.raises(ValidationError):
        bind(runtime, commitment, "CMT")
    action = create(runtime[0], "action", description="Deliver")
    bind(runtime, action, "ACT")
    result = execute(
        runtime[0],
        "LinkObjects",
        {
            "source_id": str(commitment.pk),
            "target_id": str(action.pk),
            "relation_type_id": str(RelationType.objects.get(workspace=runtime[0][3], key="commits_to").pk),
        },
    )
    bind(runtime, commitment, "CMT")
    with pytest.raises(ValidationError):
        execute(runtime[0], "UnlinkObjects", {"relation_id": result["data"]["relation"]["id"]})
    assert Relation.objects.filter(pk=result["data"]["relation"]["id"]).exists()


def test_human_collaboration_commands_are_not_advertised_to_runtime(runtime):
    from plane.radar.collaboration import COLLABORATION_COMMANDS

    ctx, api, credential, *_ = runtime
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type="agent",
        actor_id=credential.actor_id,
        delegator_id=ctx[0].pk,
        commands=[*OPERATIONS.values(), "LinkObjects", *sorted(COLLABORATION_COMMANDS)],
        object_types=["*"],
        fields=["*"],
    )
    response = api.get(endpoint(runtime, "capabilities"))
    assert response.status_code == 200
    assert not COLLABORATION_COMMANDS.intersection(response.data["commands"])
