"""Workspace installation state and transactional revision coordination."""

from copy import deepcopy
from plane.db.models import Workspace
from plane.radar.models import ObjectType, PropertyDefinition, RelationType, WorkspaceSchemaState
from plane.radar.ontology.package import package_definitions
from rest_framework.exceptions import APIException

METADATA_MODELS = {"radar.ObjectType", "radar.PropertyDefinition", "radar.RelationType"}
MODELS = {"types": ObjectType, "properties": PropertyDefinition, "relations": RelationType}


class SchemaConflict(APIException):
    status_code = 409
    default_code = "schema_conflict"


def schema_revision(workspace):
    workspace_id = getattr(workspace, "pk", workspace)
    return (
        WorkspaceSchemaState.objects.filter(workspace_id=workspace_id).values_list("revision", flat=True).first() or 0
    )


def lock_schema(workspace):
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    return schema_revision(workspace)


def require_schema(workspace):
    if not schema_revision(workspace):
        raise SchemaConflict({"code": "schema_not_installed", "detail": "Install the workspace schema explicitly."})


def check_schema_revision(workspace, expected):
    if type(expected) is not int or expected != schema_revision(workspace):
        raise SchemaConflict({"code": "schema_revision_conflict", "schema_revision": schema_revision(workspace)})


def metadata_records(workspace):
    records = {}
    for group, model in MODELS.items():
        queryset = model.all_objects.filter(workspace=workspace)
        if group == "properties":
            queryset = queryset.select_related("object_type")
        for row in queryset.order_by("created_at", "id"):
            key = f"{row.object_type.key}.{row.key}" if group == "properties" else row.key
            record_key = f"{group}:{key}"
            # Keep the latest replacement; installed IDs separately preserve intentional deletion.
            records[record_key] = row
    return records


def record_spec(row, fields):
    return {field: deepcopy(getattr(row, field)) for field in fields}


def legacy_base(workspace):
    definitions = package_definitions()
    records = metadata_records(workspace)
    ids, divergences = {}, []
    for key, spec in definitions.items():
        row = records.get(key)
        if row is None or not row.is_system:
            divergences.append({"key": key, "reason": "missing" if row is None else "unmanaged"})
            continue
        ids[key] = str(row.pk)
        local = record_spec(row, spec)
        if local != spec or row.deleted_at:
            divergences.append(
                {"key": key, "reason": "local_difference", "local": local, "deleted": bool(row.deleted_at)}
            )
    return {"definitions": definitions, "ids": ids}, divergences


def advance_schema_revision(context):
    """Called once before provenance flush, under the existing workspace transaction lock."""
    changed = any(change["model"] in METADATA_MODELS for change in context.changes.values())
    if not changed:
        return
    state = WorkspaceSchemaState.objects.filter(workspace_id=context.workspace_id).first()
    if state is None:
        # Trusted legacy local metadata commands are baselined without claiming a package install.
        workspace = Workspace.objects.get(pk=context.workspace_id)
        base, divergences = legacy_base(workspace)
        state = WorkspaceSchemaState(workspace=workspace, origin="legacy", installed_base=base, divergences=divergences)
    elif ("radar.WorkspaceSchemaState", state.pk) not in context.changes or context.changes[
        ("radar.WorkspaceSchemaState", state.pk)
    ]["before"] is not None:
        state.revision += 1
    state.updated_by_id = context.actor.actor_id if context.actor.actor_type == "human" else None
    state.save()
