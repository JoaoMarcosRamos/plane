import json
from dataclasses import replace
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.db.models import Project, WorkspaceMember
from plane.radar.commands.governance import (
    GOVERNANCE_OBJECTS,
    GOVERNANCE_RELATIONS,
    create_governance_scenario,
)
from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, Relation, RelationType
from .test_core import url
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def scenario(context):
    return create_governance_scenario(actor=context[5], workspace=context[3])


def test_connected_governance_uses_normative_commands_and_audit(context, client):
    ids = scenario(context)
    assert set(ids) == {key for key, _, _ in GOVERNANCE_OBJECTS}
    assert Object.objects.filter(workspace=context[3]).count() == 5
    assert Project.objects.filter(workspace=context[3]).count() == 0
    for key, title, properties in GOVERNANCE_OBJECTS:
        obj = Object.objects.get(pk=ids[key])
        assert obj.title == title
        assert obj.created_by_id == obj.updated_by_id == context[0].pk
        assert obj.version > 1
        snapshot = client.get(url(context, f"objects/{obj.pk}/properties/")).json()
        stored = {row["definition"]["key"]: row["value"] for row in snapshot["properties"]}
        assert all(stored[prop] == value for prop, value in properties.items())
        assert all(row["stored_value"] for row in snapshot["properties"] if row["has_value"])
    assert PropertyValue.objects.get(object_id=ids["risk"], definition__key="score").value == 12
    assert not RelationType.objects.filter(workspace=context[3], key__in=["supports", "affects"]).exists()
    assert Relation.objects.count() == 4
    for source, key, target in GOVERNANCE_RELATIONS:
        edge = Relation.objects.get(source_id=ids[source], target_id=ids[target], relation_type__key=key)
        assert edge.created_by_id == edge.updated_by_id == context[0].pk
        forward = client.get(url(context, f"objects/{ids[source]}/relations/?direction=outgoing"))
        reverse = client.get(url(context, f"objects/{ids[target]}/relations/?direction=incoming"))
        assert forward.status_code == reverse.status_code == 200
        assert str(edge.pk) in {item["id"] for item in forward.json()["relations"]}
        assert str(edge.pk) in {item["id"] for item in reverse.json()["relations"]}
        assert client.get(url(context, f"objects/{ids[target]}/")).json()["title"]


def test_scenario_edits_survive_fresh_api_reads_and_invalid_edit_is_atomic(context, client):
    ids = scenario(context)
    definition = PropertyDefinition.objects.get(workspace=context[3], object_type__key="action", key="due_date")
    endpoint = url(context, f"objects/{ids['action']}/properties/{definition.pk}/")
    assert client.put(endpoint, {"value": "2026-11-03"}, format="json").status_code == 200
    snapshot = client.get(url(context, f"objects/{ids['action']}/properties/")).json()
    assert (
        next(row["value"] for row in snapshot["properties"] if row["definition"]["key"] == "due_date") == "2026-11-03"
    )
    version = snapshot["object"]["version"]
    assert client.put(endpoint, {"value": "invalid"}, format="json").status_code == 400
    assert client.get(url(context, f"objects/{ids['action']}/")).json()["version"] == version
    assert PropertyValue.objects.get(object_id=ids["action"], definition=definition).value == "2026-11-03"


def test_scenario_isolation_for_every_endpoint(context, client):
    ids = scenario(context)
    WorkspaceMember.objects.create(workspace=context[4], member=context[2], role=20)
    client.force_authenticate(user=context[2])
    for pk in ids.values():
        for suffix in ["", "properties/", "relations/"]:
            endpoint = f"/api/workspaces/{context[4].slug}/radar/objects/{pk}/{suffix}"
            assert client.get(endpoint).status_code == 404
    assert Object.objects.filter(workspace=context[4]).count() == 0
    assert Relation.objects.filter(workspace=context[4]).count() == 0


@pytest.mark.parametrize("actor_type", ["agent", "system", "integration"])
def test_scenario_rejects_nonhuman_actor_before_schema_writes(context, actor_type):
    with pytest.raises(PermissionDenied):
        create_governance_scenario(actor=replace(context[5], actor_type=actor_type), workspace=context[3])
    assert not ObjectType.objects.exists()


def test_scenario_rejects_guest_and_outsider(context):
    WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(role=5)
    for actor_id in [context[0].pk, context[2].pk]:
        with pytest.raises(PermissionDenied):
            create_governance_scenario(actor=replace(context[5], actor_id=actor_id), workspace=context[3])
    assert not ObjectType.objects.exists()


def test_scenario_rerun_preserves_identity_edits_and_versions(context):
    ids = scenario(context)
    from plane.radar.commands import update_object

    update_object(actor=context[5], workspace=context[3], object_id=ids["project"], changes={"title": "Edited sandbox"})
    before = list(Object.objects.values_list("id", "title", "version", "updated_at"))
    with pytest.raises(ValidationError, match="without RADAR objects"):
        scenario(context)
    assert list(Object.objects.values_list("id", "title", "version", "updated_at")) == before
    assert Relation.objects.count() == 4


def test_late_scenario_failure_rolls_back_schema_objects_properties_and_relations(context):
    from plane.radar.commands.semantic import create_relation

    def fail_on_last(**kwargs):
        if RelationType.objects.get(pk=kwargs["relation_type_id"]).key == "threatens":
            raise ValidationError("Injected late failure")
        return create_relation(**kwargs)

    with patch("plane.radar.commands.governance.create_relation", side_effect=fail_on_last):
        with pytest.raises(ValidationError, match="Injected late failure"):
            scenario(context)
    for model in [ObjectType, PropertyDefinition, RelationType, Object, PropertyValue, Relation]:
        assert model.all_objects.count() == 0


def test_management_command_outputs_deep_links_and_rejects_rerun(context):
    output = StringIO()
    kwargs = {"workspace": context[3].slug, "actor": context[0].pk, "reason": "Validate Phase 0.5"}
    call_command("radar_governance_scenario", stdout=output, **kwargs)
    manifest = json.loads(output.getvalue())
    assert manifest["actor"] == str(context[0].pk)
    assert len(manifest["objects"]) == 5
    assert manifest["urls"]["action"] == f"/{context[3].slug}/radar/objects/{manifest['objects']['action']}/"
    with pytest.raises(CommandError, match="without RADAR objects"):
        call_command("radar_governance_scenario", **kwargs)


def test_management_command_missing_workspace_is_readable(context):
    with pytest.raises(CommandError, match="Workspace matching query"):
        call_command("radar_governance_scenario", workspace="missing", actor=context[0].pk, reason="Validate")


def test_generic_api_accepts_additional_type_without_structural_code(context, client):
    # Legacy custom metadata is explicitly baselined before generic fact creation.
    selected = fixture_write(
        lambda: ObjectType.objects.create(workspace=context[3], key="audit_probe", name="Audit probe")
    )
    definition = fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=context[3],
            object_type=selected,
            key="reading",
            name="Reading",
            value_type="number",
            config={"min": 0, "max": 100},
        )
    )
    from plane.radar.commands import initialize_semantic_model

    initialize_semantic_model(actor=context[5], workspace=context[3])
    response = client.post(
        url(context, "objects/"), {"object_type": str(selected.pk), "title": "Generic type"}, format="json"
    )
    assert response.status_code == 201
    pk = response.json()["id"]
    assert response.json()["object_type_detail"]["key"] == "audit_probe"
    endpoint = url(context, f"objects/{pk}/properties/{definition.pk}/")
    assert client.put(endpoint, {"value": 42}, format="json").status_code == 200
    snapshot = client.get(url(context, f"objects/{pk}/properties/")).json()
    assert snapshot["properties"][0]["value"] == 42
    assert snapshot["properties"][0]["definition"]["value_type"] == "number"
