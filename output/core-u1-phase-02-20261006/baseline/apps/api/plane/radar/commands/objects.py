from plane.radar.models import Object
from .actor import Actor
from .compatibility import PendingCommand, invoke
from .execution import run_internal
from .primitives_objects import authorize_primitive as authorize_primitive
from . import primitives_objects as primitives


def initialize_object_types(*, actor: Actor, workspace):
    return run_internal(
        actor=actor,
        workspace=workspace,
        name="InitializeObjectTypes",
        read=True,
        operation=lambda: primitives.initialize_object_types(actor=actor, workspace=workspace),
    )


def create_object(
    *,
    actor: Actor,
    workspace,
    object_type,
    title,
    content=None,
    properties=None,
    expected_versions=None,
    idempotency_key=None,
):
    data = {"object_type_id": object_type, "title": title, "properties": properties or {}}
    if content is not None:
        data["content"] = content
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="CreateObject",
        data=data,
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    if isinstance(result, PendingCommand):
        return result
    return Object.objects.get(workspace=workspace, pk=result["data"]["object"]["id"])


def update_object(
    *,
    actor: Actor,
    workspace,
    object_id,
    changes,
    set_properties=None,
    remove_properties=None,
    expected_versions=None,
    idempotency_key=None,
):
    result = invoke(
        actor=actor,
        workspace=workspace,
        name="UpdateObject",
        data={
            "object_id": object_id,
            "changes": changes,
            "set_properties": set_properties or {},
            "remove_properties": remove_properties or [],
        },
        expected_versions=expected_versions,
        idempotency_key=idempotency_key,
    )
    if isinstance(result, PendingCommand):
        return result
    return Object.objects.get(workspace=workspace, pk=object_id)
