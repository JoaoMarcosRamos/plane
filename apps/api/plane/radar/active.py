"""Current operational policy. Historical reads must opt into all_objects explicitly."""

from django.db import models
from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, RelationType, Relation


def active_types(workspace):
    return ObjectType.objects.filter(workspace=workspace, is_active=True)


def active_objects(workspace):
    return Object.objects.filter(
        workspace=workspace,
        object_type__workspace=workspace,
        object_type__is_active=True,
        object_type__deleted_at__isnull=True,
    )


def active_definitions(workspace):
    return PropertyDefinition.objects.filter(
        workspace=workspace,
        object_type__workspace=workspace,
        is_active=True,
        object_type__is_active=True,
        object_type__deleted_at__isnull=True,
    )


def active_values(workspace):
    return PropertyValue.objects.filter(
        workspace=workspace,
        definition__workspace=workspace,
        object__workspace=workspace,
        definition__is_active=True,
        definition__deleted_at__isnull=True,
        definition__object_type__workspace=workspace,
        definition__object_type__is_active=True,
        definition__object_type__deleted_at__isnull=True,
        object__deleted_at__isnull=True,
        object__object_type__workspace=workspace,
        object__object_type__is_active=True,
        object__object_type__deleted_at__isnull=True,
        object__object_type_id=models.F("definition__object_type_id"),
    )


def active_relation_types(workspace):
    return RelationType.objects.filter(workspace=workspace, is_active=True)


def active_relations(workspace):
    return Relation.objects.filter(
        workspace=workspace,
        relation_type__is_active=True,
        relation_type__deleted_at__isnull=True,
        relation_type__workspace=workspace,
        source_id__in=active_objects(workspace).values("pk"),
        target_id__in=active_objects(workspace).values("pk"),
    ).select_related("relation_type")
