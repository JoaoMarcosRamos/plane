"""Audited local provisioning; never called by a model or public transport."""

from uuid import UUID, uuid4
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.commands import initialize_semantic_model, configure_person_identity, register_actor_grant
from plane.radar.commands.runtime_control import bind_runtime_object, issue_runtime_credential
from plane.radar.commands.control import require_workspace_admin
from plane.radar.models import PersonIdentity
from plane.radar.ontology.schema import load_schema


class Command(BaseCommand):
    help = "Bind an existing Object or issue a CoS credential with explicit human authority."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--admin-id", required=True, type=UUID)
        parser.add_argument("--context", required=True)
        parser.add_argument("--bind-object", type=UUID)
        parser.add_argument("--external-id")
        parser.add_argument("--agent-id", type=UUID)
        parser.add_argument("--reviewer-id", type=UUID)
        parser.add_argument("--person-id", type=UUID)
        parser.add_argument("--channel", choices=["telegram", "plane"], default="telegram")
        parser.add_argument("--telegram-user-id", type=int)
        parser.add_argument("--manager", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        workspace = Workspace.objects.get(slug=options["workspace"])
        actor = Actor(
            actor_type="human",
            actor_id=options["admin_id"],
            reason="Provision CoS runtime",
            source="radar.runtime-cli",
            correlation_id=uuid4(),
        )
        require_workspace_admin(actor, workspace)
        initialize_semantic_model(actor=actor, workspace=workspace)
        if options["bind_object"]:
            identity = bind_runtime_object(
                actor=actor,
                workspace=workspace,
                object_id=options["bind_object"],
                external_id=options["external_id"] or "",
                context=options["context"],
            )
            self.stdout.write(identity.external_id)
            return
        if not all(options[key] for key in ("agent_id", "reviewer_id", "person_id")) or (
            options["channel"] == "telegram" and not options["telegram_user_id"]
        ):
            raise CommandError(
                "Issuing a credential requires agent, reviewer and Person IDs; Telegram also requires its user ID."
            )
        existing_identity = PersonIdentity.objects.filter(workspace=workspace, user_id=options["reviewer_id"]).first()
        if existing_identity:
            if existing_identity.person_id != options["person_id"] or not existing_identity.is_active:
                raise CommandError("Configure this reviewer's PersonIdentity explicitly before provisioning.")
        else:
            configure_person_identity(
                actor=actor, workspace=workspace, user_id=options["reviewer_id"], person_id=options["person_id"]
            )
        register_actor_grant(
            actor=actor,
            workspace=workspace,
            actor_type="agent",
            actor_id=options["agent_id"],
            delegator_id=options["reviewer_id"],
            commands=["CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement", "LinkObjects"],
            object_types=list(load_schema()["object_types"]),
            fields=["*"],
        )
        credential, token = issue_runtime_credential(
            actor=actor,
            workspace=workspace,
            actor_id=options["agent_id"],
            context=options["context"],
            channel=options["channel"],
            external_author=f"plane:{options['reviewer_id']}"
            if options["channel"] == "plane"
            else f"telegram:{options['telegram_user_id']}",
            reviewer_id=options["reviewer_id"],
            person_id=options["person_id"],
            is_manager=options["manager"],
        )
        self.stdout.write(str(credential.pk) if options["channel"] == "plane" else token)
