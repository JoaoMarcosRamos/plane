"""Schema installation/upgrades, revision preconditions and uniform active reads."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound

from plane.db.models import WorkspaceMember
from plane.radar.active import active_objects, active_values, active_relations
from plane.radar.agent_runtime import load_context
from plane.radar.commands import create_object, update_object, initialize_semantic_model
from plane.radar.commands.execution import execute_command, CommandConflict, run_internal
from plane.radar.commands.schema import install_schema, preview_upgrade, upgrade_schema, update_metadata, three_way
from plane.radar.models import (
    ObjectType,
    PropertyDefinition,
    RelationType,
    Relation,
    WorkspaceSchemaState,
    SchemaUpgrade,
    Provenance,
)
from plane.radar.ontology.contracts import validate_property_config, validate_relation_descriptor
from plane.radar.ontology.package import package_definitions
from plane.radar.workspace_schema import schema_revision, SchemaConflict
from .fixture_writes import fixture_write
from .test_core import url
from .test_commands import envelope, approved_agent

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def installed(context):
    state = install_schema(actor=context[5], workspace=context[3])
    assert state.revision == 1
    return context


def object_for(ctx, key="objective"):
    kind = ObjectType.objects.get(workspace=ctx[3], key=key)
    return create_object(actor=ctx[5], workspace=ctx[3], object_type=kind.pk, title="Phase 2")


def edit(ctx, row, patch_data):
    group = {"objecttype": "types", "propertydefinition": "properties", "relationtype": "relations"}[
        row._meta.model_name
    ]
    return update_metadata(
        actor=ctx[5],
        workspace=ctx[3],
        group=group,
        definition_id=row.pk,
        patch=patch_data,
        expected_revision=schema_revision(ctx[3]),
    )


def upgrade(ctx, candidate, version="3.2.1"):
    plan = preview_upgrade(
        actor=ctx[5], workspace=ctx[3], expected_revision=schema_revision(ctx[3]), definitions=candidate
    )
    return upgrade_schema(
        actor=ctx[5],
        workspace=ctx[3],
        expected_revision=plan["schema_revision"],
        reviewed_hash=plan["candidate_hash"],
        definitions=candidate,
        version=version,
    )


def test_gets_do_not_install_schema_and_explicit_provisioning_is_admin_only(client, context):
    for suffix in ("schema/", "object-types/", "property-definitions/", "relation-types/", "objects/"):
        response = client.get(url(context, suffix))
        assert response.status_code == 200
    assert client.get(url(context, "schema/")).data["status"] == "uninitialized"
    assert (
        not ObjectType.objects.exists()
        and not WorkspaceSchemaState.objects.exists()
        and not Provenance.objects.exists()
    )
    client.force_authenticate(context[1])
    assert client.post(url(context, "schema/"), {"operation": "install"}, format="json").status_code == 403
    client.force_authenticate(context[0])
    first = client.post(url(context, "schema/"), {"operation": "install"}, format="json")
    assert first.status_code == 200 and first.data["schema_revision"] == 1
    before = (Provenance.objects.count(), SchemaUpgrade.objects.count())
    assert client.post(url(context, "schema/"), {"operation": "install"}, format="json").data == first.data
    assert (Provenance.objects.count(), SchemaUpgrade.objects.count()) == before


def test_three_way_field_merge_preserves_local_customization():
    base = {"name": "Base", "config": {"min": 1, "max": 5}}
    local = {"name": "Custom", "config": {"min": 1, "max": 5}}
    merged, conflicts = three_way(base, local, {"name": "Base", "config": {"min": 0, "max": 5}})
    assert merged == {"name": "Custom", "config": {"min": 0, "max": 5}} and not conflicts
    assert three_way(base, local, {**base, "name": "Package"})[1] == ["name"]


def test_upgrade_preserves_ids_local_fields_and_inactive_definitions(installed):
    ctx = installed
    kind = ObjectType.objects.get(workspace=ctx[3], key="objective")
    edit(ctx, kind, {"name": "My objective"})
    inactive = PropertyDefinition.objects.get(object_type=kind, key="description")
    edit(ctx, inactive, {"is_active": False})
    candidate = package_definitions()
    candidate["types:objective"]["description"] = "Package description"
    state = upgrade(ctx, candidate)
    kind.refresh_from_db()
    inactive.refresh_from_db()
    assert kind.name == "My objective" and kind.description == "Package description"
    assert not inactive.is_active and state.revision == 4
    before = (state.revision, Provenance.objects.count(), SchemaUpgrade.objects.count())
    assert upgrade(ctx, candidate).revision == before[0]
    assert (schema_revision(ctx[3]), Provenance.objects.count(), SchemaUpgrade.objects.count()) == before
    assert state.installed_base["ids"]["types:objective"] == str(kind.pk)


def test_upgrade_conflicts_are_reviewable_and_never_overwrite_local_fields(installed):
    kind = ObjectType.objects.get(workspace=installed[3], key="objective")
    edit(installed, kind, {"name": "Local"})
    candidate = package_definitions()
    candidate["types:objective"]["name"] = "Package"
    before = (schema_revision(installed[3]), Provenance.objects.count(), SchemaUpgrade.objects.count())
    plan = preview_upgrade(
        actor=installed[5], workspace=installed[3], expected_revision=before[0], definitions=candidate
    )
    assert plan["conflicts"] == [{"key": "types:objective", "fields": ["name"]}]
    with pytest.raises(SchemaConflict):
        upgrade(installed, candidate)
    kind.refresh_from_db()
    assert kind.name == "Local"
    assert before == (schema_revision(installed[3]), Provenance.objects.count(), SchemaUpgrade.objects.count())


def test_legacy_custom_workspace_is_baselined_without_a_presumed_package_version(context):
    custom = fixture_write(
        lambda: ObjectType.objects.create(workspace=context[3], key="objective", name="Local", is_system=False)
    )
    state = install_schema(actor=context[5], workspace=context[3])
    assert state.origin == "legacy" and state.package_version == "" and state.package_hash == ""
    assert {"key": "types:objective", "reason": "unmanaged"} in state.divergences
    assert ObjectType.objects.get(pk=custom.pk).name == "Local"
    assert ObjectType.objects.count() == 1
    with pytest.raises(SchemaConflict):
        upgrade(context, package_definitions())


def test_retired_deleted_definition_is_never_recreated_by_install_or_upgrade(installed):
    row = PropertyDefinition.objects.get(workspace=installed[3], object_type__key="objective", key="description")
    fixture_write(lambda: PropertyDefinition.all_objects.filter(pk=row.pk).update(deleted_at=timezone.now()))
    initialize_semantic_model(actor=installed[5], workspace=installed[3])
    upgrade(installed, package_definitions())
    assert not PropertyDefinition.objects.filter(object_type=row.object_type, key=row.key).exists()
    assert PropertyDefinition.all_objects.filter(object_type=row.object_type, key=row.key).count() == 1


def test_upgrade_failure_rolls_back_metadata_state_history_and_provenance(installed):
    candidate = package_definitions()
    candidate["types:objective"]["description"] = "Must rollback"
    before = (schema_revision(installed[3]), Provenance.objects.count(), SchemaUpgrade.objects.count())
    with patch.object(SchemaUpgrade, "save", side_effect=IntegrityError("audit failed")), pytest.raises(IntegrityError):
        upgrade(installed, candidate)
    assert ObjectType.objects.get(workspace=installed[3], key="objective").description == ""
    assert before == (schema_revision(installed[3]), Provenance.objects.count(), SchemaUpgrade.objects.count())


@pytest.mark.parametrize("change", ["kind", "choices", "required"])
def test_incompatible_property_changes_require_explicit_fact_migration(installed, change):
    obj = object_for(installed)
    row = PropertyDefinition.objects.get(
        object_type=obj.object_type,
        key="status" if change == "choices" else "start_date" if change == "required" else "description",
    )
    if change == "kind":
        patch_data = {"value_type": "integer", "config": {}}
    elif change == "choices":
        patch_data = {"config": {"choices": ["active"], "default": "active", "terminal": []}}
    else:
        patch_data = {"is_required": True, "config": {}}
    before = schema_revision(installed[3])
    with pytest.raises(ValidationError):
        edit(installed, row, patch_data)
    assert schema_revision(installed[3]) == before
    obj.refresh_from_db()
    assert obj.version == 1


def test_cardinality_reduction_checks_existing_edges(installed):
    source, first, second = (object_for(installed) for _ in range(3))
    kind = RelationType.objects.get(workspace=installed[3], key="relates_to")
    from plane.radar.commands import create_relation

    for target in (first, second):
        create_relation(
            actor=installed[5],
            workspace=installed[3],
            relation_type_id=kind.pk,
            source_id=source.pk,
            target_id=target.pk,
        )
    with pytest.raises(ValidationError):
        edit(installed, kind, {"cardinality": "0..1"})
    assert Relation.objects.filter(source=source).count() == 2


def test_metadata_revision_changes_without_incrementing_objects_and_rejects_old_forms(client, installed):
    obj = object_for(installed)
    row = PropertyDefinition.objects.get(object_type=obj.object_type, key="description")
    first = client.get(url(installed, f"objects/{obj.pk}/properties/")).data
    edit(installed, row, {"name": "Narrative"})
    second = client.get(url(installed, f"objects/{obj.pk}/properties/")).data
    assert second["object"]["version"] == first["object"]["version"] == 1
    assert second["schema_revision"] == first["schema_revision"] + 1
    response = client.patch(
        url(installed, f"objects/{obj.pk}/"),
        {"title": "Old form"},
        format="json",
        HTTP_X_RADAR_EXPECTED_SCHEMA_REVISION=str(first["schema_revision"]),
    )
    assert response.status_code == 409 and response.data["code"] == "schema_revision_conflict"


def test_confirmed_replay_precedes_schema_precondition(installed):
    obj = object_for(installed)
    kwargs = dict(
        actor=installed[5],
        workspace=installed[3],
        object_id=obj.pk,
        changes={"title": "Confirmed"},
        expected_versions={str(obj.pk): 1},
        expected_schema_revision=1,
        idempotency_key="schema-replay",
    )
    update_object(**kwargs)
    kind = ObjectType.objects.get(pk=obj.object_type_id)
    edit(installed, kind, {"name": "New label"})
    before = Provenance.objects.count()
    assert update_object(**kwargs).title == "Confirmed" and Provenance.objects.count() == before


def test_pending_approval_is_stale_after_metadata_change(installed):
    obj = object_for(installed)
    agent = approved_agent(installed, requires_approval=True)
    request = envelope(
        installed,
        "UpdateObject",
        {"object_id": str(obj.pk), "changes": {"title": "Agent"}},
        actor=agent,
        versions={str(obj.pk): 1},
    )
    first = execute_command(actor=agent, workspace=installed[3], envelope=request)
    assert first["status"] == "pending_approval"
    edit(installed, obj.object_type, {"name": "Changed"})
    with pytest.raises(CommandConflict, match="approval_stale"):
        execute_command(actor=agent, workspace=installed[3], envelope=request)


@pytest.mark.parametrize("retirement", ["inactive_type", "deleted_type", "deleted_object"])
def test_uniform_object_policy_and_explicit_history(client, installed, retirement):
    obj = object_for(installed)
    if retirement == "inactive_type":
        edit(installed, obj.object_type, {"is_active": False})
    elif retirement == "deleted_type":
        fixture_write(lambda: ObjectType.all_objects.filter(pk=obj.object_type_id).update(deleted_at=timezone.now()))
    else:
        fixture_write(lambda: type(obj).all_objects.filter(pk=obj.pk).update(deleted_at=timezone.now()))
    assert not active_objects(installed[3]).filter(pk=obj.pk).exists()
    assert client.get(url(installed, "objects/")).data == []
    for suffix in ("", "properties/", "relations/"):
        assert client.get(url(installed, f"objects/{obj.pk}/{suffix}")).status_code == 404
    assert client.get(url(installed, f"objects/{obj.pk}/provenance/")).status_code == 200
    with pytest.raises(NotFound):
        load_context(active_objects(installed[3]), SimpleNamespace(fields=["*"]), [obj.pk])


def test_agent_context_excludes_retired_values_relations_and_endpoints(installed):
    obj, target = object_for(installed), object_for(installed)
    row = PropertyDefinition.objects.get(object_type=obj.object_type, key="description")
    from plane.radar.commands import set_property_value

    set_property_value(
        actor=installed[5], workspace=installed[3], object_id=obj.pk, definition_id=row.pk, value="private retired fact"
    )
    from plane.radar.commands import create_relation

    kind = RelationType.objects.get(workspace=installed[3], key="relates_to")
    create_relation(
        actor=installed[5], workspace=installed[3], relation_type_id=kind.pk, source_id=obj.pk, target_id=target.pk
    )
    edit(installed, row, {"is_active": False})
    edit(installed, kind, {"is_active": False})
    snapshot = load_context(active_objects(installed[3]), SimpleNamespace(fields=["*"]), [obj.pk])
    assert "description" not in snapshot["objects"][0]["properties"] and snapshot["relations"] == []
    assert (
        not active_values(installed[3]).filter(definition=row).exists() and not active_relations(installed[3]).exists()
    )


@pytest.mark.parametrize(
    "kind,config",
    [
        ("enum", {}),
        ("enum", {"choices": ["a", "a"]}),
        ("enum", {"choices": ["a"], "default": "b"}),
        ("enum", {"choices": ["a"], "terminal": ["b"]}),
        ("number", {"min": True}),
        ("number", {"min": 2, "max": 1}),
        ("integer", {"default": 1.2}),
        ("boolean", {"default": "true"}),
        ("string", {"script": "unsafe"}),
        ("rich_text", {}),
        ("user", {"default": "invalid"}),
    ],
)
def test_invalid_property_config_is_rejected_before_persistence(kind, config):
    with pytest.raises(ValidationError):
        validate_property_config(kind, config)


def test_invalid_relation_descriptors_are_rejected():
    spec = {
        "source_types": ["objective"],
        "target_types": ["action"],
        "allowed_pairs": [["action", "objective"]],
        "cardinality": "0..n",
        "allow_self": False,
    }
    with pytest.raises(ValidationError):
        validate_relation_descriptor(spec, {"objective", "action"})
    with pytest.raises(ValidationError):
        validate_relation_descriptor({**spec, "allowed_pairs": [], "source_types": ["typo"]}, {"objective", "action"})


def test_schema_metadata_edit_requires_admin_and_exact_revision(installed):
    kind = ObjectType.objects.get(workspace=installed[3], key="objective")
    with pytest.raises(PermissionDenied):
        update_metadata(
            actor=replace(installed[5], actor_id=installed[1].pk),
            workspace=installed[3],
            group="types",
            definition_id=kind.pk,
            patch={"name": "No"},
            expected_revision=1,
        )
    with pytest.raises(SchemaConflict):
        update_metadata(
            actor=installed[5],
            workspace=installed[3],
            group="types",
            definition_id=kind.pk,
            patch={"name": "No"},
            expected_revision=0,
        )
    assert schema_revision(installed[3]) == 1


def test_authority_changes_are_distinct_from_schema_revision(client, installed):
    first = client.get(url(installed, "schema/")).data
    WorkspaceMember.objects.filter(workspace=installed[3], member=installed[0]).update(role=5)
    second = client.get(url(installed, "schema/")).data
    assert second["schema_revision"] == first["schema_revision"]
    assert second["authority_revision"] != first["authority_revision"] and not second["can_write"]


def test_upgrade_preview_reports_new_required_field_migration_blocker(installed):
    object_for(installed)
    candidate = package_definitions()
    candidate["properties:objective.new_required"] = {
        "name": "Required",
        "value_type": "string",
        "config": {},
        "is_required": True,
        "is_active": True,
    }
    plan = preview_upgrade(actor=installed[5], workspace=installed[3], expected_revision=1, definitions=candidate)
    assert plan["migration_blockers"][0]["key"] == "properties:objective.new_required"
    with pytest.raises(SchemaConflict):
        upgrade(installed, candidate)
    assert not PropertyDefinition.objects.filter(key="new_required").exists() and schema_revision(installed[3]) == 1


def test_legacy_confirmed_http_intent_replays_without_new_schema_header(installed):
    obj = object_for(installed)
    from plane.radar.commands.semantic import initialize_properties_command

    actor = replace(installed[5], source="radar.session-api", reason="Initialize object defaults")
    confirmed = initialize_properties_command(
        actor=actor,
        workspace=installed[3],
        object_id=obj.pk,
        expected_versions={str(obj.pk): 1},
        idempotency_key="legacy-http-defaults",
    )
    edit(installed, obj.object_type, {"name": "Changed"})
    client = APIClient()
    client.force_authenticate(installed[0])
    response = client.post(
        url(installed, f"objects/{obj.pk}/properties/"),
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="legacy-http-defaults",
        HTTP_X_RADAR_EXPECTED_VERSIONS='{"%s":1}' % obj.pk,
    )
    assert response.status_code == 200 and response.data == confirmed["data"]
    response = client.post(
        url(installed, f"objects/{obj.pk}/properties/"),
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="new-without-header",
        HTTP_X_RADAR_EXPECTED_VERSIONS='{"%s":1}' % obj.pk,
    )
    assert response.status_code == 400


def test_metadata_operations_report_uninitialized_workspace(client, context):
    response = client.post(
        url(context, "schema/"), {"operation": "preview_upgrade", "expected_revision": 0}, format="json"
    )
    assert response.status_code == 409 and response.data["code"] == "schema_not_installed"


def test_invalid_metadata_config_cannot_be_saved_under_a_trusted_audit_context(installed):
    row = PropertyDefinition.objects.get(workspace=installed[3], object_type__key="objective", key="status")
    before = (schema_revision(installed[3]), Provenance.objects.count())

    def operation():
        row.config = {"choices": ["draft"], "default": "wrong"}
        row.save()

    with pytest.raises(ValidationError):
        run_internal(actor=installed[5], workspace=installed[3], name="InvalidConfig", operation=operation)
    row.refresh_from_db()
    assert row.config["default"] == "draft"
    assert (schema_revision(installed[3]), Provenance.objects.count()) == before
