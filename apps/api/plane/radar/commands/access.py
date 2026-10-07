"""One translation of Plane roles for RADAR readers, writers and administrators."""

from rest_framework.exceptions import PermissionDenied
from plane.db.models import User, Workspace, WorkspaceMember
from .actor import Actor


READ_ROLES = frozenset({5, 15, 20})
WRITE_ROLES = frozenset({15, 20})
ADMIN_ROLE = 20


def role_can_write(role):
    return role in WRITE_ROLES


def role_is_admin(role):
    return role == ADMIN_ROLE


def is_workspace_admin(actor, workspace):
    return actor.actor_type == "human" and user_is_workspace_admin(actor.actor_id, workspace)


def user_is_workspace_admin(user_id, workspace):
    return (
        workspace.owner_id == user_id
        or WorkspaceMember.objects.filter(
            workspace=workspace, member_id=user_id, role=ADMIN_ROLE, is_active=True
        ).exists()
    )


def require_workspace_admin(actor, workspace):
    require_human_membership(actor, workspace)
    if not is_workspace_admin(actor, workspace):
        raise PermissionDenied("Only the workspace owner or admin may provision RADAR authority.")


def require_human_membership(actor: Actor, workspace: Workspace, *, write=True) -> None:
    roles = WRITE_ROLES if write else READ_ROLES
    if (
        actor.actor_type != "human"
        or not User.objects.filter(pk=actor.actor_id, is_active=True, is_bot=False).exists()
        or not WorkspaceMember.objects.filter(
            workspace=workspace, member_id=actor.actor_id, role__in=roles, is_active=True
        ).exists()
    ):
        raise PermissionDenied("Active workspace membership does not permit this operation.")
