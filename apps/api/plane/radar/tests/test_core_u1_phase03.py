"""Capability parity, complete effect authority, replanning and atomic execution."""

from dataclasses import replace
from uuid import UUID

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.commands.capabilities import CAPABILITIES, command_contracts, register, resolve, runtime_definitions
from plane.radar.commands.execution import execute_command, schema_fingerprint, CommandConflict, emit
from plane.radar.commands.inputs import INPUTS
from plane.radar.commands.operations import OPERATIONS
from plane.radar.models import (
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    Relation,
    DomainEvent,
    Provenance,
    CommandExecution,
    ActorGrant,
)
from plane.radar.workspace_schema import schema_revision
from .test_commands import create, execute, envelope, approved_agent, accept
from .test_core import url

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def ready(context):
    from plane.radar.commands import initialize_semantic_model

    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def counts():
    return tuple(
        model.objects.count() for model in (Object, PropertyValue, Relation, DomainEvent, Provenance, CommandExecution)
    )


@pytest.mark.parametrize("name", list(CAPABILITIES))
def test_every_registered_capability_has_one_input_handler_planner_and_contract(name):
    capability = CAPABILITIES[name]
    contract = command_contracts()[name]
    assert INPUTS[name] is capability.input_type
    assert set(contract["input"]) == set(INPUTS[name]().fields)
    assert callable(resolve(capability.handler)) and callable(resolve(capability.planner))
    assert contract["policy"]["independent_reviewer"] and contract["policy"]["agent_review_required"]
    if capability.runtime_operation:
        assert OPERATIONS[capability.runtime_operation] == name


def test_new_registration_reaches_session_runtime_and_execution_without_other_lists(ready, client, monkeypatch):
    ctx = ready
    capability = replace(CAPABILITIES["CreateObject"], name="PhaseThreeCreate")
    monkeypatch.setitem(CAPABILITIES, capability.name, capability)
    assert capability.name in INPUTS and capability.name in command_contracts(nonhuman=True)
    assert capability.name in client.get(url(ctx, "schema/")).data["capabilities"]
    kind = ObjectType.objects.get(workspace=ctx[3], key="objective")
    result = execute(ctx, capability.name, {"object_type_id": str(kind.pk), "title": "Registry extension"})
    assert (
        result["status"] == "executed"
        and Object.objects.get(pk=result["data"]["object"]["id"]).title == "Registry extension"
    )
    with pytest.raises(ValueError):
        register(capability)


def test_runtime_parameters_and_new_operations_are_generated_from_inputs(ready, monkeypatch):
    from plane.radar.api.runtime_views import PrepareInput

    c = replace(CAPABILITIES["CaptureIssue"], name="PhaseThreeCapture", runtime_operation="phase_three_capture")
    monkeypatch.setitem(CAPABILITIES, c.name, c)
    definitions = runtime_definitions(ready[3])
    for operation, name in OPERATIONS.items():
        expected = set(INPUTS[name]().fields) - {"context", CAPABILITIES[name].target_field}
        assert set(definitions[operation]["parameters"]) == expected
    assert c.runtime_operation in PrepareInput().fields["operation"].choices
    assert definitions["record_measurement"]["parameters"]["value"]["type"] == "number"
    actor = approved_agent(ready, "system", requires_approval=False)
    result = execute(
        ready,
        c.name,
        {
            "title": "Registered capture",
            "case_title": "Case",
            "evidence_title": "Evidence",
            "source": "pytest",
            "context": "company:test",
        },
        actor=actor,
    )
    assert result["status"] == "executed"
    assert Object.objects.count() == 3


def test_preview_is_symbolic_complete_and_does_not_persist_anything(ready, client):
    ctx = ready
    objective = create(ctx)
    data = {
        "title": "Compound risk",
        "description": "Delivery",
        "likelihood": 4,
        "impact": 5,
        "threatens_object_ids": [str(objective.pk)],
    }
    before = counts()
    response = client.post(
        url(ctx, "commands/preview/"),
        {
            "command_name": "RegisterRisk",
            "command_version": 1,
            "reason": "Plan risk",
            "input": data,
            "expected_schema_revision": schema_revision(ctx[3]),
        },
        format="json",
    )
    assert response.status_code == 200 and counts() == before
    plan = response.data["effect_plan"]
    assert response.data["expected_versions"] == {str(objective.pk): 1}
    assert plan["authority"]["object_types"] == ["objective", "risk"]
    assert plan["authority"]["commands"] == ["LinkObjects", "RegisterRisk"]
    assert {"score", "likelihood", "impact", "title", "content"} <= set(plan["authority"]["fields"])
    assert {"ObjectCreated", "RiskRegistered", "ObjectLinked"} <= {event["event_type"] for event in plan["events"]}
    assert all(change["id"].startswith("$new:") for change in plan["changes"] if change["before"] is None)


@pytest.mark.parametrize("missing", ["type", "relation", "derived"])
def test_partial_grant_cannot_authorize_only_part_of_a_compound_effect(ready, missing):
    ctx = ready
    objective = create(ctx)
    actor = approved_agent(ctx, "system", requires_approval=False)
    grant = ActorGrant.objects.get(actor_id=actor.actor_id)
    from .fixture_writes import fixture_write

    if missing == "type":
        fixture_write(lambda: ActorGrant.objects.filter(pk=grant.pk).update(object_types=["risk"]))
    elif missing == "relation":
        fixture_write(lambda: ActorGrant.objects.filter(pk=grant.pk).update(commands=["RegisterRisk"]))
    else:
        fields = list(
            PropertyDefinition.objects.filter(workspace=ctx[3], object_type__key="risk").values_list("key", flat=True)
        )
        fixture_write(
            lambda: ActorGrant.objects.filter(pk=grant.pk).update(
                fields=["title", "content", *[f for f in fields if f != "score"]]
            )
        )
    before = counts()
    with pytest.raises(PermissionDenied):
        execute(
            ctx,
            "RegisterRisk",
            {"title": "Denied risk", "description": "Delivery", "threatens_object_ids": [str(objective.pk)]},
            actor=actor,
        )
    assert counts() == before


def test_omitted_reference_declaration_is_still_discovered_from_actual_effects(ready, monkeypatch):
    ctx = ready
    person = create(ctx, "person")
    monkeypatch.setitem(CAPABILITIES, "CreateAction", replace(CAPABILITIES["CreateAction"], object_refs=()))
    data = {"title": "Owned action", "description": "Work", "owner_person_id": str(person.pk)}
    before = counts()
    with pytest.raises(ValidationError):
        execute(ctx, "CreateAction", data, versions={})
    assert counts() == before
    result = execute(ctx, "CreateAction", data, versions={str(person.pk): 1})
    assert result["versions_before"] == {str(person.pk): 1}
    assert Relation.objects.filter(source_id=result["data"]["object"]["id"], target=person).exists()


@pytest.mark.parametrize("extra", ["event", "field", "dependency"])
def test_effects_outside_the_plan_fail_atomically(ready, monkeypatch, extra):
    ctx = ready
    obj, other = create(ctx), create(ctx)
    capability = CAPABILITIES["UpdateObject"]
    original = resolve(capability.handler)
    calls = 0

    def unstable(workspace, data):
        nonlocal calls
        calls += 1
        result = original(workspace, data)
        if calls == 2:
            if extra == "event":
                emit("UnexpectedEvent", {"object_id": obj.pk})
            elif extra == "field":
                from plane.radar.commands.handlers import patch_object_properties
                from plane.radar.commands.queries import lookup_object

                patch_object_properties(workspace, lookup_object(workspace, obj.pk), {"description": "Unplanned"})
            else:
                from plane.radar.commands.queries import lookup_object

                lookup_object(workspace, other.pk)
        return result

    monkeypatch.setattr("plane.radar.commands.handlers._update", unstable)
    before = counts()
    with pytest.raises(CommandConflict) as error:
        execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Planned"}})
    assert error.value.detail["code"] == "effect_plan_conflict" and counts() == before
    obj.refresh_from_db()
    assert obj.title == "objective" and obj.version == 1


def test_review_detects_dependency_change_and_cannot_consume_old_approval(ready):
    ctx = ready
    objective = create(ctx)
    actor = approved_agent(ctx)
    request = envelope(
        ctx,
        "RegisterRisk",
        {"title": "Review risk", "description": "Delivery", "threatens_object_ids": [str(objective.pk)]},
        actor=actor,
    )
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    execute(ctx, "UpdateObject", {"object_id": str(objective.pk), "changes": {"title": "Changed dependency"}})
    before = counts()
    with pytest.raises(CommandConflict):
        accept(ctx, pending)
    assert counts() == before
    assert CommandExecution.objects.get(pk=pending["command_id"]).status == "pending_approval"


def test_registered_policy_change_invalidates_pending_review(ready, monkeypatch):
    ctx = ready
    actor = approved_agent(ctx)
    pending = execute(ctx, "RegisterRisk", {"title": "Review risk", "description": "Delivery"}, actor=actor)
    fingerprint = schema_fingerprint(ctx[3])
    monkeypatch.setitem(CAPABILITIES, "RegisterRisk", replace(CAPABILITIES["RegisterRisk"], human_only=True))
    assert schema_fingerprint(ctx[3]) != fingerprint
    with pytest.raises(CommandConflict) as error:
        accept(ctx, pending)
    assert error.value.detail["code"] == "approval_stale"


def test_confirmed_replay_uses_persisted_plan_and_current_grant_without_replanning(ready, monkeypatch):
    ctx = ready
    actor = approved_agent(ctx, "system", requires_approval=False)
    request = envelope(ctx, "RegisterRisk", {"title": "Replay risk", "description": "Delivery"}, actor=actor)
    result = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    ledger = CommandExecution.objects.get(pk=result["command_id"])
    assert ledger.envelope["effect_plan"]["contract"] == "transactional_effects_v1"
    monkeypatch.setattr(
        "plane.radar.commands.handlers._register_risk",
        lambda *a, **kw: pytest.fail("Confirmed replay must not execute"),
    )
    before = counts()
    assert execute_command(actor=actor, workspace=ctx[3], envelope=request) == result and counts() == before
    from .fixture_writes import fixture_write

    grant = ActorGrant.objects.get(actor_id=actor.actor_id)
    fixture_write(lambda: ActorGrant.objects.filter(pk=grant.pk).update(fields=["title"]))
    with pytest.raises(PermissionDenied):
        execute_command(actor=actor, workspace=ctx[3], envelope=request)


def test_human_only_minimums_are_not_weakened_by_a_nonhuman_grant(ready):
    actor = approved_agent(ready, "system", requires_approval=False)
    obj = create(ready)
    with pytest.raises(PermissionDenied):
        execute(ready, "AddComment", {"object_id": str(obj.pk), "body": "Forbidden"}, actor=actor)


@pytest.mark.parametrize("invalid", [True, "3", float("inf")])
def test_generated_numeric_contract_matches_measurement_validation(invalid):
    from plane.radar.commands.inputs import FiniteNumberField

    assert command_contracts()["RecordMeasurement"]["input"]["value"]["type"] == "number"
    with pytest.raises(ValidationError):
        FiniteNumberField().run_validation(invalid)


def test_preview_rejects_guests_stale_schema_unknown_commands_and_forged_actors(ready, client):
    ctx = ready
    obj = create(ctx)
    payload = {
        "command_name": "UpdateObject",
        "command_version": 1,
        "input": {"object_id": str(obj.pk), "changes": {"title": "Changed"}},
        "reason": "Preview",
        "expected_schema_revision": schema_revision(ctx[3]),
    }
    before = counts()
    assert (
        client.post(url(ctx, "commands/preview/"), {**payload, "actor_id": str(ctx[0].pk)}, format="json").status_code
        == 400
    )
    assert (
        client.post(url(ctx, "commands/preview/"), {**payload, "command_name": "Unknown"}, format="json").status_code
        == 400
    )
    assert (
        client.post(
            url(ctx, "commands/preview/"), {**payload, "expected_schema_revision": 0}, format="json"
        ).status_code
        == 409
    )
    from plane.db.models import WorkspaceMember

    WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=5)
    assert client.post(url(ctx, "commands/preview/"), payload, format="json").status_code == 403
    assert counts() == before


def test_preview_rejects_foreign_assertion_dependencies(ready, client):
    from uuid import uuid4

    ctx = ready
    obj = create(ctx)
    before = counts()
    response = client.post(
        url(ctx, "commands/preview/"),
        {
            "command_name": "UpdateObject",
            "command_version": 1,
            "reason": "Preview",
            "input": {"object_id": str(obj.pk), "changes": {"title": "Changed"}},
            "expected_schema_revision": schema_revision(ctx[3]),
            "evidence_ids": [str(uuid4())],
        },
        format="json",
    )
    assert response.status_code == 404 and counts() == before


def test_plans_preserve_caller_dates_and_include_private_payload_metadata(ready):
    import json
    from django.core.files.uploadedfile import SimpleUploadedFile
    from plane.radar.collaboration import prepare_upload

    ctx = ready
    obj = create(ctx, "action", description="Work")
    request = envelope(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"due_date": "2026-11-01"}})
    result = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request)
    plan = CommandExecution.objects.get(pk=result["command_id"]).envelope["effect_plan"]
    assert any(c["model"] == "radar.PropertyValue" and c["after"]["value"] == "2026-11-01" for c in plan["changes"])
    obj.refresh_from_db()
    upload = prepare_upload(SimpleUploadedFile("proof.txt", b"private payload proof"))
    request = envelope(ctx, "AddAttachment", {"object_id": str(obj.pk), **upload.metadata})
    result = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request, upload=upload)
    plan = CommandExecution.objects.get(pk=result["command_id"]).envelope["effect_plan"]
    assert plan["payloads"][0]["sha256"] == upload.metadata["sha256"]
    assert plan["payloads"][0]["size"] == upload.metadata["size"]
    assert "private payload proof" not in json.dumps(plan)
    assert command_contracts()["AddAttachment"]["transport"] == "multipart_upload"


def test_auxiliary_guard_dependencies_keep_versions_without_requiring_a_new_ui_write_map(ready):
    from plane.radar.commands.runtime_control import bind_runtime_object
    from plane.radar.commands.execution import preview_command
    from plane.radar.models import RelationType
    from .fixture_writes import fixture_write

    ctx = ready
    obj, target = create(ctx), create(ctx, "action", description="Work")
    relation = fixture_write(
        lambda: RelationType.objects.create(
            workspace=ctx[3],
            key="mandatory_guard_target",
            forward_label="requires",
            reverse_label="required by",
            source_types=["objective"],
            target_types=["action"],
            cardinality="1..1",
        )
    )
    execute(
        ctx,
        "LinkObjects",
        {"source_id": str(obj.pk), "target_id": str(target.pk), "relation_type_id": str(relation.pk)},
    )
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=target.pk, external_id="ACT-20261006-ABCDEF", context="company:test"
    )
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="OBJ-20261006-ABCDEF", context="company:test"
    )
    obj.refresh_from_db()
    target.refresh_from_db()
    data = {"object_id": str(obj.pk), "changes": {"title": "Existing UI write"}}
    preview = preview_command(
        actor=ctx[5], workspace=ctx[3], name="UpdateObject", data=data, expected_schema_revision=schema_revision(ctx[3])
    )
    assert preview["expected_versions"] == {str(obj.pk): obj.version, str(target.pk): target.version}
    assert preview["effect_plan"]["required_versions"] == {str(obj.pk): obj.version}
    result = execute(ctx, "UpdateObject", data, versions={str(obj.pk): obj.version})
    assert result["versions_before"] == preview["expected_versions"]
    obj.refresh_from_db()
    actor = approved_agent(ctx)
    request = envelope(
        ctx,
        "UpdateObject",
        {"object_id": str(obj.pk), "changes": {"title": "Review auxiliary dependency"}},
        actor=actor,
    )
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    accept(ctx, pending)
    execute(ctx, "UpdateObject", {"object_id": str(target.pk), "changes": {"title": "Guard dependency changed"}})
    before = counts()
    with pytest.raises(CommandConflict) as error:
        execute_command(
            actor=replace(actor, approval_id=UUID(pending["approval_id"])), workspace=ctx[3], envelope=request
        )
    assert error.value.detail["code"] == "approval_stale" and counts() == before


def test_collaboration_operational_reads_retire_with_an_inactive_type(ready, client):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from plane.radar.commands.schema import update_metadata

    ctx = ready
    obj = create(ctx)
    request = client.post(
        url(ctx, f"objects/{obj.pk}/attachments/"),
        {"file": SimpleUploadedFile("proof.txt", b"proof")},
        HTTP_X_RADAR_EXPECTED_VERSIONS='{"%s": %s}' % (obj.pk, obj.version),
        HTTP_IDEMPOTENCY_KEY="retire-proof",
    )
    assert request.status_code == 200
    item_id = request.data["data"]["item_id"]
    update_metadata(
        actor=ctx[5],
        workspace=ctx[3],
        group="types",
        definition_id=obj.object_type_id,
        patch={"is_active": False},
        expected_revision=schema_revision(ctx[3]),
    )
    before = counts()
    assert client.get(url(ctx, f"objects/{obj.pk}/collaboration/")).status_code == 404
    assert client.get(url(ctx, f"objects/{obj.pk}/attachments/{item_id}/download/")).status_code == 404
    assert (
        client.post(
            url(ctx, f"objects/{obj.pk}/attachments/"), {"file": SimpleUploadedFile("new.txt", b"new")}
        ).status_code
        == 404
    )
    assert client.get(url(ctx, f"objects/{obj.pk}/provenance/")).status_code == 200
    assert counts() == before
