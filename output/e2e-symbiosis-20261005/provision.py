"""Phase 1.8 administrative setup in the isolated plane-radar stack (run inside the API container).

    docker exec -i -e RADAR_E2E_MEMBER_PASSWORD=... -e RADAR_E2E_GUEST_PASSWORD=... -e RADAR_E2E_OUTSIDER_PASSWORD=... \
      plane-radar-api-1 python manage.py shell --settings=plane.settings.local < provision.py

Plane accounts/workspace are test infrastructure. Everything RADAR goes through the audited control
commands an administrator uses (`radar_runtime_provision` and `register_actor_grant`); domain Objects
used by the flow are created later by the human in the browser. Idempotent: reruns reuse what exists.
"""

import hashlib
import io
import json
import os
from uuid import UUID, uuid4

from django.core.management import call_command
from plane.db.models import Profile, User, Workspace, WorkspaceMember
from plane.radar.commands import initialize_semantic_model, register_actor_grant
from plane.radar.commands.actor import Actor
from plane.radar.commands.objects import create_object
from plane.radar.models import (
    ActorGrant,
    Object,
    ObjectType,
    PersonIdentity,
    RuntimeCredential,
)

SLUG = os.environ.get("RADAR_E2E_SLUG", "radar-e2e")
CONTEXT = f"company:{SLUG}"
ONBOARDED = {
    "workspace_join": True,
    "profile_complete": True,
    "workspace_create": True,
    "workspace_invite": True,
}


def account(email, password_env, first_name):
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create(
            email=email,
            username=email.split("@")[0],
            first_name=first_name,
            display_name=first_name,
        )
    if password_env:
        user.set_password(os.environ[password_env])
        user.is_password_autoset = False
        user.save()
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.is_onboarded, profile.onboarding_step = True, ONBOARDED
    profile.save()
    return user


tester = User.objects.get(email="radar-tester@plane.local")
member = account(
    "radar-e2e-member@plane.local", "RADAR_E2E_MEMBER_PASSWORD", "E2E Member"
)
guest = account("radar-e2e-guest@plane.local", "RADAR_E2E_GUEST_PASSWORD", "E2E Guest")
outsider = account(
    "radar-e2e-outsider@plane.local", "RADAR_E2E_OUTSIDER_PASSWORD", "E2E Outsider"
)

workspace = Workspace.objects.filter(slug=SLUG).first() or Workspace.objects.create(
    name=SLUG.replace("-", " ").upper(), slug=SLUG, owner=tester
)
for user, role in ((tester, 20), (member, 15), (guest, 5)):
    WorkspaceMember.objects.update_or_create(
        workspace=workspace, member=user, defaults={"role": role, "is_active": True}
    )
for user in (member, guest):
    Profile.objects.filter(user=user).update(last_workspace_id=workspace.pk)

admin = Actor(
    actor_type="human",
    actor_id=tester.pk,
    reason="Provision Phase 1.8 E2E agent",
    source="radar.runtime-cli",
    correlation_id=uuid4(),
)
initialize_semantic_model(actor=admin, workspace=workspace)

identity = PersonIdentity.objects.filter(
    workspace=workspace, user=tester, is_active=True
).first()
person = identity.person if identity else None
if person is None:
    person = create_object(
        actor=admin,
        workspace=workspace,
        object_type=ObjectType.objects.get(workspace=workspace, key="person").pk,
        title="Radar Tester",
        properties={},
    )
    person = Object.objects.get(pk=person.pk)


def provision(*args):
    out = io.StringIO()
    call_command(
        "radar_runtime_provision",
        "--workspace",
        SLUG,
        "--admin-id",
        str(tester.pk),
        "--context",
        CONTEXT,
        *args,
        stdout=out,
    )
    return out.getvalue().strip()


provision(
    "--bind-object",
    str(person.pk),
    "--external-id",
    "PER-20261005-" + hashlib.sha256(SLUG.encode()).hexdigest()[:6].upper(),
)
binding = RuntimeCredential.objects.filter(
    workspace=workspace, reviewer=tester, channel="plane", is_active=True
).first()
if binding is None:
    binding_id = provision(
        "--channel",
        "plane",
        "--agent-id",
        str(uuid4()),
        "--reviewer-id",
        str(tester.pk),
        "--person-id",
        str(person.pk),
    )
    binding = RuntimeCredential.objects.get(pk=UUID(binding_id))

# Risk Review needs CreateAction besides the CLI defaults; the existing grant control extends the ceiling.
grant = ActorGrant.objects.get(
    workspace=workspace, actor_type="agent", actor_id=binding.actor_id
)
if "CreateAction" not in grant.commands:
    register_actor_grant(
        actor=admin,
        workspace=workspace,
        actor_type="agent",
        actor_id=binding.actor_id,
        delegator_id=tester.pk,
        commands=[*grant.commands, "CreateAction"],
        object_types=grant.object_types,
        fields=grant.fields,
    )
grant.refresh_from_db()
print(
    "PROVISIONED "
    + json.dumps(
        {
            "workspace": SLUG,
            "workspace_id": str(workspace.pk),
            "context": CONTEXT,
            "binding_id": str(binding.pk),
            "agent_id": str(binding.actor_id),
            "person_id": str(person.pk),
            "tester_id": str(tester.pk),
            "member_id": str(member.pk),
            "guest_id": str(guest.pk),
            "outsider_id": str(outsider.pk),
            "grant_commands": grant.commands,
            "grant_policy_version": grant.policy_version,
        }
    )
)
