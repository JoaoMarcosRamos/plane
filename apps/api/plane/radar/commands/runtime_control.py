"""Explicit, audited provisioning of the CoS trust boundary and canonical identities."""

import hashlib
import re
import secrets
from dataclasses import replace
from uuid import UUID
from rest_framework.exceptions import PermissionDenied, ValidationError
from plane.radar.models import ActorGrant, PersonIdentity, RuntimeCredential
from plane.radar.runtime_identity import bind_identity, runtime_identities
from .control import require_workspace_admin
from .execution import run_internal
from .queries import lookup_object


def bind_runtime_object(*, actor, workspace, object_id, external_id, context, expected_schema_revision=None):
    def operation():
        require_workspace_admin(actor, workspace)
        if not isinstance(external_id, str) or not external_id:
            raise ValidationError({"external_id": "Provisioning requires an explicit external ID."})
        if expected_schema_revision is not None:
            from plane.radar.workspace_schema import check_schema_revision

            check_schema_revision(workspace, expected_schema_revision)
        obj = lookup_object(workspace, object_id, active_person=False)
        return bind_identity(workspace, obj, context, user_id=actor.actor_id, external_id=external_id)

    return run_internal(actor=actor, workspace=workspace, name="RuntimeObjectBound", operation=operation)


def issue_runtime_credential(
    *,
    actor,
    workspace,
    actor_id,
    context,
    external_author,
    reviewer_id,
    person_id,
    is_manager=False,
    object_ids=None,
    channel="telegram",
):
    token = secrets.token_urlsafe(48)

    def operation():
        require_workspace_admin(actor, workspace)
        if not isinstance(actor_id, UUID) or type(is_manager) is not bool:
            raise ValidationError("Use an agent UUID and an explicit manager flag.")
        if channel not in {"telegram", "plane"}:
            raise ValidationError("Use a declared runtime channel.")
        if channel == "telegram" and not re.fullmatch(r"telegram:[1-9][0-9]*", external_author):
            raise ValidationError("Bind an authenticated Telegram author.")
        if channel == "plane" and external_author != f"plane:{reviewer_id}":
            raise ValidationError("Bind the authenticated Plane reviewer.")
        grant = ActorGrant.objects.filter(
            workspace=workspace,
            actor_type="agent",
            actor_id=actor_id,
            delegator_id=reviewer_id,
            is_active=True,
        ).first()
        if grant is None or not grant.commands:
            raise PermissionDenied("Issuing a credential requires an active grant from this reviewer.")
        from .access import require_human_membership

        require_human_membership(replace(actor, actor_type="human", actor_id=reviewer_id), workspace)
        person = lookup_object(workspace, person_id, {"person"})
        identities = runtime_identities(workspace, context)
        if "*" not in grant.object_types:
            identities = identities.filter(object__object_type__key__in=grant.object_types)
        if (
            not identities.filter(object=person).exists()
            or not PersonIdentity.objects.filter(
                workspace=workspace, user_id=reviewer_id, person_id=person_id, is_active=True
            ).exists()
        ):
            raise PermissionDenied("Bind the reviewer to an active Person in this context first.")
        if object_ids is not None:
            if (
                not isinstance(object_ids, list)
                or not all(isinstance(value, str) for value in object_ids)
                or set(object_ids)
                != set(identities.filter(external_id__in=object_ids).values_list("external_id", flat=True))
            ):
                raise ValidationError("Object scope must contain explicit IDs in this context.")
            if not identities.filter(object=person, external_id__in=object_ids).exists():
                raise ValidationError("Object scope must include the authenticated Person.")
        credential = RuntimeCredential.objects.create(
            workspace=workspace,
            channel=channel,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            actor_id=actor_id,
            context=context,
            external_author=external_author,
            reviewer_id=reviewer_id,
            person_id=person_id,
            is_manager=is_manager,
            object_ids=object_ids,
            created_by_id=actor.actor_id,
            updated_by_id=actor.actor_id,
        )
        return credential

    credential = run_internal(actor=actor, workspace=workspace, name="RuntimeCredentialIssued", operation=operation)
    return credential, token
