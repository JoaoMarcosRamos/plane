from collections.abc import Mapping
from typing import Any
from uuid import UUID
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from plane.db.models import User, Workspace, WorkspaceMember
from plane.utils.content_validator import validate_html_content
from plane.radar.models import Object, ObjectType
from plane.radar.ontology.schema import load_schema
from .actor import Actor

SYSTEM_TYPES = tuple((key, spec["label"]) for key, spec in load_schema()["object_types"].items())


def _authorize(actor: Actor, workspace: Workspace, *, write: bool = True) -> UUID | None:
    from plane.radar.mutation import current_mutation

    context = current_mutation.get()
    if context is not None:
        if context.actor != actor or context.workspace_id != workspace.pk:
            raise PermissionDenied("Nested primitives must preserve Actor and workspace.")
        return actor.actor_id if actor.actor_type == "human" else None
    if write:
        raise PermissionDenied("Domain primitives must be invoked through the command layer.")
    if actor.actor_type != "human" or not actor.source.strip() or not actor.reason.strip():
        raise PermissionDenied("An explicit human actor with source and reason is required.")
    if not Workspace.objects.filter(pk=workspace.pk).exists():
        raise NotFound("Workspace not found.")
    if not User.objects.filter(pk=actor.actor_id, is_active=True, is_bot=False).exists():
        raise PermissionDenied("Human actor is not active.")
    roles = [15, 20] if write else [5, 15, 20]
    if not WorkspaceMember.objects.filter(
        workspace_id=workspace.pk, member_id=actor.actor_id, role__in=roles, is_active=True
    ).exists():
        raise PermissionDenied("Workspace membership does not permit this operation.")
    return actor.actor_id


def _type(workspace: Workspace, type_id: UUID) -> ObjectType:
    try:
        return ObjectType.objects.get(pk=type_id, workspace_id=workspace.pk, is_active=True)
    except ObjectType.DoesNotExist:
        raise ValidationError({"object_type": "Select an active type from this workspace."})


def _title(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 255:
        raise ValidationError({"title": "Title must contain 1–255 characters."})
    return value.strip()


def _content(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError({"content": "Content must be HTML text."})
    valid, error, clean = validate_html_content(value)
    if not valid:
        raise ValidationError({"content": error})
    return clean or ""


@transaction.atomic
def initialize_object_types(*, actor: Actor, workspace: Workspace) -> list[ObjectType]:
    from plane.radar.mutation import current_mutation

    if current_mutation.get() is None:
        raise PermissionDenied("Schema initialization requires an audited command context.")
    user_id = _authorize(actor, workspace, write=False)
    # Serialize initialization per tenant, including concurrent first accesses.
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    for key, name in SYSTEM_TYPES:
        ObjectType.objects.get_or_create(
            workspace=workspace,
            key=key,
            defaults={
                "name": name,
                "is_system": True,
                "created_by_id": user_id,
                "updated_by_id": user_id,
                "rules": {
                    "invariants": [
                        {field: value for field, value in rule.items() if field != "class"}
                        for rule in load_schema()["invariants"]
                        if rule["class"] == key
                    ]
                },
            },
        )
    return list(ObjectType.objects.filter(workspace=workspace, is_active=True))


@transaction.atomic
def create_object(
    *,
    actor: Actor,
    workspace: Workspace,
    object_type: UUID,
    title: str,
    content: str | None = None,
    initial_values: Mapping[str, Any] | None = None,
) -> Object:
    user_id = _authorize(actor, workspace)
    from .primitives_semantic import initialize_semantic_model, materialize_defaults

    if actor.actor_type == "human":
        initialize_semantic_model(actor=actor, workspace=workspace)
    selected_type = _type(workspace, object_type)
    result = Object(
        workspace=workspace,
        object_type=selected_type,
        title=_title(title),
        content=_content(content),
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    result.save()
    if initial_values:
        from plane.radar.models import PropertyDefinition, PropertyValue
        from .primitives_semantic import validate_value

        for key, value in initial_values.items():
            definition = PropertyDefinition.objects.filter(
                workspace=workspace, object_type=selected_type, key=key, is_active=True
            ).first()
            if definition is None:
                raise ValidationError({key: "Unknown property for this object type."})
            PropertyValue.objects.create(
                workspace=workspace,
                object=result,
                definition=definition,
                value=validate_value(definition, value, workspace),
                created_by_id=user_id,
                updated_by_id=user_id,
            )
    materialize_defaults(result, user_id)
    # Future events/outbox belong here, inside this transaction.
    return result


@transaction.atomic
def update_object(*, actor: Actor, workspace: Workspace, object_id: UUID, changes: Mapping[str, Any]) -> Object:
    user_id = _authorize(actor, workspace)
    if set(changes) - {"title", "content", "object_type"} or not changes:
        raise ValidationError("Provide title, content or object_type; audit fields are read-only.")
    try:
        result = Object.objects.select_for_update().get(pk=object_id, workspace=workspace)
    except Object.DoesNotExist:
        raise NotFound("Object not found in this workspace.")
    selected_type = _type(workspace, changes.get("object_type", result.object_type_id))
    if "title" in changes:
        result.title = _title(changes["title"])
    if "content" in changes:
        result.content = _content(changes["content"])
    if selected_type.pk != result.object_type_id:
        from .primitives_semantic import assert_type_change_safe

        assert_type_change_safe(result)
    result.object_type = selected_type
    result.updated_by_id = user_id
    result.version += 1
    result.save(update_fields=["title", "content", "object_type", "updated_by", "updated_at", "version"])
    return result
