"""Core U1 phase 4 backend: effective capacities (C20), presentation (C21) and creation contracts (C03)."""

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from rest_framework.exceptions import ValidationError

from plane.db.models import WorkspaceMember
from plane.radar.capacities import object_capacities
from plane.radar.commands import create_object, initialize_semantic_model, configure_person_identity
from plane.radar.commands.capabilities import command_contracts
from plane.radar.commands.descriptors import layout
from plane.radar.commands.execution import run_internal
from plane.radar.commands.primitives_semantic import effective_values, property_definitions
from plane.radar.commands.schema import update_metadata
from plane.radar.models import (
    CommandExecution,
    DecisionApproval,
    DomainEvent,
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    Provenance,
    Relation,
    RelationType,
    WorkspaceSchemaState,
)
from plane.radar.ontology.package import PACKAGE_PRESENTATION, package_definitions
from plane.radar.workspace_schema import schema_revision
from .fixture_writes import fixture_write
from .test_commands import create, decision_with_evidence, execute
from .test_core import url

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def ready(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def kind(ctx, key):
    return ObjectType.objects.get(workspace=ctx[3], key=key)


def capacities(ctx, obj, actor=None):
    return object_capacities(actor=actor or ctx[5], workspace=ctx[3], object_id=obj.pk)


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


def counts():
    return tuple(
        model.objects.count()
        for model in (Object, PropertyValue, Relation, DomainEvent, Provenance, CommandExecution, DecisionApproval)
    )


def reviewer(ctx):
    return replace(ctx[5], actor_id=ctx[1].pk)


# --- C03: creation and action contracts carry reference hints ---------------------------------


def test_reference_inputs_publish_the_object_types_they_accept():
    contracts = command_contracts()
    action = contracts["CreateAction"]["creation"]["parameters"]
    assert action["owner_person_id"]["type"] == "uuid" and action["owner_person_id"]["object_types"] == ["person"]
    assert action["executor_person_ids"]["items"]["object_types"] == ["person"]
    assert contracts["RegisterRisk"]["creation"]["parameters"]["threatens_object_ids"]["items"]["object_types"] == [
        "objective",
        "project",
    ]
    complete = contracts["CompleteAction"]
    assert complete["object_action"] == "action_id" and complete["input"]["evidence_id"]["object_types"] == ["document"]
    assert contracts["ApproveDecision"]["object_action"] == "decision_id"


# --- C21: presentation --------------------------------------------------------------------------


def test_package_presentations_are_valid_and_migration_freezes_them(ready):
    ctx = ready
    for key in PACKAGE_PRESENTATION:
        row = kind(ctx, key)
        resolved = layout(row, property_definitions(SimpleNamespace(workspace=ctx[3], object_type_id=row.pk)))
        assert (
            resolved["source"] == "presentation" and not resolved["diagnostic"] and not resolved["retired_references"]
        )
        listed = [p for section in resolved["sections"] for p in section["properties"]]
        assert len(listed) == len(set(listed)) and resolved["narrative"]["field"] not in listed, key
    frozen = import_module("plane.radar.migrations.0014_type_presentation").PRESENTATIONS
    assert frozen == PACKAGE_PRESENTATION
    assert all(
        "presentation" in spec["rules"] for name, spec in package_definitions().items() if name.startswith("types:")
    )


def test_two_types_share_the_page_with_distinct_sections_and_a_documented_fallback(ready):
    ctx = ready
    action = capacities(ctx, create(ctx, "action", description="Plan"))["presentation"]
    decision = capacities(ctx, create(ctx, "decision", context="C", decision="D", rationale="R"))["presentation"]
    assert action["narrative"] == {"field": "description", "label": "description"}
    assert action["content"] == {"role": "notes", "label": "Notes"}
    assert [section["key"] for section in action["sections"]] == ["execution", "other"]
    assert action["sections"][-1]["properties"] == ["due_at"]
    assert decision["narrative"]["field"] == "decision"
    assert [section["key"] for section in decision["sections"]] == ["reasoning", "status"]

    def custom():
        selected = ObjectType.objects.create(workspace=ctx[3], key="note", name="Note", rules={})
        PropertyDefinition.objects.create(
            workspace=ctx[3],
            object_type=selected,
            key="topic",
            name="Topic",
            value_type="string",
            config={"default": ""},
        )
        return selected

    selected = run_internal(actor=ctx[5], workspace=ctx[3], name="TestSchemaConfiguration", operation=custom)
    note = create_object(actor=ctx[5], workspace=ctx[3], object_type=selected.pk, title="Plain")
    fallback = capacities(ctx, note)["presentation"]
    assert fallback["source"] == "fallback" and fallback["content"] == {"role": "narrative", "label": "Content"}
    assert fallback["sections"] == [{"key": "properties", "label": "Properties", "properties": ["topic"]}]


@pytest.mark.parametrize(
    "presentation",
    [
        {"narrative": "content", "sections": [], "theme": "dark"},
        {"narrative": "content", "sections": [{"key": "a", "label": "A", "properties": ["status"], "hidden": True}]},
        {"narrative": "description", "sections": [{"key": "a", "label": "A", "properties": ["description"]}]},
        {"narrative": "content", "sections": [{"key": "a", "label": "A", "properties": ["status", "status"]}]},
        {
            "narrative": "content",
            "sections": [
                {"key": "a", "label": "A", "properties": ["status"]},
                {"key": "b", "label": "B", "properties": ["status"]},
            ],
        },
        {"narrative": "content", "sections": [{"key": "a", "label": " ", "properties": []}]},
        {"narrative": "score", "sections": []},
        {"narrative": "likelihood", "sections": []},
        {"narrative": "missing", "sections": []},
        {"narrative": "content", "sections": [{"key": "a", "label": "A", "properties": ["missing"]}]},
        {"narrative": "content", "sections": [{"key": f"s{i}", "label": "S", "properties": []} for i in range(17)]},
    ],
)
def test_invalid_presentations_are_refused_when_edited(ready, presentation):
    ctx = ready
    row = kind(ctx, "risk")
    rules, revision = deepcopy(row.rules), schema_revision(ctx[3])
    with pytest.raises(ValidationError):
        edit(ctx, row, {"rules": {**row.rules, "presentation": presentation}})
    assert kind(ctx, "risk").rules == rules and schema_revision(ctx[3]) == revision


def test_retiring_a_referenced_property_degrades_layout_without_copying_narratives(ready):
    ctx = ready
    obj = create(ctx, "objective", description="Original narrative")
    fixture_write(lambda: Object.objects.filter(pk=obj.pk).update(content="<p>Earlier notes</p>"))
    presentation = capacities(ctx, obj)["presentation"]
    assert presentation["legacy_notes"] is True and presentation["content"]["role"] == "notes"
    # Layout never blocks retirement; the 3B creation contract still protects fields it needs.
    with pytest.raises(ValidationError):
        edit(
            ctx,
            PropertyDefinition.objects.get(object_type=kind(ctx, "action"), key="description"),
            {"is_active": False},
        )
    edit(
        ctx, PropertyDefinition.objects.get(object_type=kind(ctx, "objective"), key="description"), {"is_active": False}
    )
    edit(ctx, PropertyDefinition.objects.get(object_type=kind(ctx, "objective"), key="outcome"), {"is_active": False})
    degraded = capacities(ctx, obj)["presentation"]
    assert degraded["narrative"] == {"field": "content", "label": "Content"} and degraded["legacy_notes"] is False
    assert degraded["retired_references"] == ["outcome", "description"]
    assert degraded["sections"][0]["properties"] == ["progress"]
    obj.refresh_from_db()
    assert obj.content == "<p>Earlier notes</p>"
    assert PropertyValue.all_objects.get(object=obj, definition__key="description").value == "Original narrative"


# --- C20: effective capacities ------------------------------------------------------------------


def test_derived_stamp_and_lifecycle_fields_are_not_free_inputs(ready):
    ctx = ready
    risk = capacities(ctx, create(ctx, "risk", description="Delivery"))
    assert risk["fields"]["score"] == {
        "editable": False,
        "removable": False,
        "reason": "derived",
        "options": None,
        "governed_by": [],
    }
    assert risk["fields"]["likelihood"]["editable"] is True
    assert risk["fields"]["status"]["options"] == ["identified", "monitoring"]
    runtime = {(t["to"], t["parameter"]) for t in risk["transitions"] if t["reason"] == "runtime_context"}
    assert runtime == {("closed", "resolved"), ("accepted", "accepted")}
    action = capacities(ctx, create(ctx, "action", description="Work"))
    assert action["fields"]["completed_at"]["reason"] == "lifecycle_stamp"
    assert action["fields"]["completed_at"]["governed_by"] == ["CompleteAction"]
    assert action["fields"]["status"]["options"] == ["todo", "in_progress"]
    assert "done" not in action["fields"]["status"]["options"]
    complete = next(a for a in action["actions"] if a["capability"] == "CompleteAction")
    assert complete["available"] and complete["reason"] == "requires_input" and complete["transition"]["to"] == "done"


def test_terminal_state_exposes_no_free_options_or_completion(ready):
    ctx = ready
    action = create(ctx, "action", description="Work")
    document = create_object(
        actor=ctx[5], workspace=ctx[3], object_type=kind(ctx, "document").pk, title="Evidence", content="<p>Done</p>"
    )
    execute(ctx, "CompleteAction", {"action_id": str(action.pk), "outcome": "Done", "evidence_id": str(document.pk)})
    result = capacities(ctx, action)
    assert result["state"]["terminal"] is True and result["fields"]["status"] == {
        "editable": False,
        "removable": False,
        "reason": "lifecycle_state",
        "options": ["done"],
        "governed_by": [],
    }
    complete = next(a for a in result["actions"] if a["capability"] == "CompleteAction")
    assert not complete["available"] and complete["reason"] == "not_declared_from_state"
    evidence = capacities(ctx, document)
    assert evidence["envelope"]["content"] == {"editable": False, "reason": "evidence_in_use"}
    assert all(field["reason"] == "evidence_in_use" for key, field in evidence["fields"].items() if key != "status")
    verifies = Relation.objects.get(relation_type__key="verifies", source=document)
    assert evidence["relations"][str(verifies.pk)] == {
        "removable": False,
        "reason": "completion_evidence",
        "requires_review": False,
    }


def test_guarded_transition_and_approval_are_probed_with_the_real_guards(ready):
    ctx = ready
    decision, _, person = decision_with_evidence(ctx)
    before = counts()
    author = capacities(ctx, decision)
    take = next(t for t in author["transitions"] if t["to"] == "decided")
    assert take["guard"] == "decision_approval" and take["human_only"] and not take["available"]
    assert take["reason"] == "approval_stale"
    approve = next(a for a in author["actions"] if a["capability"] == "ApproveDecision")
    assert not approve["available"] and approve["reason"] == "not_permitted"
    candidate = capacities(ctx, decision, reviewer(ctx))
    approve = next(a for a in candidate["actions"] if a["capability"] == "ApproveDecision")
    assert approve["available"] and approve["prefill"]["approver_person_id"] == str(person.pk)
    assert counts() == before
    decision.refresh_from_db()
    version = decision.version
    execute(
        ctx,
        "ApproveDecision",
        {"decision_id": str(decision.pk), "rationale": "Independent", "approver_person_id": str(person.pk)},
        actor=reviewer(ctx),
    )
    approved = capacities(ctx, decision, reviewer(ctx))
    assert next(t for t in approved["transitions"] if t["to"] == "decided")["available"] is True
    made_by = Relation.objects.get(relation_type__key="made_by", source=decision)
    assert approved["relations"][str(made_by.pk)]["reason"] == "approval_history"
    decision.refresh_from_db()
    assert decision.version == version + 1 and not approved["metadata_errors"]


def test_decided_decision_fields_and_relations_follow_the_shared_restrictions(ready):
    ctx = ready
    decision, document, person = decision_with_evidence(ctx)
    execute(
        ctx,
        "ApproveDecision",
        {"decision_id": str(decision.pk), "rationale": "Independent", "approver_person_id": str(person.pk)},
        actor=reviewer(ctx),
    )
    execute(
        ctx,
        "UpdateObject",
        {"object_id": str(decision.pk), "set_properties": {"status": "decided"}},
        actor=reviewer(ctx),
    )
    result = capacities(ctx, decision)
    for key in ("context", "decision", "rationale", "consequences"):
        assert result["fields"][key]["reason"] == "decision_taken"
        with pytest.raises(ValidationError):
            execute(ctx, "UpdateObject", {"object_id": str(decision.pk), "set_properties": {key: "Changed"}})
    assert result["envelope"]["title"]["reason"] == "decision_taken"
    assert result["fields"]["decided_at"]["reason"] == "lifecycle_stamp"
    informed = Relation.objects.get(relation_type__key="informed_by", source=decision, target=document)
    assert result["relations"][str(informed.pk)]["reason"] == "decision_evidence"


def test_measurement_relations_and_review_requirements(ready):
    ctx = ready
    indicator = capacities(ctx, create(ctx, "indicator"))
    assert indicator["fields"]["current"]["reason"] == "measurement"
    assert indicator["fields"]["current"]["governed_by"] == ["RecordMeasurement"]
    person = create(ctx, "person")
    action = Object.objects.get(
        pk=execute(ctx, "CreateAction", {"title": "Owned", "description": "Work", "owner_person_id": str(person.pk)})[
            "data"
        ]["object"]["id"]
    )
    commitment = create(ctx, "commitment")
    commits = RelationType.objects.get(workspace=ctx[3], key="commits_to")
    execute(
        ctx,
        "LinkObjects",
        {"source_id": str(commitment.pk), "target_id": str(action.pk), "relation_type_id": str(commits.pk)},
    )
    result = capacities(ctx, action)
    owned = Relation.objects.get(relation_type__key="owned_by", source=action)
    edge = Relation.objects.get(relation_type=commits, source=commitment)
    assert result["relations"][str(owned.pk)] == {"removable": True, "reason": None, "requires_review": True}
    assert result["relations"][str(edge.pk)]["reason"] == "mandatory_relation"


def test_readers_get_read_only_capacities_without_probes(ready):
    ctx = ready
    obj = create(ctx, "action", description="Work")
    WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[1]).update(role=5)
    result = capacities(ctx, obj, reviewer(ctx))
    assert result["can_write"] is False
    assert {field["reason"] for field in result["fields"].values()} == {"read_only_access"}
    assert all(t["reason"] == "read_only_access" and not t["available"] for t in result["transitions"])
    assert all(a["reason"] == "read_only_access" for a in result["actions"])


def test_invalid_metadata_is_distinguished_from_current_unavailability(ready):
    ctx = ready
    obj = create(ctx, "objective")
    row = kind(ctx, "objective")
    broken = {**row.rules, "lifecycle": {**row.rules["lifecycle"], "initial": "missing"}}
    fixture_write(lambda: ObjectType.objects.filter(pk=row.pk).update(rules=broken))
    result = capacities(ctx, obj)
    assert result["metadata_errors"] and result["metadata_errors"][0]["section"] == "rules"
    assert {field["reason"] for field in result["fields"].values()} == {"invalid_metadata"}
    assert result["envelope"]["title"]["reason"] == "invalid_metadata" and result["transitions"] == []
    with pytest.raises(ValidationError):
        execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Blocked"}})


def test_capacities_endpoint_is_scoped_to_workspace_members(ready, client):
    ctx = ready
    obj = create(ctx, "risk", description="Delivery")
    response = client.get(url(ctx, f"objects/{obj.pk}/capabilities/"))
    assert response.status_code == 200 and response.data["schema_revision"] == schema_revision(ctx[3])
    assert response.data["object"] == {"id": str(obj.pk), "version": obj.version, "object_type": "risk"}
    client.force_authenticate(ctx[2])
    assert client.get(url(ctx, f"objects/{obj.pk}/capabilities/")).status_code in {403, 404}


def test_presentation_data_migration_preserves_local_layouts(ready):
    ctx = ready
    migration = import_module("plane.radar.migrations.0014_type_presentation")
    editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    local = {"narrative": "content", "sections": []}
    state = WorkspaceSchemaState.objects.get(workspace=ctx[3])

    def legacy():
        for row in ObjectType.objects.filter(workspace=ctx[3]):
            rules = {k: v for k, v in row.rules.items() if k != "presentation"}
            row.rules = {**rules, **({"presentation": local} if row.key == "case" else {})}
            row.save()

    fixture_write(legacy)
    revision = schema_revision(ctx[3])
    fixture_write(lambda: migration.install_presentations(django_apps, editor))
    assert kind(ctx, "case").rules["presentation"] == local
    assert kind(ctx, "action").rules["presentation"] == PACKAGE_PRESENTATION["action"]
    state.refresh_from_db()
    assert state.revision == revision + 1
    fixture_write(lambda: migration.remove_presentations(django_apps, editor))
    assert all("presentation" not in row.rules for row in ObjectType.objects.filter(workspace=ctx[3]))
    assert effective_values(create(ctx, "objective"))["status"] == "draft"


def test_capacities_follow_the_actor_specific_approver_identity(ready):
    ctx = ready
    decision, _, person = decision_with_evidence(ctx)
    configure_person_identity(actor=ctx[5], workspace=ctx[3], user_id=ctx[1].pk, person_id=person.pk, can_approve=False)
    approve = next(
        a for a in capacities(ctx, decision, reviewer(ctx))["actions"] if a["capability"] == "ApproveDecision"
    )
    assert not approve["available"] and approve["reason"] == "not_permitted"
