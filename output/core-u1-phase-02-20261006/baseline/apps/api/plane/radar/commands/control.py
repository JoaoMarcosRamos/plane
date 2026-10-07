"""Explicit human provisioning and review, audited through the same transaction layer."""

from uuid import UUID
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from plane.db.models import User, WorkspaceMember
from plane.radar.models import ActorGrant, CommandApproval, CommandExecution, PersonIdentity
from .execution import (
    require_human_membership,
    lock_expected_versions,
    authorize,
    CommandConflict,
    emit,
    run_internal,
    schema_fingerprint,
)
from .handlers import check_grant, references
from .queries import lookup_object
from .inputs import INPUTS


def require_workspace_admin(actor, workspace):
    require_human_membership(actor, workspace)
    if (
        workspace.owner_id != actor.actor_id
        and not WorkspaceMember.objects.filter(
            workspace=workspace, member_id=actor.actor_id, role=20, is_active=True
        ).exists()
    ):
        raise PermissionDenied("Only the workspace owner or admin may provision RADAR authority.")


def register_actor_grant(
    *,
    actor,
    workspace,
    actor_type,
    actor_id,
    delegator_id,
    commands,
    object_types,
    fields,
    requires_approval=True,
    is_active=True,
):
    def operation():
        require_workspace_admin(actor, workspace)
        if actor_type not in {"agent", "system", "integration"} or not isinstance(actor_id, UUID):
            raise ValidationError("Register a nonhuman UUID principal of a declared type.")
        if (
            not commands
            or set(commands) - set(INPUTS)
            or {"ApproveDecision", "InitializeObjectProperties"}.intersection(commands)
        ):
            raise ValidationError("Grant only known commands; Decision approval is human-only.")
        if not object_types or not fields or not all(isinstance(v, str) for v in [*object_types, *fields]):
            raise ValidationError("Explicit Object type and field scopes are required.")
        if type(requires_approval) is not bool or type(is_active) is not bool:
            raise ValidationError("Grant flags must be booleans.")
        if not User.objects.filter(pk=delegator_id, is_active=True, is_bot=False).exists() or not (
            WorkspaceMember.objects.filter(
                workspace=workspace, member_id=delegator_id, role__in=[15, 20], is_active=True
            ).exists()
        ):
            raise PermissionDenied("Delegator must be an active human workspace writer.")
        grant = ActorGrant.objects.filter(workspace=workspace, actor_type=actor_type, actor_id=actor_id).first()
        values = dict(
            delegator_id=delegator_id,
            commands=commands,
            object_types=object_types,
            fields=fields,
            requires_approval=requires_approval or actor_type == "agent",
            is_active=is_active,
            updated_by_id=actor.actor_id,
        )
        if grant is None:
            grant = ActorGrant.objects.create(
                workspace=workspace, actor_type=actor_type, actor_id=actor_id, created_by_id=actor.actor_id, **values
            )
        else:
            for key, value in values.items():
                setattr(grant, key, value)
            grant.policy_version += 1
            grant.save()
        return grant

    return run_internal(actor=actor, workspace=workspace, name="ActorGrantConfigured", operation=operation)


def configure_person_identity(*, actor, workspace, user_id, person_id, can_approve=False, is_active=True):
    def operation():
        require_workspace_admin(actor, workspace)
        person = lookup_object(workspace, person_id, {"person"})
        if type(can_approve) is not bool or type(is_active) is not bool:
            raise ValidationError("Authority flags must be booleans.")
        if not User.objects.filter(pk=user_id, is_active=True, is_bot=False).exists() or not (
            WorkspaceMember.objects.filter(
                workspace=workspace, member_id=user_id, role__in=[15, 20], is_active=True
            ).exists()
        ):
            raise PermissionDenied("Person identity requires an active human workspace writer.")
        identity, created = PersonIdentity.objects.get_or_create(
            workspace=workspace,
            user_id=user_id,
            defaults={
                "person": person,
                "can_approve": can_approve,
                "is_active": is_active,
                "created_by_id": actor.actor_id,
                "updated_by_id": actor.actor_id,
            },
        )
        if not created:
            identity.person, identity.can_approve, identity.is_active = person, can_approve, is_active
            identity.updated_by_id = actor.actor_id
            identity.save()
        return identity

    return run_internal(actor=actor, workspace=workspace, name="PersonIdentityConfigured", operation=operation)


def review_command(*, actor, workspace, command_id, intent_hash, approve, rationale):
    def operation():
        require_human_membership(actor, workspace)
        if type(approve) is not bool or not isinstance(rationale, str) or not rationale.strip():
            raise ValidationError("Review requires a boolean outcome and a rationale.")
        execution = CommandExecution.objects.filter(pk=command_id, workspace=workspace).first()
        if execution is None:
            raise NotFound("Command not found in this workspace.")
        approval = CommandApproval.objects.filter(workspace=workspace, execution=execution).first()
        if approval is None or approval.status != "pending" or execution.status != "pending_approval":
            raise CommandConflict({"code": "approval_stale"})
        if execution.actor_type == "human" and execution.actor_id == actor.actor_id:
            raise PermissionDenied("An independent human must review this intention.")
        if execution.intent_hash != intent_hash or approval.expires_at <= timezone.now():
            raise CommandConflict({"code": "approval_stale"})
        if approve:
            if execution.envelope["schema_hash"] != schema_fingerprint(workspace):
                raise CommandConflict({"code": "approval_stale"})
            request_actor_data = execution.actor_context.copy()
            from datetime import datetime
            from .actor import Actor

            for key in ("actor_id", "correlation_id", "run_id", "approval_id", "on_behalf_of"):
                if request_actor_data.get(key):
                    request_actor_data[key] = UUID(request_actor_data[key])
            request_actor_data["timestamp"] = datetime.fromisoformat(request_actor_data["timestamp"])
            request_actor = Actor(**request_actor_data)
            grant = authorize(request_actor, workspace, execution.command_name)
            serializer = INPUTS[execution.command_name](data=execution.envelope["input"])
            serializer.is_valid(raise_exception=True)
            refs = references(workspace, execution.command_name, serializer.validated_data)
            refs.update(UUID(pk) for pk in execution.envelope["assertion"]["evidence_ids"])
            lock_expected_versions(workspace, execution.envelope["expected_versions"], refs)
            check_grant(workspace, grant, execution.command_name, serializer.validated_data, refs)
            if approval.policy_version != (grant.policy_version if grant else 1):
                raise CommandConflict({"code": "approval_stale"})
        approval.approver_id, approval.rationale = actor.actor_id, rationale.strip()
        approval.status, approval.updated_by_id = "approved" if approve else "rejected", actor.actor_id
        approval.save(update_fields=["approver_id", "rationale", "status", "updated_by", "updated_at"])
        if not approve:
            execution.status = "rejected"
            execution.save(update_fields=["status"])
        emit(
            "CommandApprovalReviewed",
            {
                "command_id": execution.pk,
                "approval_id": approval.pk,
                "approved": approve,
                "approver_id": actor.actor_id,
            },
        )
        return approval

    return run_internal(actor=actor, workspace=workspace, name="ReviewCommand", operation=operation)
