"""Existing session endpoints are adapters, never an alternative domain writer."""

from dataclasses import dataclass
from uuid import uuid4

from django.db import transaction
from plane.db.models import Workspace
from plane.radar.models import Object, CommandExecution
from .execution import authorize, execute_command
from .handlers import references
from .inputs import INPUTS


@dataclass(frozen=True)
class PendingCommand:
    result: dict


@transaction.atomic
def invoke(*, actor, workspace, name, data, expected_versions=None, idempotency_key=None):
    authorize(actor, workspace, name)
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    serializer = INPUTS[name](data=data)
    serializer.is_valid(raise_exception=True)
    if expected_versions is None:
        # Compatibility for trusted legacy Python callers. New transport clients supply their snapshot.
        previous = (
            CommandExecution.objects.filter(
                workspace=workspace,
                actor_type=actor.actor_type,
                actor_id=actor.actor_id,
                idempotency_key=idempotency_key,
            ).first()
            if idempotency_key
            else None
        )
        if previous is not None:
            expected_versions = previous.envelope["expected_versions"]
        else:
            refs = references(workspace, name, serializer.validated_data)
            expected_versions = {
                str(obj.pk): obj.version for obj in Object.objects.filter(workspace=workspace, pk__in=refs)
            }
    envelope = {
        "command_name": name,
        "command_version": 1,
        "idempotency_key": idempotency_key or str(uuid4()),
        "expected_versions": expected_versions,
        "reason": actor.reason,
        "input": data,
        "assertion": {"kind": "inferred" if actor.confidence is not None else "asserted", "evidence_ids": []},
    }
    if actor.confidence is not None:
        envelope["assertion"]["confidence"] = actor.confidence
    if actor.approval_id is not None:
        envelope["approval_id"] = actor.approval_id
    result = execute_command(actor=actor, workspace=workspace, envelope=envelope)
    return PendingCommand(result) if result["status"] == "pending_approval" else result
