from dataclasses import replace
from uuid import uuid4
from pathlib import Path

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.db.models import WorkspaceMember
from plane.radar.commands import create_object, execute_command, initialize_semantic_model, register_actor_grant
from plane.radar.commands.actor import Actor
from plane.radar.commands.control import review_command
from plane.radar.commands.execution import CommandConflict, run_internal, schema_fingerprint
from plane.radar.commands import primitives_semantic
from plane.radar.commands.runtime_control import bind_runtime_object
from plane.radar.models import (
    CommandExecution,
    DomainEvent,
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    Provenance,
    RelationType,
)
from plane.radar.mutation import current_mutation
from .test_commands import approved_agent, create, envelope, execute

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def ready(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def schema_write(ctx, operation):
    return run_internal(actor=ctx[5], workspace=ctx[3], name="TestSchemaConfiguration", operation=operation)


def custom_type(ctx, *, rules=None, keys=None):
    def operation():
        selected = ObjectType.objects.create(workspace=ctx[3], key="custom", name="Custom", rules=rules or {})
        for key, kind, default in keys or []:
            PropertyDefinition.objects.create(
                workspace=ctx[3],
                object_type=selected,
                key=key,
                name=key,
                value_type=kind,
                config={"default": default},
            )
        return selected

    return schema_write(ctx, operation)


def test_names_from_risk_and_decision_are_not_globally_reserved(ready):
    ctx = ready
    selected = custom_type(
        ctx,
        keys=[
            ("score", "integer", 0),
            ("likelihood", "integer", 0),
            ("impact", "integer", 0),
            ("decided_at", "string", ""),
            ("status", "string", "decided"),
        ],
    )
    obj = create_object(
        actor=ctx[5], workspace=ctx[3], object_type=selected.pk, title="Custom", properties={"score": 99}
    )
    actor = Actor(
        actor_type="integration", actor_id=uuid4(), reason="Custom update", source="test", correlation_id=uuid4()
    )
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        delegator_id=ctx[0].pk,
        commands=["UpdateObject"],
        object_types=["custom"],
        fields=["likelihood", "impact", "decided_at", "status"],
        requires_approval=False,
    )
    result = execute(
        ctx,
        "UpdateObject",
        {
            "object_id": str(obj.pk),
            "set_properties": {"likelihood": 7, "impact": 3, "decided_at": "local", "status": "decided"},
        },
        actor=actor,
    )
    assert result["status"] == "executed"
    assert primitives_semantic.effective_values(obj)["score"] == 99
    assert primitives_semantic.effective_values(obj)["decided_at"] == "local"


@pytest.mark.parametrize("path", ["command", "primitive"])
def test_multi_factor_workspace_rule_is_shared_by_writers(ready, path):
    ctx = ready
    selected = custom_type(
        ctx,
        rules={"invariants": [{"kind": "product", "result": "total", "factors": ["a", "b", "c"]}]},
        keys=[("a", "integer", 2), ("b", "integer", 3), ("c", "integer", 4), ("total", "integer", 0)],
    )
    obj = create_object(actor=ctx[5], workspace=ctx[3], object_type=selected.pk, title="Product")
    assert primitives_semantic.effective_values(obj)["total"] == 24
    if path == "command":
        result = execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"a": 5, "b": 6}})
        assert result["status"] == "executed"
    else:
        definition = PropertyDefinition.objects.get(object_type=selected, key="a")
        schema_write(
            ctx,
            lambda: primitives_semantic.set_property_value(
                actor=ctx[5],
                workspace=ctx[3],
                object_id=obj.pk,
                definition_id=definition.pk,
                value=10,
            ),
        )
    obj.refresh_from_db()
    assert obj.version == 2
    assert primitives_semantic.effective_values(obj)["total"] == 120
    assert obj.last_provenance_id is not None


def test_derived_authority_follows_workspace_rule_keys(ready):
    ctx = ready
    selected = custom_type(
        ctx,
        rules={"invariants": [{"kind": "product", "result": "total", "factors": ["a", "b"]}]},
        keys=[("a", "integer", 2), ("b", "integer", 3), ("total", "integer", 0)],
    )
    obj = create_object(actor=ctx[5], workspace=ctx[3], object_type=selected.pk, title="Product")
    actor = Actor(
        actor_type="integration", actor_id=uuid4(), reason="Restricted", source="test", correlation_id=uuid4()
    )
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type="integration",
        actor_id=actor.actor_id,
        delegator_id=ctx[0].pk,
        commands=["UpdateObject"],
        object_types=["custom"],
        fields=["a"],
        requires_approval=False,
    )
    with pytest.raises(PermissionDenied):
        execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"a": 4}}, actor=actor)
    assert primitives_semantic.effective_values(obj)["total"] == 6


def test_invalid_batch_rolls_back_values_versions_events_and_provenance(ready):
    ctx = ready
    obj = create(ctx)
    counts = (Provenance.objects.count(), DomainEvent.objects.count())
    with pytest.raises(ValidationError):
        execute(
            ctx,
            "UpdateObject",
            {
                "object_id": str(obj.pk),
                "changes": {"title": "Must roll back"},
                "set_properties": {"start_date": "2026-10-06", "due_date": "2026-10-05"},
            },
        )
    obj.refresh_from_db()
    assert obj.title == "objective" and obj.version == 1
    assert counts == (Provenance.objects.count(), DomainEvent.objects.count())


@pytest.mark.parametrize(
    "rules",
    [
        {"script": "unsafe"},
        {"invariants": [{"kind": "unknown"}]},
        {"invariants": [{"kind": "product", "result": "a", "factors": ["a", "b"]}]},
        {"invariants": [{"kind": "product", "result": "c", "factors": ["a"]}]},
    ],
)
def test_rule_contract_rejects_unknown_or_invalid_operators(ready, rules):
    with pytest.raises(ValidationError):
        custom_type(ready, rules=rules)
    assert not ObjectType.objects.filter(key="custom").exists()


@pytest.mark.parametrize("when", ["before_review", "after_review"])
@pytest.mark.parametrize("change", ["implementation", "implementation_bytes", "metadata"])
def test_pending_approval_is_bound_to_effective_rules(ready, monkeypatch, when, change):
    ctx = ready
    obj = create(ctx, "risk", description="Risk")
    actor = approved_agent(ctx)
    request = envelope(
        ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"likelihood": 4}}, actor=actor
    )
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    execution = CommandExecution.objects.get(pk=pending["command_id"])
    from plane.radar.commands.rules import RULES_REVISION

    assert execution.envelope["rules_contract"]["revision"] == RULES_REVISION
    assert "rules_contract" in Provenance.objects.get(pk=pending["provenance_id"]).context
    if when == "after_review":
        approval = review_command(
            actor=replace(ctx[5], actor_id=ctx[1].pk),
            workspace=ctx[3],
            command_id=execution.pk,
            intent_hash=execution.intent_hash,
            approve=True,
            rationale="Review",
        )
    old_hash = schema_fingerprint(ctx[3])
    if change == "implementation":
        monkeypatch.setattr("plane.radar.commands.rules.RULES_REVISION", "next-release")
    elif change == "implementation_bytes":
        original = Path.read_bytes

        def revised_source(path):
            content = original(path)
            return content + b"\n# changed guard implementation" if path.name == "handlers.py" else content

        monkeypatch.setattr(Path, "read_bytes", revised_source)
    else:
        selected = ObjectType.objects.get(pk=obj.object_type_id)
        selected.rules = {}
        schema_write(ctx, selected.save)
    assert old_hash != schema_fingerprint(ctx[3])
    with pytest.raises(CommandConflict) as caught:
        if when == "before_review":
            review_command(
                actor=replace(ctx[5], actor_id=ctx[1].pk),
                workspace=ctx[3],
                command_id=execution.pk,
                intent_hash=execution.intent_hash,
                approve=True,
                rationale="Review",
            )
        else:
            execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    assert caught.value.detail["code"] == "approval_stale"
    obj.refresh_from_db()
    assert obj.version == 1


def mandatory_relation(ctx, source_key="objective"):
    return schema_write(
        ctx,
        lambda: RelationType.objects.create(
            workspace=ctx[3],
            key="mandatory",
            forward_label="requires",
            reverse_label="required_by",
            source_types=[source_key],
            target_types=["action"],
            cardinality="1..1",
        ),
    )


def test_mandatory_relation_allows_assembly_but_guards_activation_and_binding(ready):
    ctx = ready
    kind = mandatory_relation(ctx)
    obj = create(ctx)
    action = create(ctx, "action", description="Work")
    with pytest.raises(ValidationError):
        execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"status": "active"}})
    with pytest.raises(ValidationError):
        bind_runtime_object(
            actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="OBJ-20261005-ABCDEF", context="company:test"
        )
    edge = execute(
        ctx, "LinkObjects", {"source_id": str(obj.pk), "target_id": str(action.pk), "relation_type_id": str(kind.pk)}
    )
    # Relation exists, but binding additionally needs an authorized same-context target.
    with pytest.raises(ValidationError):
        bind_runtime_object(
            actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="OBJ-20261005-ABCDEF", context="company:test"
        )
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=action.pk, external_id="ACT-20261005-ABCDEF", context="company:test"
    )
    binding = bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="OBJ-20261005-ABCDEF", context="company:test"
    )
    assert binding.object_id == obj.pk
    execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"status": "active"}})
    with pytest.raises(ValidationError):
        execute(ctx, "UnlinkObjects", {"relation_id": edge["data"]["relation"]["id"]})
    second = create(ctx, "action", description="Other")
    with pytest.raises(ValidationError):
        execute(
            ctx,
            "LinkObjects",
            {"source_id": str(obj.pk), "target_id": str(second.pk), "relation_type_id": str(kind.pk)},
        )


@pytest.mark.parametrize("manager", ["objects", "all_objects"])
@pytest.mark.parametrize("operation", ["save", "create", "update", "bulk_create", "bulk_update", "pointer"])
def test_orm_writes_fail_closed_without_command(ready, manager, operation):
    ctx = ready
    obj = create(ctx)
    query = getattr(Object, manager)
    obj.title = "Bypass"
    with pytest.raises(PermissionDenied):
        if operation == "save":
            obj.save()
        elif operation == "create":
            query.create(workspace=ctx[3], object_type=obj.object_type, title="Bypass")
        elif operation == "update":
            query.filter(pk=obj.pk).update(title="Bypass")
        elif operation == "pointer":
            query.filter(pk=obj.pk).update(last_provenance_id=uuid4())
        elif operation == "bulk_create":
            query.bulk_create([Object(workspace=ctx[3], object_type=obj.object_type, title="Bypass")])
        else:
            query.bulk_update([obj], ["title"])
    obj.refresh_from_db()
    assert obj.title == "objective" and obj.version == 1
    assert current_mutation.get() is None


def test_command_context_still_rejects_foreign_fks_and_workspace_reassignment(ready):
    ctx = ready
    obj = create(ctx)
    WorkspaceMember.objects.create(workspace=ctx[4], member=ctx[2], role=20)
    foreign = run_internal(
        actor=replace(ctx[5], actor_id=ctx[2].pk),
        workspace=ctx[4],
        name="ForeignSchema",
        operation=lambda: ObjectType.objects.create(workspace=ctx[4], key="foreign", name="Foreign"),
        read=True,
    )
    with pytest.raises(ValidationError):
        schema_write(ctx, lambda: Object.objects.create(workspace=ctx[3], object_type=foreign, title="Invalid"))
    obj.workspace = ctx[4]
    with pytest.raises(PermissionDenied):
        run_internal(
            actor=replace(ctx[5], actor_id=ctx[2].pk), workspace=ctx[4], name="Move", operation=obj.save, read=True
        )


def test_successful_command_flush_records_provenance_and_exact_replay(ready):
    ctx = ready
    obj = create(ctx)
    request = envelope(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Reviewed"}})
    result = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request)
    assert execute_command(actor=ctx[5], workspace=ctx[3], envelope=request) == result
    obj.refresh_from_db()
    assert str(obj.last_provenance_id) == result["provenance_id"]
    assert obj.version == 2 and current_mutation.get() is None


def test_command_context_cannot_forge_provenance_or_move_properties_between_types(ready):
    ctx = ready
    obj = create(ctx)
    obj.last_provenance_id = uuid4()
    with pytest.raises(PermissionDenied):
        schema_write(ctx, obj.save)
    with pytest.raises(PermissionDenied):
        schema_write(ctx, lambda: Object.objects.filter(pk=obj.pk).update(last_provenance_id=uuid4()))
    foreign_definition = PropertyDefinition.objects.filter(workspace=ctx[3], object_type__key="risk").first()
    with pytest.raises(ValidationError):
        schema_write(
            ctx,
            lambda: PropertyValue.objects.create(
                workspace=ctx[3], object=obj, definition=foreign_definition, value="ignored"
            ),
        )
    assert current_mutation.get() is None


def test_rules_contract_is_server_owned_and_removed_from_replay_input(ready):
    from plane.radar.commands.execution import command_envelope

    ctx = ready
    obj = create(ctx)
    request = envelope(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Valid"}})
    with pytest.raises(ValidationError):
        execute_command(actor=ctx[5], workspace=ctx[3], envelope={**request, "rules_contract": {"revision": "forged"}})
    result = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request)
    stored = CommandExecution.objects.get(pk=result["command_id"])
    assert "rules_contract" in stored.envelope and "schema_hash" in stored.envelope
    assert "rules_contract" not in command_envelope(stored) and "schema_hash" not in command_envelope(stored)
    assert execute_command(actor=ctx[5], workspace=ctx[3], envelope=command_envelope(stored)) == result


def test_internal_object_write_revalidates_bound_mandatory_relations(ready):
    ctx = ready
    obj = create(ctx)
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="OBJ-20261005-ABCDEF", context="company:test"
    )
    mandatory_relation(ctx)
    obj.refresh_from_db()
    obj.title = "Invalid bound write"
    with pytest.raises(ValidationError):
        schema_write(ctx, obj.save)
    obj.refresh_from_db()
    assert obj.title == "objective"
    assert current_mutation.get() is None
