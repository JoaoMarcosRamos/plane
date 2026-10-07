import json
from uuid import UUID, uuid4

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import APIException

from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.commands.governance import create_governance_scenario


class Command(BaseCommand):
    help = "Create the five-object Phase 0.5 demo in a workspace without RADAR objects."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True, help="Existing dedicated workspace slug")
        parser.add_argument("--actor", required=True, type=UUID, help="Active human member UUID")
        parser.add_argument("--reason", required=True, help="Explicit reason for creating demo data")

    def handle(self, *args, **options):
        actor = Actor(
            actor_type="human",
            actor_id=options["actor"],
            reason=options["reason"],
            source="radar_governance_scenario",
            correlation_id=uuid4(),
        )
        try:
            workspace = Workspace.objects.get(slug=options["workspace"])
            objects = create_governance_scenario(actor=actor, workspace=workspace)
        except (ObjectDoesNotExist, APIException) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "workspace": workspace.slug,
                    "actor": str(actor.actor_id),
                    "objects": {key: str(pk) for key, pk in objects.items()},
                    "urls": {key: f"/{workspace.slug}/radar/objects/{pk}/" for key, pk in objects.items()},
                },
                ensure_ascii=False,
            )
        )
