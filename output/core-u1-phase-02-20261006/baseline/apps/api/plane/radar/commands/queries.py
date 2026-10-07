"""Public domain queries/validation shared by commands and authenticated adapters."""

from uuid import UUID
from collections.abc import Collection
from django.utils.html import strip_tags
from rest_framework.exceptions import ValidationError
from plane.db.models import Workspace
from plane.radar.models import Object, DecisionApproval, Relation
from . import primitives_semantic as semantic


def lookup_object(
    workspace: Workspace, pk: UUID, types: Collection[str] | None = None, *, active_person: bool = True
) -> Object:
    obj = semantic.get_active_object(workspace, pk)
    if types is not None and obj.object_type.key not in types:
        raise ValidationError("Object type does not satisfy this command.")
    if active_person and obj.object_type.key == "person" and effective_values(obj).get("status") != "active":
        raise ValidationError("Select an active Person.")
    return obj


def effective_values(obj: Object) -> dict:
    return semantic.effective_values(obj)


def decision_evidence_ids(workspace: Workspace, decision_id: UUID) -> set[UUID]:
    return set(
        Relation.objects.filter(
            workspace=workspace,
            source_id=decision_id,
            relation_type__key="informed_by",
            relation_type__is_active=True,
            target__object_type__key="document",
            target__deleted_at__isnull=True,
        ).values_list("target_id", flat=True)
    )


def current_decision_approval(workspace: Workspace, obj: Object) -> DecisionApproval | None:
    return (
        DecisionApproval.objects.filter(
            workspace=workspace, decision=obj, is_stale=False, resulting_version=obj.version
        )
        .order_by("-created_at")
        .first()
    )


def validate_evidence(obj: Object) -> None:
    values = effective_values(obj)
    if (
        obj.object_type.key != "document"
        or values.get("status") == "archived"
        or not (strip_tags(obj.content).strip() or values.get("uri"))
    ):
        raise ValidationError({"evidence": "Use a live Document with content or a source URI."})
