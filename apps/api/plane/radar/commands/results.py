"""Typed application read models; no dependency on HTTP/API serializers.

The version-1 representation is preserved for persisted command results/replays.
Adapters may extend their read responses without changing historical executions.
"""

from datetime import datetime
from typing import Any, TypedDict
from django.utils import timezone
from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, Relation, RelationType


class AuditResult(TypedDict):
    id: str
    workspace: str
    created_at: str
    updated_at: str
    created_by: str | None
    updated_by: str | None


class ObjectTypeResult(AuditResult):
    key: str
    name: str
    description: str
    icon: str
    rules: dict
    is_system: bool
    is_active: bool


class ObjectResult(AuditResult):
    object_type: str
    object_type_detail: ObjectTypeResult
    title: str
    content: str
    version: int


class RelationTypeResult(AuditResult):
    key: str
    forward_label: str
    reverse_label: str
    description: str
    source_types: list[str]
    target_types: list[str]
    allowed_pairs: list[list[str]]
    cardinality: str
    allow_self: bool
    is_system: bool
    is_active: bool


class RelationResult(AuditResult):
    relation_type: str
    relation_type_detail: RelationTypeResult
    source: str
    target: str


class PropertyDefinitionResult(AuditResult):
    object_type: str
    key: str
    name: str
    value_type: str
    config: dict
    is_required: bool
    is_active: bool
    is_system: bool


class PropertyValueResult(AuditResult):
    object: str
    definition: str
    value: Any


class PropertyRowResult(TypedDict):
    definition: PropertyDefinitionResult
    stored_value: PropertyValueResult | None
    value: Any
    has_value: bool


class PropertySnapshotResult(TypedDict):
    schema_revision: int
    object: ObjectResult
    properties: list[PropertyRowResult]


def result_timestamp(value: datetime) -> str:
    """Preserve the v1 ISO representation, including the current timezone and UTC Z."""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.isoformat().replace("+00:00", "Z")


def audit_result(item) -> AuditResult:
    return {
        "id": str(item.pk),
        "workspace": str(item.workspace_id),
        "created_at": result_timestamp(item.created_at),
        "updated_at": result_timestamp(item.updated_at),
        "created_by": str(item.created_by_id) if item.created_by_id else None,
        "updated_by": str(item.updated_by_id) if item.updated_by_id else None,
    }


def object_type_result(item: ObjectType) -> ObjectTypeResult:
    return {
        **audit_result(item),
        "key": item.key,
        "name": item.name,
        "description": item.description,
        "icon": item.icon,
        "rules": item.rules,
        "is_system": item.is_system,
        "is_active": item.is_active,
    }


def object_data(item: Object) -> ObjectResult:
    return {
        **audit_result(item),
        "object_type": str(item.object_type_id),
        "object_type_detail": object_type_result(item.object_type),
        "title": item.title,
        "content": item.content,
        "version": item.version,
    }


def object_result(item: Object) -> dict[str, ObjectResult]:
    item.refresh_from_db()
    return {"object": object_data(item)}


def relation_type_result(item: RelationType) -> RelationTypeResult:
    return {
        **audit_result(item),
        "key": item.key,
        "forward_label": item.forward_label,
        "reverse_label": item.reverse_label,
        "description": item.description,
        "source_types": item.source_types,
        "target_types": item.target_types,
        "allowed_pairs": item.allowed_pairs,
        "cardinality": item.cardinality,
        "allow_self": item.allow_self,
        "is_system": item.is_system,
        "is_active": item.is_active,
    }


def relation_result(item: Relation) -> RelationResult:
    return {
        **audit_result(item),
        "relation_type": str(item.relation_type_id),
        "relation_type_detail": relation_type_result(item.relation_type),
        "source": str(item.source_id),
        "target": str(item.target_id),
    }


def definition_result(item: PropertyDefinition) -> PropertyDefinitionResult:
    return {
        **audit_result(item),
        "object_type": str(item.object_type_id),
        "key": item.key,
        "name": item.name,
        "value_type": item.value_type,
        "config": item.config,
        "is_required": item.is_required,
        "is_active": item.is_active,
        "is_system": item.is_system,
    }


def property_value_result(item: PropertyValue) -> PropertyValueResult:
    return {
        **audit_result(item),
        "object": str(item.object_id),
        "definition": str(item.definition_id),
        "value": item.value,
    }


def property_snapshot_result(item: Object) -> PropertySnapshotResult:
    values = {
        value.definition_id: value
        for value in PropertyValue.objects.filter(
            workspace_id=item.workspace_id, object=item, definition__is_active=True, definition__deleted_at__isnull=True
        )
    }
    rows: list[PropertyRowResult] = []
    for definition in PropertyDefinition.objects.filter(
        workspace_id=item.workspace_id, object_type_id=item.object_type_id, is_active=True
    ):
        value = values.get(definition.pk)
        rows.append(
            {
                "definition": definition_result(definition),
                "stored_value": property_value_result(value) if value else None,
                "value": value.value if value else definition.config.get("default"),
                "has_value": value is not None or "default" in definition.config,
            }
        )
    from plane.radar.workspace_schema import schema_revision

    return {"schema_revision": schema_revision(item.workspace_id), "object": object_data(item), "properties": rows}
