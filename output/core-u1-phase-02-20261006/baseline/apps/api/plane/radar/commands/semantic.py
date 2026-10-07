from rest_framework.exceptions import ValidationError
from plane.radar.models import Object, PropertyDefinition, PropertyValue, Relation
from .actor import Actor
from .compatibility import PendingCommand, invoke
from .execution import authorize, run_internal
from .primitives_semantic import (
    get_active_object,
    active_relations as active_relations,
)
from . import primitives_semantic as primitives


def initialize_semantic_model(*, actor: Actor, workspace):
    return run_internal(
        actor=actor,
        workspace=workspace,
        name="InitializeSemanticModel",
        read=True,
        operation=lambda: primitives.initialize_semantic_model(actor=actor, workspace=workspace),
    )


def initialize_properties_command(*, actor: Actor, workspace, object_id, expected_versions=None, idempotency_key=None):
    """Public defaults intention with the same ledger/replay contract as domain writes."""
    return invoke(
        actor=actor,
        workspace=workspace,
        name="InitializeObjectProperties",
        data={"object_id": object_id},
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )


def initialize_object_properties(*, actor: Actor, workspace, object_id, expected_versions=None, idempotency_key=None):
    """Trusted Python compatibility; transport callers use the confirmed command snapshot."""
    result = initialize_properties_command(
        actor=actor,
        workspace=workspace,
        object_id=object_id,
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    if isinstance(result, PendingCommand):
        return result
    return Object.objects.get(workspace=workspace, pk=result["data"]["object"]["id"])


def _selected(actor, workspace, object_id, definition_id):
    authorize(actor, workspace, "UpdateObject")
    obj = get_active_object(workspace, object_id)
    definition = PropertyDefinition.objects.filter(
        workspace=workspace, object_type=obj.object_type, pk=definition_id, is_active=True
    ).first()
    if definition is None:
        raise ValidationError({"definition": "Unknown active definition for this Object and workspace."})
    return definition


def set_property_value(
    *, actor: Actor, workspace, object_id, definition_id, value, expected_versions=None, idempotency_key=None
):
    definition = _selected(actor, workspace, object_id, definition_id)
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="UpdateObject",
        data={
            "object_id": object_id,
            "set_properties": {definition.key: value},
        },
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    if isinstance(result, PendingCommand):
        return result
    return PropertyValue.objects.get(workspace=workspace, object_id=object_id, definition=definition)


def remove_property_value(
    *, actor: Actor, workspace, object_id, definition_id, expected_versions=None, idempotency_key=None
):
    definition = _selected(actor, workspace, object_id, definition_id)
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="UpdateObject",
        data={
            "object_id": object_id,
            "remove_properties": [definition.key],
        },
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    return result if isinstance(result, PendingCommand) else None


def create_relation(
    *, actor: Actor, workspace, relation_type_id, source_id, target_id, expected_versions=None, idempotency_key=None
):
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="LinkObjects",
        data={
            "source_id": source_id,
            "target_id": target_id,
            "relation_type_id": relation_type_id,
        },
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    if isinstance(result, PendingCommand):
        return result
    return Relation.objects.get(workspace=workspace, pk=result["data"]["relation"]["id"])


def remove_relation(*, actor: Actor, workspace, relation_id, expected_versions=None, idempotency_key=None):
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="UnlinkObjects",
        data={"relation_id": relation_id},
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    return result if isinstance(result, PendingCommand) else None
