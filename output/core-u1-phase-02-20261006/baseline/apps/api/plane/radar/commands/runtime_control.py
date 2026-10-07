"""Explicit, audited provisioning of the CoS trust boundary and canonical identities."""

import hashlib
import re
import secrets
from uuid import UUID
from rest_framework.exceptions import PermissionDenied, ValidationError
from plane.radar.models import PersonIdentity, RuntimeCredential, RuntimeObjectIdentity
from plane.radar.ontology.schema import load_schema
from .control import require_workspace_admin
from .execution import run_internal
from .queries import lookup_object


def bind_runtime_object(*, actor, workspace, object_id, external_id, context):
    def operation():
        require_workspace_admin(actor, workspace)
        obj = lookup_object(workspace, object_id, active_person=False)
        spec = load_schema()["object_types"].get(obj.object_type.key)
        if spec is None:
            raise ValidationError("This Object type has no canonical runtime identity contract.")
        prefix = spec["prefix"]
        from .primitives_semantic import validate_required_relations

        validate_required_relations(obj, context=context)
        if not re.fullmatch(r"(company|manager):[A-Za-z0-9_.-]+", context) or not re.fullmatch(
            prefix + r"-\d{8}-[A-Z0-9]{6}", external_id
        ):
            raise ValidationError("Use a declared context and a canonical ID matching the Object type.")
        existing = RuntimeObjectIdentity.objects.filter(workspace=workspace, object=obj).first()
        if existing:
            if existing.external_id != external_id or existing.context != context:
                raise ValidationError("Runtime identity is immutable.")
            return existing
        return RuntimeObjectIdentity.objects.create(
            workspace=workspace,
            object=obj,
            external_id=external_id,
            context=context,
            created_by_id=actor.actor_id,
            updated_by_id=actor.actor_id,
        )

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
        if (
            not RuntimeObjectIdentity.objects.filter(workspace=workspace, object_id=person_id, context=context).exists()
            or not PersonIdentity.objects.filter(
                workspace=workspace, user_id=reviewer_id, person_id=person_id, is_active=True
            ).exists()
        ):
            raise PermissionDenied("Bind the reviewer to an active Person in this context first.")
        if object_ids is not None:
            if not isinstance(object_ids, list) or set(object_ids) != set(
                RuntimeObjectIdentity.objects.filter(
                    workspace=workspace, context=context, external_id__in=object_ids
                ).values_list("external_id", flat=True)
            ):
                raise ValidationError("Object scope must contain explicit IDs in this context.")
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
