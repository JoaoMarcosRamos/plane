from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from plane.db.models import WorkspaceMember
from plane.radar.commands import (
    configure_person_identity,
    create_object,
    execute_command,
    initialize_semantic_model,
    register_actor_grant,
    review_command,
    set_property_value,
)
from plane.radar.commands.actor import Actor
from plane.radar.commands.execution import CommandConflict
from plane.radar.commands.handlers import references
from plane.radar.commands.inputs import INPUTS
from plane.radar.models import (
    ActionCompletion,
    ActorGrant,
    CommandApproval,
    CommandExecution,
    DecisionApproval,
    DomainEvent,
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    Provenance,
    Relation,
)
from plane.radar.mutation import current_mutation
from .test_core import url
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def ready(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def envelope(ctx, name, data, *, actor=None, key=None, versions=None, assertion=None):
    actor = actor or ctx[5]
    parsed = INPUTS[name](data=data)
    parsed.is_valid(raise_exception=True)
    refs = references(ctx[3], name, parsed.validated_data)
    assertion = assertion or {"kind": "asserted", "evidence_ids": []}
    refs.update(UUID(str(pk)) for pk in assertion["evidence_ids"])
    if versions is None:
        versions = {str(obj.pk): obj.version for obj in Object.objects.filter(pk__in=refs)}
    return {
        "command_name": name,
        "command_version": 1,
        "workspace_id": str(ctx[3].pk),
        "idempotency_key": key or str(uuid4()),
        "expected_versions": versions,
        "reason": actor.reason,
        "input": data,
        "assertion": assertion,
    }


def execute(ctx, name, data, *, actor=None, **kwargs):
    return execute_command(
        actor=actor or ctx[5], workspace=ctx[3], envelope=envelope(ctx, name, data, actor=actor, **kwargs)
    )


def create(ctx, key="objective", **properties):
    return create_object(
        actor=ctx[5],
        workspace=ctx[3],
        object_type=ObjectType.objects.get(workspace=ctx[3], key=key).pk,
        title=key,
        properties=properties,
    )


def approved_agent(ctx, actor_type="agent", requires_approval=True):
    actor = Actor(
        actor_type=actor_type,
        actor_id=uuid4(),
        run_id=uuid4(),
        on_behalf_of=ctx[0].pk,
        reason="Review risk",
        source="test.adapter",
        correlation_id=uuid4(),
        confidence=0.8,
    )
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type=actor_type,
        actor_id=actor.actor_id,
        delegator_id=ctx[0].pk,
        commands=[name for name in INPUTS if name != "ApproveDecision"],
        object_types=["*"],
        fields=["*"],
        requires_approval=requires_approval,
    )
    return actor


def accept(ctx, pending):
    execution = CommandExecution.objects.get(pk=pending["command_id"])
    return review_command(
        actor=replace(ctx[5], actor_id=ctx[1].pk),
        workspace=ctx[3],
        command_id=execution.pk,
        intent_hash=execution.intent_hash,
        approve=True,
        rationale="Reviewed exact effects and evidence",
    )


def decision_with_evidence(ctx):
    decision = create(
        ctx,
        "decision",
        context="Sandbox governance",
        decision="Use enterprise licenses",
        rationale="Centralized control",
    )
    evidence = execute(
        ctx,
        "AddEvidence",
        {
            "target_id": str(decision.pk),
            "relation_key": "informed_by",
            "document": {"title": "License assessment", "content": "<p>Reviewed options</p>", "source_system": "local"},
        },
    )
    person = create(ctx, "person")
    configure_person_identity(actor=ctx[5], workspace=ctx[3], user_id=ctx[1].pk, person_id=person.pk, can_approve=True)
    return decision, Object.objects.get(pk=evidence["data"]["document_id"]), person


def test_all_mutations_capture_complete_provenance_and_atomic_events(ready):
    ctx = ready
    objective = create(ctx)
    result = execute(
        ctx,
        "RegisterRisk",
        {
            "title": "License delay",
            "description": "Contract may be late",
            "likelihood": 4,
            "impact": 5,
            "threatens_object_ids": [str(objective.pk)],
        },
    )
    risk = Object.objects.get(pk=result["data"]["object"]["id"])
    assert risk.version == 1
    assert PropertyValue.objects.get(object=risk, definition__key="score").value == 20
    provenance = Provenance.objects.get(pk=result["provenance_id"])
    assert provenance.actor_type == "human" and provenance.actor_id == ctx[0].pk
    assert provenance.reason == ctx[5].reason and provenance.source == ctx[5].source
    assert provenance.timestamp.tzinfo and provenance.correlation_id == ctx[5].correlation_id
    assert provenance.run_id is provenance.approval_id is provenance.confidence is None
    assert risk.created_provenance_id == risk.last_provenance_id == provenance.pk
    edge = Relation.objects.get(source=risk, target=objective)
    assert edge.created_provenance_id == provenance.pk
    assert all(item.last_provenance_id == provenance.pk for item in PropertyValue.objects.filter(object=risk))
    events = DomainEvent.objects.filter(execution_id=result["command_id"])
    assert set(events.values_list("event_type", flat=True)) == {"ObjectCreated", "RiskRegistered", "ObjectLinked"}
    assert all(event.provenance_id == provenance.pk and event.published_at is None for event in events)
    objective.refresh_from_db()
    assert objective.version == 2


def test_agent_pending_accept_execute_preserves_both_actors_and_is_idempotent(ready):
    ctx = ready
    actor = approved_agent(ctx)
    request = envelope(
        ctx,
        "RegisterRisk",
        {"title": "Delay", "description": "Hypothesis"},
        actor=actor,
        assertion={"kind": "inferred", "confidence": 0.8, "evidence_ids": []},
    )
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    assert pending["status"] == "pending_approval" and not Object.objects.exists()
    preview = pending["data"]["effect_plan"]
    assert preview["preview_only"] is True
    assert any(change["id"].startswith("$new:radar.Object:") for change in preview["changes"])
    assert any(event["event_type"] == "RiskRegistered" for event in preview["events"])
    assert execute_command(actor=actor, workspace=ctx[3], envelope=request) == pending
    assert not DomainEvent.objects.filter(event_type="RiskRegistered").exists()
    approval = accept(ctx, pending)
    authorized = replace(actor, approval_id=approval.pk)
    result = execute_command(actor=authorized, workspace=ctx[3], envelope=request)
    assert result["status"] == "executed"
    provenance = Provenance.objects.get(pk=result["provenance_id"])
    assert provenance.actor_type == "agent" and provenance.actor_id == actor.actor_id
    assert provenance.confidence == 0.8 and provenance.run_id == actor.run_id
    assert provenance.approval_id == approval.pk and provenance.context["approver_id"] == str(ctx[1].pk)
    assert provenance.context["assertion"]["kind"] == "inferred"
    assert provenance.context["initiator"]["actor_id"] == str(actor.actor_id)
    assert (
        provenance.context["schema_hash"]
        == CommandExecution.objects.get(pk=result["command_id"]).envelope["schema_hash"]
    )
    assert Object.objects.get(pk=result["data"]["object"]["id"]).created_by_id is None
    approval.refresh_from_db()
    assert approval.status == "consumed"
    assert execute_command(actor=authorized, workspace=ctx[3], envelope=request) == result
    assert Object.objects.count() == 1 and DomainEvent.objects.filter(event_type="RiskRegistered").count() == 1


@pytest.mark.parametrize("actor_type", ["agent", "system", "integration"])
def test_nonhuman_requires_explicit_grant_and_records_principal_when_permitted(ready, actor_type):
    ctx = ready
    actor = Actor(
        actor_type=actor_type,
        actor_id=uuid4(),
        reason="Scheduled capture",
        source="trusted.adapter",
        correlation_id=uuid4(),
        run_id=uuid4(),
    )
    request = envelope(
        ctx,
        "CreateObject",
        {"object_type_id": str(ObjectType.objects.get(key="objective").pk), "title": "Capture"},
        actor=actor,
    )
    with pytest.raises(PermissionDenied):
        execute_command(actor=actor, workspace=ctx[3], envelope=request)
    actor = approved_agent(ctx, actor_type, requires_approval=False)
    request["reason"] = actor.reason
    pending_or_result = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    if actor_type == "agent":
        approval = accept(ctx, pending_or_result)
        actor = replace(actor, approval_id=approval.pk)
        result = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    else:
        result = pending_or_result
    assert Provenance.objects.get(pk=result["provenance_id"]).actor_type == actor_type


def test_decision_approval_taken_action_and_completion_workflow(ready):
    ctx = ready
    decision, document, person = decision_with_evidence(ctx)
    reviewer = replace(ctx[5], actor_id=ctx[1].pk)
    vote = execute(
        ctx,
        "ApproveDecision",
        {"decision_id": str(decision.pk), "rationale": "Fits governance", "approver_person_id": str(person.pk)},
        actor=reviewer,
    )
    decision.refresh_from_db()
    assert PropertyValue.objects.get(object=decision, definition__key="status").value == "proposed"
    approval = DecisionApproval.objects.get(pk=vote["data"]["decision_approval_id"])
    assert approval.resulting_version == decision.version and not approval.is_stale
    taken = execute(
        ctx, "UpdateObject", {"object_id": str(decision.pk), "set_properties": {"status": "decided"}}, actor=reviewer
    )
    assert DomainEvent.objects.filter(execution_id=taken["command_id"], event_type="DecisionTaken").exists()
    result = execute(
        ctx,
        "CreateAction",
        {
            "title": "Negotiate",
            "description": "Obtain license agreement",
            "origin_decision_id": str(decision.pk),
            "owner_person_id": str(person.pk),
            "executor_person_ids": [str(person.pk)],
        },
    )
    action = Object.objects.get(pk=result["data"]["object"]["id"])
    assert action.version == 1
    attachment = execute(
        ctx,
        "AddEvidence",
        {
            "target_id": str(action.pk),
            "relation_key": "verifies",
            "document": {"title": "Agreement", "source_system": "local", "content": "<p>Signed agreement</p>"},
        },
    )
    proof = Object.objects.get(pk=attachment["data"]["document_id"])
    request = envelope(
        ctx,
        "CompleteAction",
        {"action_id": str(action.pk), "evidence_id": str(proof.pk), "outcome": "Agreement signed"},
    )
    complete = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request)
    assert PropertyValue.objects.get(object=action, definition__key="status").value == "done"
    record = ActionCompletion.objects.get(action=action)
    assert record.outcome == "Agreement signed" and record.completed_at.tzinfo
    assert execute_command(actor=ctx[5], workspace=ctx[3], envelope=request) == complete
    edge = Relation.objects.get(source=proof, target=action, relation_type__key="verifies")
    with pytest.raises(PermissionDenied):
        execute(ctx, "UnlinkObjects", {"relation_id": str(edge.pk)})
    with pytest.raises(ValidationError):
        execute(ctx, "UpdateObject", {"object_id": str(proof.pk), "changes": {"content": "Changed"}})
    with pytest.raises(ValidationError):
        execute(
            ctx, "UpdateObject", {"object_id": str(decision.pk), "set_properties": {"decision": "Different choice"}}
        )
    assert document.pk != proof.pk


def test_generic_writers_cannot_bypass_specialized_guards(ready):
    ctx = ready
    with pytest.raises(ValidationError):
        create(ctx, "action")
    action = create(ctx, "action", description="Work")
    selected = PropertyDefinition.objects.get(object_type=action.object_type, key="status")
    with pytest.raises(ValidationError):
        set_property_value(actor=ctx[5], workspace=ctx[3], object_id=action.pk, definition_id=selected.pk, value="done")
    with pytest.raises(ValidationError):
        execute(
            ctx, "CompleteAction", {"action_id": str(action.pk), "evidence_id": str(action.pk), "outcome": "No proof"}
        )
    decision = create(ctx, "decision", context="Scope", decision="Choice", rationale="Reason")
    person = create(ctx, "person")
    from plane.radar.models import RelationType

    with pytest.raises(PermissionDenied):
        execute(
            ctx,
            "LinkObjects",
            {
                "source_id": str(decision.pk),
                "target_id": str(person.pk),
                "relation_type_id": str(RelationType.objects.get(key="made_by").pk),
            },
        )
    actor = approved_agent(ctx)
    with pytest.raises(PermissionDenied):
        execute(
            ctx, "UpdateObject", {"object_id": str(decision.pk), "set_properties": {"status": "decided"}}, actor=actor
        )
    with pytest.raises(PermissionDenied):
        execute(
            ctx,
            "ApproveDecision",
            {"decision_id": str(decision.pk), "approver_person_id": str(person.pk), "rationale": "Impersonation"},
            actor=actor,
        )


def test_stale_revision_modified_intent_and_approval_expiry_do_not_write(ready):
    ctx = ready
    obj = create(ctx)
    actor = approved_agent(ctx)
    request = envelope(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Agent edit"}}, actor=actor)
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    approval = accept(ctx, pending)
    execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Human edit"}})
    with pytest.raises(CommandConflict):
        execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    changed = {**request, "input": {"object_id": str(obj.pk), "changes": {"title": "Different payload"}}}
    with pytest.raises(CommandConflict):
        execute_command(actor=actor, workspace=ctx[3], envelope=changed)
    request = envelope(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Expired"}}, actor=actor)
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    approval = accept(ctx, pending)
    fixture_write(
        lambda: CommandApproval.all_objects.filter(pk=approval.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
    )
    with pytest.raises(CommandConflict):
        execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    obj.refresh_from_db()
    assert obj.title == "Human edit"


def test_grant_revocation_scope_and_policy_changes_are_enforced(ready):
    ctx = ready
    actor = approved_agent(ctx)
    request = envelope(ctx, "RegisterRisk", {"title": "Risk", "description": "Hypothesis"}, actor=actor)
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    approval = accept(ctx, pending)
    grant = ActorGrant.objects.get(actor_id=actor.actor_id)
    fixture_write(lambda: ActorGrant.all_objects.filter(pk=grant.pk).update(policy_version=2))
    with pytest.raises(CommandConflict):
        execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    fixture_write(lambda: ActorGrant.all_objects.filter(pk=grant.pk).update(object_types=["objective"]))
    with pytest.raises(PermissionDenied):
        execute_command(actor=actor, workspace=ctx[3], envelope={**request, "idempotency_key": str(uuid4())})
    fixture_write(lambda: ActorGrant.all_objects.filter(pk=grant.pk).update(is_active=False))
    with pytest.raises(PermissionDenied):
        execute_command(actor=actor, workspace=ctx[3], envelope=request)
    assert not Object.objects.exists()


def test_failure_rolls_back_domain_provenance_outbox_and_context(ready):
    ctx = ready
    before = (
        Object.objects.count(),
        Provenance.objects.count(),
        DomainEvent.objects.count(),
        CommandExecution.objects.count(),
    )
    with patch.object(DomainEvent.objects, "create", side_effect=IntegrityError("Outbox unavailable")):
        with pytest.raises(IntegrityError):
            execute(ctx, "RegisterRisk", {"title": "Rollback", "description": "Must not survive"})
    assert (
        Object.objects.count(),
        Provenance.objects.count(),
        DomainEvent.objects.count(),
        CommandExecution.objects.count(),
    ) == before
    assert current_mutation.get() is None
    result = execute(ctx, "RegisterRisk", {"title": "Retry", "description": "Now available"})
    assert result["status"] == "executed"


def test_final_patch_validates_dates_atomically_and_noop_emits_no_fact(ready):
    ctx = ready
    obj = create(ctx, start_date="2026-10-01", due_date="2026-10-02")
    result = execute(
        ctx,
        "UpdateObject",
        {"object_id": str(obj.pk), "set_properties": {"start_date": "2026-11-01", "due_date": "2026-11-02"}},
    )
    assert result["data"]["object"]["version"] == 2
    noop = execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": obj.title}})
    assert noop["status"] == "noop" and noop["event_ids"] == []
    assert Provenance.objects.get(pk=noop["provenance_id"]).outcome == "noop"


def test_api_same_layer_provenance_forgery_and_required_snapshot(ready, client):
    ctx = ready
    request = envelope(ctx, "RegisterRisk", {"title": "API risk", "description": "Captured by session"})
    result = client.post(url(ctx, "commands/"), request, format="json")
    assert result.status_code == 200 and result.data["status"] == "executed"
    obj = Object.objects.get(pk=result.data["data"]["object"]["id"])
    records = client.get(url(ctx, f"objects/{obj.pk}/provenance/"))
    assert records.status_code == 200 and records.data[-1]["actor_type"] == "human"
    assert records.data[-1]["source"] == "radar.session-api"
    forged = {**request, "idempotency_key": str(uuid4()), "actor_type": "system", "actor_id": str(uuid4())}
    assert client.post(url(ctx, "commands/"), forged, format="json").status_code == 400
    assert (
        client.post(
            url(ctx, "objects/"), {"object_type": str(obj.object_type_id), "title": 42}, format="json"
        ).status_code
        == 400
    )
    bare = APIClient()
    bare.force_authenticate(ctx[0])
    assert bare.patch(url(ctx, f"objects/{obj.pk}/"), {"title": "No snapshot"}, format="json").status_code == 400
    WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=5)
    assert client.post(url(ctx, "commands/"), request, format="json").status_code == 403


def test_cross_workspace_and_independent_approver_enforced(ready):
    ctx = ready
    decision, document, person = decision_with_evidence(ctx)
    configure_person_identity(
        actor=ctx[5], workspace=ctx[3], user_id=ctx[0].pk, person_id=create(ctx, "person").pk, can_approve=True
    )
    own_person = person_identity_for(ctx, ctx[0].pk)
    with pytest.raises(PermissionDenied):
        execute(
            ctx,
            "ApproveDecision",
            {"decision_id": str(decision.pk), "approver_person_id": str(own_person), "rationale": "Self approval"},
        )
    with pytest.raises(PermissionDenied):
        execute(
            ctx,
            "ApproveDecision",
            {"decision_id": str(decision.pk), "approver_person_id": str(person.pk), "rationale": "Fake identity"},
        )
    WorkspaceMember.objects.create(workspace=ctx[4], member=ctx[0], role=15)
    foreign = envelope(
        ctx,
        "CompleteAction",
        {"action_id": str(decision.pk), "evidence_id": str(document.pk), "outcome": "Wrong scope"},
    )
    foreign.pop("workspace_id")
    with pytest.raises(NotFound):
        execute_command(actor=ctx[5], workspace=ctx[4], envelope=foreign)


def test_schema_default_change_invalidates_review_and_execution(ready):
    ctx = ready
    actor = approved_agent(ctx)
    request = envelope(ctx, "RegisterRisk", {"title": "Delay", "description": "Hypothesis"}, actor=actor)
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    default = PropertyDefinition.objects.get(workspace=ctx[3], object_type__key="risk", key="likelihood")
    original = default.config.copy()
    default.config = {**original, "default": 4}
    fixture_write(lambda: default.save())
    with pytest.raises(CommandConflict):
        accept(ctx, pending)
    default.config = original
    fixture_write(lambda: default.save())
    approval = accept(ctx, pending)
    default.config = {**original, "default": 5}
    fixture_write(lambda: default.save())
    with pytest.raises(CommandConflict):
        execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    assert not Object.objects.exists()
    approval.refresh_from_db()
    assert approval.status == "approved"


def test_generic_specialized_creation_checks_embedded_reference_versions_and_scope(ready):
    ctx = ready
    person = create(ctx, "person")
    kind = ObjectType.objects.get(workspace=ctx[3], key="action")
    data = {
        "object_type_id": str(kind.pk),
        "title": "Follow up",
        "properties": {
            "description": "Review",
            "owner_person_id": str(person.pk),
        },
    }
    with pytest.raises(ValidationError):
        execute(ctx, "CreateObject", data, versions={})
    actor = approved_agent(ctx)
    grant = ActorGrant.objects.get(actor_id=actor.actor_id)
    grant.object_types = ["action"]
    fixture_write(lambda: grant.save())
    with pytest.raises(PermissionDenied):
        execute(ctx, "CreateObject", data, actor=actor)
    assert Object.objects.count() == 1 and not Relation.objects.exists()


@pytest.mark.parametrize("field,value", [("title", 42), ("description", True)])
def test_text_inputs_do_not_coerce_nontext(ready, field, value):
    data = {"title": "Delay", "description": "Hypothesis", field: value}
    with pytest.raises(ValidationError):
        execute(ready, "RegisterRisk", data)
    assert not Object.objects.exists()


def test_observation_timestamp_requires_explicit_timezone(ready):
    action = create(ready, "action", description="Follow up")
    with pytest.raises(ValidationError):
        execute(
            ready,
            "AddEvidence",
            {
                "target_id": str(action.pk),
                "relation_key": "verifies",
                "document": {"title": "Result", "content": "Done", "source_system": "local"},
                "observed_at": "2026-01-01T10:00:00",
            },
        )
    assert Object.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_command_key_commits_once(ready):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections
    from plane.db.models import Workspace

    ctx = ready
    request = envelope(ctx, "RegisterRisk", {"title": "Delay", "description": "Hypothesis"})
    barrier = Barrier(2)

    def write(_):
        close_old_connections()
        try:
            workspace = Workspace.objects.get(pk=ctx[3].pk)
            barrier.wait(timeout=10)
            return execute_command(actor=ctx[5], workspace=workspace, envelope=request)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert results[0] == results[1]
    assert Object.objects.count() == 1
    assert CommandExecution.objects.count() == 1
    assert DomainEvent.objects.filter(event_type="RiskRegistered").count() == 1


def person_identity_for(ctx, user_id):
    from plane.radar.models import PersonIdentity

    return PersonIdentity.objects.get(workspace=ctx[3], user_id=user_id).person_id
