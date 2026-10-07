import math
from datetime import date, datetime
from uuid import UUID
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email, URLValidator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.models import Object, PropertyDefinition, PropertyValue, RelationType, Relation
from plane.radar.ontology.schema import load_schema
from .actor import Actor
from .primitives_objects import _authorize


def validate_value(definition: PropertyDefinition, value, workspace: Workspace):
    kind, config = definition.value_type, definition.config
    valid = False
    if kind in {"string", "email", "uri", "enum", "date", "datetime", "user"}:
        valid = isinstance(value, str)
    elif kind == "string_list":
        valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
    elif kind == "boolean":
        valid = type(value) is bool
    elif kind == "integer":
        valid = type(value) is int
    elif kind == "number":
        valid = type(value) is int or type(value) is float and math.isfinite(value)
    if not valid:
        raise ValidationError({definition.key: f"Expected {kind}; null requires removal."})
    try:
        if kind == "enum" and value not in config.get("choices", []):
            raise ValueError("Select a declared vocabulary value.")
        if kind in {"number", "integer"}:
            if "min" in config and value < config["min"] or "max" in config and value > config["max"]:
                raise ValueError("Value outside the configured range.")
        if kind == "date":
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Use YYYY-MM-DD.")
        if kind == "datetime":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or "T" not in value:
                raise ValueError("Use ISO datetime with timezone.")
        if kind == "email":
            validate_email(value)
        if kind == "uri":
            URLValidator(schemes=["https", "http", "ftp", "ftps"])(value)
        if kind == "user":
            user_id = UUID(value)
            if not User.objects.filter(pk=user_id, is_active=True, is_bot=False).exists() or not (
                WorkspaceMember.objects.filter(workspace=workspace, member_id=user_id, is_active=True).exists()
            ):
                raise ValueError("Select an active human workspace member.")
    except (ValueError, TypeError, OverflowError, DjangoValidationError) as exc:
        raise ValidationError({definition.key: str(exc)}) from exc
    return value


@transaction.atomic
def initialize_semantic_model(*, actor: Actor, workspace: Workspace):
    from .primitives_objects import initialize_object_types

    user_id = _authorize(actor, workspace, write=False)
    types = {item.key: item for item in initialize_object_types(actor=actor, workspace=workspace)}
    schema = load_schema()
    for key, spec in schema["object_types"].items():
        selected = types.get(key)
        if selected is None:
            continue  # Never reactivate a deliberately inactive type.
        attributes = {"status": {"type": "enum", **spec["status"]}, **spec["attributes"]}
        for prop_key, prop in attributes.items():
            config = {k: v for k, v in prop.items() if k in {"default", "min", "max", "terminal"}}
            if "vocabulary" in prop:
                config["choices"] = schema["vocabularies"][prop["vocabulary"]]
            PropertyDefinition.objects.get_or_create(
                workspace=workspace,
                object_type=selected,
                key=prop_key,
                defaults={
                    "name": prop_key,
                    "value_type": prop["type"],
                    "config": config,
                    "is_required": prop.get("required", False),
                    "is_system": True,
                    "created_by_id": user_id,
                    "updated_by_id": user_id,
                },
            )
    for key, spec in schema["link_types"].items():
        RelationType.objects.get_or_create(
            workspace=workspace,
            key=key,
            defaults={
                "forward_label": spec["roles"]["source"],
                "reverse_label": spec["roles"]["target"],
                "description": spec["description"],
                "source_types": spec["domain"],
                "target_types": spec["codomain"],
                "allowed_pairs": spec.get("allowed_pairs", []),
                "cardinality": spec["cardinality"],
                "allow_self": spec["constraints"]["self_link"],
                "is_system": True,
                "created_by_id": user_id,
                "updated_by_id": user_id,
            },
        )


def _object(workspace: Workspace, object_id: UUID, *, lock=False) -> Object:
    queryset = Object.objects.select_related("object_type")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(
            pk=object_id,
            workspace=workspace,
            object_type__workspace=workspace,
            object_type__is_active=True,
            object_type__deleted_at__isnull=True,
        )
    except Object.DoesNotExist:
        raise NotFound("Active object not found in this workspace.")


def _definition(workspace: Workspace, obj: Object, definition_id: UUID) -> PropertyDefinition:
    try:
        return PropertyDefinition.objects.get(
            pk=definition_id, workspace=workspace, object_type_id=obj.object_type_id, is_active=True
        )
    except PropertyDefinition.DoesNotExist:
        raise ValidationError({"definition": "Select an active definition for this object type and workspace."})


def _touch(objects: list[Object], user_id: UUID):
    from plane.radar.mutation import current_mutation

    context = current_mutation.get()
    for obj in {item.pk: item for item in objects}.values():
        if context is not None:
            if obj.pk in context.created_objects or obj.pk in context.touched:
                continue
            context.touched.add(obj.pk)
            obj.refresh_from_db(fields=["version"])
        obj.version += 1
        obj.updated_by_id = user_id
        obj.save(update_fields=["version", "updated_by", "updated_at"])


def materialize_defaults(obj: Object, user_id: UUID) -> bool:
    changed = False
    for definition in PropertyDefinition.objects.filter(
        workspace_id=obj.workspace_id, object_type_id=obj.object_type_id, is_active=True
    ):
        if definition.is_required and "default" not in definition.config:
            if not PropertyValue.objects.filter(object=obj, definition=definition).exists():
                raise ValidationError({definition.key: "Required property has no value or configured default."})
        if "default" in definition.config:
            value = validate_value(definition, definition.config["default"], obj.workspace)
            _, created = PropertyValue.objects.get_or_create(
                workspace_id=obj.workspace_id,
                object=obj,
                definition=definition,
                defaults={"value": value, "created_by_id": user_id, "updated_by_id": user_id},
            )
            changed |= created
    return changed


@transaction.atomic
def initialize_object_properties(*, actor: Actor, workspace: Workspace, object_id: UUID) -> Object:
    user_id = _authorize(actor, workspace)
    initialize_semantic_model(actor=actor, workspace=workspace)
    obj = _object(workspace, object_id, lock=True)
    changed = materialize_defaults(obj, user_id)
    changed = patch_properties(actor=actor, workspace=workspace, obj=obj, values={}) or changed
    if changed:
        _touch([obj], user_id)
    return obj


def property_definitions(obj: Object) -> dict:
    return {
        item.key: item
        for item in PropertyDefinition.objects.filter(
            workspace_id=obj.workspace_id, object_type_id=obj.object_type_id, is_active=True
        )
    }


def effective_values(obj: Object) -> dict:
    definitions = property_definitions(obj)
    values = {key: item.config["default"] for key, item in definitions.items() if "default" in item.config}
    values.update(
        {
            item.definition.key: item.value
            for item in PropertyValue.objects.filter(
                workspace_id=obj.workspace_id, object=obj, definition_id__in=[d.pk for d in definitions.values()]
            ).select_related("definition")
        }
    )
    return values


def plan_properties(obj: Object, values: dict, remove=()) -> tuple[dict, dict, set[str]]:
    from .rules import effective_invariants, evaluate_invariants

    definitions = property_definitions(obj)
    effective = effective_values(obj)
    for key, value in values.items():
        if key not in definitions:
            raise ValidationError({key: "Unknown property for this Object type."})
        effective[key] = validate_value(definitions[key], value, obj.workspace)
    for key in remove:
        definition = definitions.get(key)
        if definition is None or definition.is_required or "default" in definition.config:
            raise ValidationError({key: "Cannot remove a required/defaulted or unknown property."})
        effective.pop(key, None)
    invariants = effective_invariants(obj.object_type, definitions)
    derived = evaluate_invariants(invariants, effective, values)
    if set(remove).intersection(derived):
        raise ValidationError({"rules": "Derived properties cannot be removed independently."})
    return definitions, {**values, **derived}, set(derived)


def property_effect_fields(obj: Object, values: dict, remove=()) -> set[str]:
    from .rules import derived_fields

    definitions, changes, derived = plan_properties(obj, values, remove)
    fields = set(values) | set(remove) | derived_fields(obj.object_type, definitions, set(values) | set(remove))
    stored = {
        item.definition.key: item.value
        for item in PropertyValue.objects.filter(
            workspace_id=obj.workspace_id, object=obj, definition_id__in=[d.pk for d in definitions.values()]
        ).select_related("definition")
    }
    fields.update(key for key in derived if key not in stored or stored[key] != changes[key])
    return fields


@transaction.atomic
def patch_properties(*, actor: Actor, workspace: Workspace, obj: Object, values: dict, remove=()) -> bool:
    user_id = _authorize(actor, workspace)
    definitions, changes, _ = plan_properties(obj, values, remove)
    if "status" in values and values["status"] != effective_values(obj).get("status"):
        validate_required_relations(obj)
    changed = False
    for key, value in changes.items():
        definition = definitions[key]
        value = validate_value(definition, value, workspace)
        stored = PropertyValue.objects.filter(workspace=workspace, object=obj, definition=definition).first()
        if stored is None:
            PropertyValue.objects.create(
                workspace=workspace,
                object=obj,
                definition=definition,
                value=value,
                created_by_id=user_id,
                updated_by_id=user_id,
            )
            changed = True
        elif stored.value != value:
            stored.value, stored.updated_by_id = value, user_id
            stored.save(update_fields=["value", "updated_by", "updated_at"])
            changed = True
    for key in remove:
        stored = PropertyValue.objects.filter(workspace=workspace, object=obj, definition=definitions[key]).first()
        if stored:
            stored.deleted_at, stored.updated_by_id = timezone.now(), user_id
            stored.save(update_fields=["deleted_at", "updated_by", "updated_at"])
            changed = True
    if changed:
        _touch([obj], user_id)
    return changed


@transaction.atomic
def set_property_value(
    *, actor: Actor, workspace: Workspace, object_id: UUID, definition_id: UUID, value
) -> PropertyValue:
    _authorize(actor, workspace)
    obj = _object(workspace, object_id, lock=True)
    definition = _definition(workspace, obj, definition_id)
    patch_properties(actor=actor, workspace=workspace, obj=obj, values={definition.key: value})
    return PropertyValue.objects.get(workspace=workspace, object=obj, definition=definition)


@transaction.atomic
def remove_property_value(*, actor: Actor, workspace: Workspace, object_id: UUID, definition_id: UUID):
    _authorize(actor, workspace)
    obj = _object(workspace, object_id, lock=True)
    definition = _definition(workspace, obj, definition_id)
    patch_properties(actor=actor, workspace=workspace, obj=obj, values={}, remove=[definition.key])


def _endpoints(workspace: Workspace, source_id: UUID, target_id: UUID) -> tuple[Object, Object]:
    # Stable global ordering avoids deadlocks for reverse concurrent edges.
    objects = {
        obj.pk: obj
        for obj in Object.objects.select_for_update(of=("self",))
        .select_related("object_type")
        .filter(
            workspace=workspace,
            pk__in=[source_id, target_id],
            object_type__workspace=workspace,
            object_type__is_active=True,
            object_type__deleted_at__isnull=True,
        )
        .order_by("pk")
    }
    try:
        return objects[source_id], objects[target_id]
    except KeyError:
        raise NotFound("Active relation endpoints not found in this workspace.")


@transaction.atomic
def create_relation(
    *, actor: Actor, workspace: Workspace, relation_type_id: UUID, source_id: UUID, target_id: UUID
) -> Relation:
    user_id = _authorize(actor, workspace)
    source, target = _endpoints(workspace, source_id, target_id)
    try:
        kind = RelationType.objects.get(pk=relation_type_id, workspace=workspace, is_active=True)
    except RelationType.DoesNotExist:
        raise ValidationError({"relation_type": "Select an active relation type from this workspace."})
    pair = [source.object_type.key, target.object_type.key]
    if (
        pair[0] not in kind.source_types
        and "*" not in kind.source_types
        or pair[1] not in kind.target_types
        and "*" not in kind.target_types
        or kind.allowed_pairs
        and pair not in kind.allowed_pairs
        or source.pk == target.pk
        and not kind.allow_self
    ):
        raise ValidationError({"relation_type": "Invalid source/target pair or self-link."})
    existing = Relation.objects.filter(workspace=workspace, relation_type=kind, source=source, target=target).first()
    if existing:
        return existing
    if (
        kind.cardinality in {"0..1", "1..1"}
        and Relation.objects.filter(workspace=workspace, relation_type=kind, source=source).exists()
    ):
        raise ValidationError({"relation_type": "Outgoing cardinality is limited to one target."})
    result = Relation.objects.create(
        workspace=workspace,
        relation_type=kind,
        source=source,
        target=target,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
    _touch([source, target], user_id)
    return result


@transaction.atomic
def remove_relation(*, actor: Actor, workspace: Workspace, relation_id: UUID):
    user_id = _authorize(actor, workspace)
    try:
        result = Relation.objects.get(pk=relation_id, workspace=workspace)
    except Relation.DoesNotExist:
        raise NotFound("Relation not found in this workspace.")
    source, target = _endpoints(workspace, result.source_id, result.target_id)
    if result.relation_type.cardinality == "1..1":
        raise ValidationError("A mandatory relation cannot be removed independently.")
    # Re-check after acquiring endpoint locks: concurrent delete must not double bump.
    result = Relation.objects.filter(pk=relation_id, workspace=workspace).first()
    if result:
        result.deleted_at = timezone.now()
        result.updated_by_id = user_id
        result.save(update_fields=["deleted_at", "updated_by", "updated_at"])
        _touch([source, target], user_id)


def active_relations(workspace: Workspace):
    return Relation.objects.filter(
        workspace=workspace,
        relation_type__is_active=True,
        relation_type__deleted_at__isnull=True,
        source__workspace=workspace,
        target__workspace=workspace,
        relation_type__workspace=workspace,
        source__object_type__workspace=workspace,
        target__object_type__workspace=workspace,
        source__deleted_at__isnull=True,
        target__deleted_at__isnull=True,
        source__object_type__is_active=True,
        target__object_type__is_active=True,
        source__object_type__deleted_at__isnull=True,
        target__object_type__deleted_at__isnull=True,
    ).select_related("relation_type")


def assert_type_change_safe(obj: Object):
    if (
        PropertyValue.objects.filter(object=obj).exists()
        or Relation.objects.filter(Q(source=obj) | Q(target=obj)).exists()
    ):
        raise ValidationError({"object_type": "Cannot change type while active properties or relations exist."})


def validate_required_relations(obj: Object, *, context: str | None = None) -> None:
    """Objects may assemble links; minimum cardinality applies at lifecycle/binding boundaries."""
    from plane.radar.models import RuntimeObjectIdentity

    for kind in RelationType.objects.filter(workspace_id=obj.workspace_id, is_active=True, cardinality="1..1"):
        if obj.object_type.key not in kind.source_types and "*" not in kind.source_types:
            continue
        if kind.allowed_pairs and not any(pair[0] == obj.object_type.key for pair in kind.allowed_pairs):
            continue
        edges = list(
            active_relations(obj.workspace)
            .filter(source=obj, relation_type=kind)
            .select_related("source__object_type", "target__object_type")
        )
        if len(edges) != 1:
            raise ValidationError({"relation_type": f"{kind.key} requires exactly one active target."})
        target = edges[0].target
        pair = [obj.object_type.key, target.object_type.key]
        if (
            target.object_type.key not in kind.target_types
            and "*" not in kind.target_types
            or kind.allowed_pairs
            and pair not in kind.allowed_pairs
            or target.pk == obj.pk
            and not kind.allow_self
        ):
            raise ValidationError({"relation_type": f"{kind.key} has an invalid target."})
        if (
            context is not None
            and not RuntimeObjectIdentity.objects.filter(
                workspace_id=obj.workspace_id, object=target, context=context
            ).exists()
        ):
            raise ValidationError({"relation_type": f"{kind.key} target must be bound in the same context."})
