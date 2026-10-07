"""Shared human membership boundary; command effect authority remains in the dispatcher."""

from rest_framework.exceptions import PermissionDenied
from plane.db.models import User, Workspace, WorkspaceMember
from .actor import Actor


def require_human_membership(actor: Actor, workspace: Workspace, *, write=True) -> None:
    roles = [15, 20] if write else [5, 15, 20]
    if (
        actor.actor_type != "human"
        or not User.objects.filter(pk=actor.actor_id, is_active=True, is_bot=False).exists()
        or not WorkspaceMember.objects.filter(
            workspace=workspace, member_id=actor.actor_id, role__in=roles, is_active=True
        ).exists()
    ):
        raise PermissionDenied("Active workspace membership does not permit this operation.")
