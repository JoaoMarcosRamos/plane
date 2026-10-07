"""Core U1 3B/3C: creation by declared capability (C02) and declarative lifecycle (C01)."""

from copy import deepcopy
from datetime import datetime
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps as django_apps
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.commands import create_object, initialize_semantic_model, register_actor_grant
from plane.radar.commands import primitives_semantic
from plane.radar.commands.actor import Actor
from plane.radar.commands.capabilities import CAPABILITIES, command_contracts, guard_contracts
from plane.radar.commands.execution import CommandConflict, execute_command, run_internal, schema_fingerprint
from plane.radar.commands.handlers import create_typed_object
from plane.radar.commands.runtime_control import bind_runtime_object
from plane.radar.commands.schema import update_metadata
from plane.radar.commands.semantic import set_property_value
from plane.radar.models import (
    DomainEvent,
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    Provenance,
    Relation,
    WorkspaceSchemaState,
)
from plane.radar.ontology.package import PACKAGE_BEHAVIOR, package_definitions
from plane.radar.workspace_schema import schema_revision
from .fixture_writes import fixture_write
from .test_commands import accept, approved_agent, create, decision_with_evidence, envelope, execute
from .test_core import url

pytestmark = [pytest.mark.django_db, pytest.mark.unit]

# Frozen copy of rules.ORDINARY_TRANSITIONS before 3C, the source the package lifecycles migrate.
FORMER_ORDINARY_TRANSITIONS = {
    "objective": {("draft", "active"), ("active", "on_hold"), ("on_hold", "active")},
    "project": {("draft", "active"), ("active", "on_hold"), ("on_hold", "active")},
    "action": {("todo", "in_progress"), ("in_progress", "waiting"), ("waiting", "in_progress")},
    "risk": {("identified", "monitoring"), ("monitoring", "mitigating"), ("mitigating", "monitoring")},
    "document": {("draft", "active")},
    "person": {("active", "inactive"), ("inactive", "active")},
}
TICKET_LIFECYCLE = {
    "property": "status",
    "initial": "open",
    "transitions": [
        {"from": ["open"], "to": "working"},
        {"from": ["working"], "to": "closed", "stamp": "closed_at"},
    ],
}


@pytest.fixture
def ready(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def kind(ctx, key):
    return ObjectType.objects.get(workspace=ctx[3], key=key)


def schema_write(ctx, operation):
    return run_internal(actor=ctx[5], workspace=ctx[3], name="TestSchemaConfiguration", operation=operation)


def edit(ctx, row, patch):
    group = {"objecttype": "types", "propertydefinition": "properties"}[row._meta.model_name]
    return update_metadata(
        actor=ctx[5],
        workspace=ctx[3],
        group=group,
        definition_id=row.pk,
        patch=patch,
        expected_revision=schema_revision(ctx[3]),
    )


def edit_rules(ctx, key, **sections):
    row = kind(ctx, key)
    return edit(ctx, row, {"rules": {**row.rules, **sections}})


def ticket_type(ctx, lifecycle=None):
    """A workspace type unknown to Python: no handler, spec or branch names it."""

    def operation():
        selected = ObjectType.objects.create(workspace=ctx[3], key="ticket", name="Ticket", rules={})
        for key, value_type, config, required in (
            (
                "status",
                "enum",
                {"choices": ["open", "working", "closed"], "terminal": ["closed"], "default": "open"},
                0,
            ),
            ("closed_at", "datetime", {}, 0),
            ("summary", "string", {}, 1),
        ):
            PropertyDefinition.objects.create(
                workspace=ctx[3],
                object_type=selected,
                key=key,
                name=key,
                value_type=value_type,
                config=config,
                is_required=bool(required),
            )
        return selected

    selected = schema_write(ctx, operation)
    if lifecycle is not None:
        edit(ctx, selected, {"rules": {"lifecycle": lifecycle}})
    return ObjectType.objects.get(pk=selected.pk)


def ticket(ctx, **properties):
    return create_object(
        actor=ctx[5],
        workspace=ctx[3],
        object_type=kind(ctx, "ticket").pk,
        title="Ticket",
        properties={"summary": "Reported", **properties},
    )


def status(obj):
    return primitives_semantic.effective_values(obj)["status"]


def update(ctx, obj, values=None, remove=(), actor=None):
    obj.refresh_from_db()
    return execute(
        ctx,
        "UpdateObject",
        {"object_id": str(obj.pk), "set_properties": values or {}, "remove_properties": list(remove)},
        actor=actor,
        versions={str(obj.pk): obj.version},
    )


def counts():
    return tuple(model.objects.count() for model in (Object, PropertyValue, Relation, DomainEvent, Provenance))


# --- 3B / C02: creation by capability -------------------------------------------------------


def test_new_type_creation_uses_workspace_required_defaults_and_rejects_parameters(ready):
    ctx = ready
    ticket_type(ctx)
    with pytest.raises(ValidationError):
        create_object(actor=ctx[5], workspace=ctx[3], object_type=kind(ctx, "ticket").pk, title="Missing summary")
    before = counts()
    with pytest.raises(ValidationError):
        create_object(
            actor=ctx[5],
            workspace=ctx[3],
            object_type=kind(ctx, "ticket").pk,
            title="Generic",
            properties={"summary": "Reported"},
            parameters={"owner_person_id": str(uuid4())},
        )
    assert counts() == before
    obj = ticket(ctx)
    assert primitives_semantic.effective_values(obj) == {"status": "open", "summary": "Reported"}


def test_seeded_type_accepts_extra_property_with_mandatory_semantic_effects(ready):
    ctx = ready
    action = kind(ctx, "action")
    schema_write(
        ctx,
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3], object_type=action, key="estimate", name="Estimate", value_type="integer", config={}
        ),
    )
    person = create(ctx, "person")
    result = execute(
        ctx,
        "CreateObject",
        {
            "object_type_id": str(action.pk),
            "title": "Extended action",
            "properties": {"description": "Plan", "estimate": 5},
            "parameters": {"owner_person_id": str(person.pk)},
        },
    )
    obj = Object.objects.get(pk=result["data"]["object"]["id"])
    assert primitives_semantic.effective_values(obj)["estimate"] == 5
    assert status(obj) == "todo" and result["findings"] == []
    assert Relation.objects.filter(source=obj, target=person, relation_type__key="owned_by").exists()
    created = DomainEvent.objects.get(event_type="ActionCreated", payload__action_id=str(obj.pk))
    assert created.payload["initial_status"] == "todo"
    plan = Provenance.objects.get(pk=result["provenance_id"]).context["effect_plan"]
    assert {"CreateObject", "CreateAction", "LinkObjects"} <= set(plan["authority"]["commands"])
    assert "estimate" in plan["authority"]["fields"]
    facade = execute(
        ctx, "CreateAction", {"title": "Facade", "description": "Same path", "properties": {"estimate": 8}}
    )
    assert primitives_semantic.effective_values(Object.objects.get(pk=facade["data"]["object"]["id"]))["estimate"] == 8
    assert facade["findings"][0]["code"] == "RADAR-M001"
    with pytest.raises(ValidationError):
        execute(ctx, "CreateAction", {"title": "Twice", "description": "A", "properties": {"description": "B"}})


@pytest.mark.parametrize(
    "properties,parameters",
    [
        ({"description": "Embedded", "owner_person_id": "PERSON"}, {}),
        ({"description": "Unknown"}, {"unknown_reference": "PERSON"}),
        ({"description": "Typed"}, {"executor_person_ids": "PERSON"}),
        ({"description": "Wrong type"}, {"threatens_object_ids": ["PERSON"]}),
    ],
)
def test_parameters_are_separate_from_properties_and_checked_by_the_selected_capability(ready, properties, parameters):
    ctx = ready
    person = str(create(ctx, "person").pk)

    def swap(value):
        if isinstance(value, list):
            return [person if item == "PERSON" else item for item in value]
        return person if value == "PERSON" else value

    before = counts()
    with pytest.raises(ValidationError):
        execute(
            ctx,
            "CreateObject",
            {
                "object_type_id": str(kind(ctx, "action").pk),
                "title": "Separated",
                "properties": {key: swap(value) for key, value in properties.items()},
                "parameters": {key: swap(value) for key, value in parameters.items()},
            },
        )
    assert counts() == before


@pytest.mark.parametrize(
    "key,properties",
    [
        ("action", {}),
        ("action", {"description": "   "}),
        ("action", {"description": "Started", "status": "done"}),
        ("risk", {"description": "Closed", "status": "closed"}),
        ("decision", {"context": "C", "decision": "D"}),
        ("objective", {"status": "active"}),
    ],
)
def test_creation_requirements_and_initial_state_cannot_be_bypassed(ready, key, properties):
    ctx = ready
    before = counts()
    with pytest.raises(ValidationError):
        execute(ctx, "CreateObject", {"object_type_id": str(kind(ctx, key).pk), "title": key, "properties": properties})
    assert counts() == before


def test_internal_paths_cannot_choose_another_creation_capability(ready):
    ctx = ready
    with pytest.raises(PermissionDenied):
        schema_write(ctx, lambda: create_typed_object(ctx[3], "action", "Generic action", {"description": "x"}))
    with pytest.raises(PermissionDenied):
        schema_write(
            ctx,
            lambda: create_typed_object(ctx[3], "objective", "Wrong facade", {}, creation="CreateAction"),
        )
    assert not Object.objects.exists()


def test_workspace_type_policy_selects_the_creation_capability(ready):
    ctx = ready
    before = schema_fingerprint(ctx[3])
    edit_rules(ctx, "action", creation={"capability": "CreateObject"})
    assert schema_fingerprint(ctx[3]) != before
    with pytest.raises(ValidationError) as denied:
        execute(ctx, "CreateAction", {"title": "Facade", "description": "Disabled"})
    assert denied.value.detail["code"] == "unsupported_schema"
    result = execute(ctx, "CreateObject", {"object_type_id": str(kind(ctx, "action").pk), "title": "Plain action"})
    assert result["status"] == "executed"
    assert not DomainEvent.objects.filter(event_type="ActionCreated").exists()
    edit_rules(ctx, "action", creation={"capability": "CreateAction"})
    assert execute(ctx, "CreateAction", {"title": "Restored", "description": "Facade"})["status"] == "executed"


@pytest.mark.parametrize(
    "key,creation",
    [
        ("objective", {"capability": "CreateAction"}),
        ("action", {"capability": "RegisterRisk"}),
        ("objective", {"capability": "UpdateObject"}),
        ("objective", {"capability": "Missing"}),
        ("objective", {"capability": "CreateObject", "handler": "handlers._create_object"}),
        ("objective", "CreateObject"),
    ],
)
def test_invalid_creation_descriptors_are_refused_at_configuration(ready, key, creation):
    ctx = ready
    rules, revision = deepcopy(kind(ctx, key).rules), schema_revision(ctx[3])
    with pytest.raises(ValidationError):
        edit_rules(ctx, key, creation=creation)
    assert kind(ctx, key).rules == rules and schema_revision(ctx[3]) == revision


def test_initial_state_comes_from_the_persisted_lifecycle_under_capability_limits(ready):
    ctx = ready
    lifecycle = {**kind(ctx, "objective").rules["lifecycle"], "initial": "active"}
    edit_rules(ctx, "objective", lifecycle=lifecycle)
    assert status(create(ctx, "objective")) == "active"
    action = kind(ctx, "action").rules["lifecycle"]
    with pytest.raises(ValidationError):
        edit_rules(ctx, "action", lifecycle={**action, "initial": "in_progress"})
    with pytest.raises(ValidationError):
        edit_rules(ctx, "objective", lifecycle={**lifecycle, "initial": "achieved"})
    assert kind(ctx, "action").rules["lifecycle"]["initial"] == "todo"


def test_creation_contracts_are_published_from_the_registry(ready, client):
    contracts = command_contracts()
    assert contracts["CreateObject"]["creation"]["types"] == ["*"]
    action = contracts["CreateAction"]["creation"]
    assert set(action["parameters"]) == {
        "origin_decision_id",
        "owner_person_id",
        "executor_person_ids",
        "mitigates_risk_ids",
    }
    assert action["required_properties"] == ["description"] and action["initial_states"] == ["todo"]
    assert contracts["ReviewObject"]["lifecycle"]["parameter_choices"] == ["resolved", "accepted"]
    catalog = client.get(url(ready, "schema/")).data
    assert catalog["transition_guards"] == guard_contracts()
    types = {row["key"]: row for row in catalog["object_types"]}
    assert types["decision"]["rules"]["creation"] == {"capability": "CreateDecision"}
    assert types["decision"]["rules"]["lifecycle"]["transitions"][0]["guard"] == "decision_approval"


# --- 3C / C01: declarative lifecycle ----------------------------------------------------------


def test_package_lifecycles_migrate_the_former_ordinary_transitions_exactly():
    definitions = package_definitions()
    types = [key.split(":", 1)[1] for key in definitions if key.startswith("types:")]
    assert len(types) == 11
    for key in types:
        lifecycle = definitions[f"types:{key}"]["rules"]["lifecycle"]
        ordinary = {
            (source, transition["to"])
            for transition in lifecycle["transitions"]
            if "capability" not in transition and "guard" not in transition
            for source in transition["from"]
        }
        assert ordinary == FORMER_ORDINARY_TRANSITIONS.get(key, set()), key
    frozen = import_module("plane.radar.migrations.0013_type_descriptors").DESCRIPTORS
    assert frozen == PACKAGE_BEHAVIOR


def test_custom_lifecycle_transitions_without_a_python_branch_by_type(ready):
    ctx = ready
    ticket_type(ctx, TICKET_LIFECYCLE)
    obj = ticket(ctx)
    assert update(ctx, obj, {"status": "working"})["status"] == "executed"
    with pytest.raises(ValidationError):
        update(ctx, obj, {"status": "open"})
    with pytest.raises(ValidationError):
        update(ctx, obj, {"closed_at": "2026-10-06T12:00:00+00:00"})
    result = update(ctx, obj, {"status": "closed"})
    values = primitives_semantic.effective_values(obj)
    assert values["status"] == "closed" and datetime.fromisoformat(values["closed_at"]).tzinfo
    event = DomainEvent.objects.get(provenance_id=result["provenance_id"], event_type="ObjectUpdated")
    assert set(event.payload["property_keys_set"]) == {"status", "closed_at"}
    for values, remove in (({"status": "working"}, ()), ({}, ("closed_at",)), ({}, ("status",))):
        with pytest.raises(ValidationError):
            update(ctx, obj, values, remove)
    assert status(obj) == "closed"


def test_terminal_state_needs_a_declared_exit_and_enum_without_lifecycle_stays_ordinary(ready):
    ctx = ready
    ticket_type(ctx)
    plain = ticket(ctx)
    for value in ("closed", "working", "open"):
        assert update(ctx, plain, {"status": value})["status"] == "executed"
    edit_rules(
        ctx,
        "ticket",
        lifecycle={
            **TICKET_LIFECYCLE,
            "transitions": [*TICKET_LIFECYCLE["transitions"], {"from": ["closed"], "to": "open"}],
        },
    )
    governed = ticket(ctx)
    update(ctx, governed, {"status": "working"})
    update(ctx, governed, {"status": "closed"})
    assert update(ctx, governed, {"status": "open"})["status"] == "executed"
    with pytest.raises(ValidationError):
        update(ctx, plain, {"status": "closed"})


def test_stamp_is_a_planned_effect_that_needs_grant_authority(ready):
    ctx = ready
    ticket_type(ctx, TICKET_LIFECYCLE)
    obj = ticket(ctx)
    update(ctx, obj, {"status": "working"})
    actor = Actor(actor_type="integration", actor_id=uuid4(), reason="Close", source="test", correlation_id=uuid4())
    register_actor_grant(
        actor=ctx[5],
        workspace=ctx[3],
        actor_type="integration",
        actor_id=actor.actor_id,
        delegator_id=ctx[0].pk,
        commands=["UpdateObject"],
        object_types=["ticket"],
        fields=["status"],
        requires_approval=False,
    )
    with pytest.raises(PermissionDenied):
        update(ctx, obj, {"status": "closed"}, actor=actor)
    assert status(obj) == "working"


@pytest.mark.parametrize("entry", ["command", "compatibility", "http", "primitive"])
def test_every_entry_uses_the_same_declared_transitions(ready, client, entry):
    ctx = ready
    action = create(ctx, "action", description="Work")
    definition = PropertyDefinition.objects.get(object_type=kind(ctx, "action"), key="status")

    def attempt(value):
        if entry == "command":
            return update(ctx, action, {"status": value})
        if entry == "compatibility":
            return set_property_value(
                actor=ctx[5], workspace=ctx[3], object_id=action.pk, definition_id=definition.pk, value=value
            )
        if entry == "http":
            response = client.put(
                url(ctx, f"objects/{action.pk}/properties/{definition.pk}/"), {"value": value}, format="json"
            )
            if response.status_code != 200:
                raise ValidationError(response.data)
            return response
        return schema_write(
            ctx,
            lambda: primitives_semantic.set_property_value(
                actor=ctx[5], workspace=ctx[3], object_id=action.pk, definition_id=definition.pk, value=value
            ),
        )

    if entry == "primitive":
        # A context without a lifecycle capability cannot perform even an ordinary transition.
        with pytest.raises(ValidationError):
            attempt("in_progress")
    else:
        attempt("in_progress")
        assert status(action) == "in_progress"
    with pytest.raises(ValidationError) as denied:
        attempt("done")
    assert "CompleteAction" in str(denied.value.detail)
    assert not primitives_semantic.effective_values(action).get("completed_at")


def test_specialized_capabilities_read_targets_and_dispositions_from_the_lifecycle(ready):
    ctx = ready
    document = create_object(
        actor=ctx[5],
        workspace=ctx[3],
        object_type=kind(ctx, "document").pk,
        title="Evidence",
        content="<p>Observed</p>",
    )
    bind_runtime_object(
        actor=ctx[5], workspace=ctx[3], object_id=document.pk, external_id="DOC-20261006-ABC001", context="company:test"
    )

    def review(disposition, code):
        risk = create(ctx, "risk", description="Delivery")
        bind_runtime_object(
            actor=ctx[5],
            workspace=ctx[3],
            object_id=risk.pk,
            external_id=f"RSK-20261006-{code}",
            context="company:test",
        )
        execute(
            ctx,
            "ReviewObject",
            {
                "context": "company:test",
                "target_id": str(risk.pk),
                "assessment": "Reviewed",
                "evidence_id": str(document.pk),
                "disposition": disposition,
            },
        )
        return risk

    assert status(review("accepted", "ABC002")) == "accepted"
    lifecycle = kind(ctx, "risk").rules["lifecycle"]
    edit_rules(
        ctx,
        "risk",
        lifecycle={
            **lifecycle,
            "transitions": [t for t in lifecycle["transitions"] if t.get("parameter") != "accepted"],
        },
    )
    with pytest.raises(ValidationError):
        review("accepted", "ABC003")
    action = create(ctx, "action", description="Work")
    transitions = kind(ctx, "action").rules["lifecycle"]["transitions"]
    done = next(t for t in transitions if t.get("capability") == "CompleteAction")
    edit_rules(
        ctx,
        "action",
        lifecycle={
            **kind(ctx, "action").rules["lifecycle"],
            "transitions": [*[t for t in transitions if t is not done], {**done, "from": ["in_progress"]}],
        },
    )
    with pytest.raises(ValidationError):
        execute(
            ctx, "CompleteAction", {"action_id": str(action.pk), "outcome": "Done", "evidence_id": str(document.pk)}
        )
    update(ctx, action, {"status": "in_progress"})
    result = execute(
        ctx, "CompleteAction", {"action_id": str(action.pk), "outcome": "Done", "evidence_id": str(document.pk)}
    )
    values = primitives_semantic.effective_values(action)
    assert result["status"] == "executed" and values["status"] == "done" and values["completed_at"]


def test_registered_guard_keeps_decision_taking_human_only(ready):
    ctx = ready
    decision = create(ctx, "decision", context="C", decision="D", rationale="R")
    agent = approved_agent(ctx, "integration", requires_approval=False)
    with pytest.raises(PermissionDenied):
        update(ctx, decision, {"status": "decided"}, actor=agent)
    with pytest.raises(CommandConflict):
        update(ctx, decision, {"status": "decided"})
    with pytest.raises(ValidationError):
        update(ctx, decision, {"decided_at": "2026-10-06T12:00:00+00:00"})
    assert status(decision) == "proposed"
    assert guard_contracts()["decision_approval"] == {
        "capability": "UpdateObject",
        "human_only": True,
        "types": ["decision"],
        "dynamic_references": True,
    }


def test_guarded_transition_plan_keeps_the_guard_policy_and_stamp(ready):
    from dataclasses import replace

    ctx = ready
    decision, _, person = decision_with_evidence(ctx)
    reviewer = replace(ctx[5], actor_id=ctx[1].pk)
    execute(
        ctx,
        "ApproveDecision",
        {"decision_id": str(decision.pk), "rationale": "Independent", "approver_person_id": str(person.pk)},
        actor=reviewer,
    )
    taken = execute(
        ctx, "UpdateObject", {"object_id": str(decision.pk), "set_properties": {"status": "decided"}}, actor=reviewer
    )
    plan = Provenance.objects.get(pk=taken["provenance_id"]).context["effect_plan"]
    # Planned after the handler ran in its savepoint: the guard policy must not depend on the new state.
    assert plan["authority"]["human_only"] is True
    assert {"status", "decided_at"} <= set(plan["authority"]["fields"])
    values = primitives_semantic.effective_values(decision)
    event = DomainEvent.objects.get(execution_id=taken["command_id"], event_type="DecisionTaken")
    assert values["status"] == "decided" and event.payload["decided_at"] == values["decided_at"]
    assert taken["data"]["decision_approval_id"] == event.payload["decision_approval_id"]


@pytest.mark.parametrize(
    "lifecycle",
    [
        {**TICKET_LIFECYCLE, "script": "unsafe"},
        {**TICKET_LIFECYCLE, "initial": "missing"},
        {**TICKET_LIFECYCLE, "initial": "closed"},
        {**TICKET_LIFECYCLE, "property": "summary"},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "archived"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "open"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "working"}] * 2},
        {**TICKET_LIFECYCLE, "transitions": [{"from": "open", "to": "working"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "working", "capability": "Missing"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "capability": "CompleteAction"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "capability": "ReviewObject"}]},
        {
            **TICKET_LIFECYCLE,
            "transitions": [{"from": ["open"], "to": "closed", "capability": "ReviewObject", "parameter": "maybe"}],
        },
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "parameter": "resolved"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "guard": "decision_approval"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "stamp": "summary"}]},
        {**TICKET_LIFECYCLE, "transitions": [{"from": ["open"], "to": "closed", "handler": "handlers._update"}]},
    ],
)
def test_invalid_lifecycles_are_refused_before_persisting(ready, lifecycle):
    ctx = ready
    ticket_type(ctx)
    revision = schema_revision(ctx[3])
    with pytest.raises(ValidationError):
        edit_rules(ctx, "ticket", lifecycle=lifecycle)
    assert kind(ctx, "ticket").rules == {} and schema_revision(ctx[3]) == revision


def test_lifecycle_dependencies_are_validated_when_definitions_change(ready):
    ctx = ready
    ticket_type(ctx, TICKET_LIFECYCLE)
    status_definition = PropertyDefinition.objects.get(object_type=kind(ctx, "ticket"), key="status")
    stamp = PropertyDefinition.objects.get(object_type=kind(ctx, "ticket"), key="closed_at")
    with pytest.raises(ValidationError):
        edit(ctx, status_definition, {"config": {**status_definition.config, "terminal": ["open", "closed"]}})
    with pytest.raises(ValidationError):
        edit(ctx, stamp, {"is_active": False})
    assert PropertyDefinition.objects.get(pk=stamp.pk).is_active


def test_lifecycle_change_invalidates_a_pending_transition_approval(ready):
    ctx = ready
    action = create(ctx, "action", description="Work")
    actor = approved_agent(ctx)
    request = envelope(
        ctx, "UpdateObject", {"object_id": str(action.pk), "set_properties": {"status": "in_progress"}}, actor=actor
    )
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    approval = accept(ctx, pending)
    lifecycle = kind(ctx, "action").rules["lifecycle"]
    edit_rules(
        ctx,
        "action",
        lifecycle={**lifecycle, "transitions": lifecycle["transitions"][:2] + lifecycle["transitions"][3:]},
    )
    from dataclasses import replace

    with pytest.raises(CommandConflict):
        execute_command(actor=replace(actor, approval_id=approval.pk), workspace=ctx[3], envelope=request)
    assert status(action) == "todo"


def test_data_migration_installs_frozen_descriptors_and_preserves_local_ones(ready):
    ctx = ready
    migration = import_module("plane.radar.migrations.0013_type_descriptors")
    editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    custom = {"lifecycle": {"property": "status", "initial": "draft", "transitions": []}}
    state = WorkspaceSchemaState.objects.get(workspace=ctx[3])
    legacy_base = deepcopy(state.installed_base)
    for record, spec in legacy_base["definitions"].items():
        if record.startswith("types:"):
            spec["rules"] = {"invariants": spec["rules"]["invariants"]}

    def legacy():
        for row in ObjectType.objects.filter(workspace=ctx[3]):
            row.rules = {"invariants": row.rules.get("invariants", []), **(custom if row.key == "objective" else {})}
            row.save()
        WorkspaceSchemaState.objects.filter(pk=state.pk).update(installed_base=legacy_base)

    fixture_write(legacy)
    revision = schema_revision(ctx[3])
    fixture_write(lambda: migration.install_descriptors(django_apps, editor))
    assert kind(ctx, "objective").rules == {
        "invariants": [{"kind": "ordered_dates", "first": "start_date", "second": "due_date"}],
        **custom,
    }
    for key in ("action", "risk", "decision", "commitment"):
        assert {k: v for k, v in kind(ctx, key).rules.items() if k != "invariants"} == PACKAGE_BEHAVIOR[key]
    state.refresh_from_db()
    assert state.revision == revision + 1
    assert (
        state.installed_base["definitions"]["types:action"]["rules"]["lifecycle"]
        == PACKAGE_BEHAVIOR["action"]["lifecycle"]
    )
    assert "lifecycle" not in state.installed_base["definitions"]["types:objective"]["rules"]
    fixture_write(lambda: migration.remove_descriptors(django_apps, editor))
    assert all(set(row.rules) <= {"invariants"} for row in ObjectType.objects.filter(workspace=ctx[3]))
    state.refresh_from_db()
    assert all(
        set(spec["rules"]) == {"invariants"}
        for record, spec in state.installed_base["definitions"].items()
        if record.startswith("types:")
    )


def test_every_lifecycle_capability_is_registered_with_declared_types():
    assert {name for name, c in CAPABILITIES.items() if c.lifecycle_types} == {
        "UpdateObject",
        "CompleteAction",
        "DelegateAction",
        "ReviewObject",
    }
    assert {name for name, c in CAPABILITIES.items() if c.creation} == {
        "CreateObject",
        "CreateAction",
        "RegisterRisk",
        "CreateDecision",
    }
