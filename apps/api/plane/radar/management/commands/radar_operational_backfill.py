"""Explicit reviewed backfill/export; no application startup or GET migrates facts."""

import json
from uuid import UUID, uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.commands.control import require_workspace_admin
from plane.radar.operational_backfill import preview_backfill, backfill, export_workspace


class Command(BaseCommand):
    help = "Inventory legacy operational records, apply a reviewed backfill, or stream recovery export."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", required=True)
        parser.add_argument("--admin-id", required=True, type=UUID)
        parser.add_argument("--timezone", default="UTC")
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--export", action="store_true")
        parser.add_argument("--reviewed-hash")
        parser.add_argument("--reason")

    @transaction.atomic
    def handle(self, *args, **options):
        workspace = Workspace.objects.get(slug=options["workspace"])
        actor = Actor(
            actor_type="human",
            actor_id=options["admin_id"],
            correlation_id=uuid4(),
            source="radar.operational-backfill-cli",
            reason=options["reason"] or "Inventory operational archive",
        )
        require_workspace_admin(actor, workspace)
        if options["export"]:
            from plane.radar.workspace_schema import lock_schema

            lock_schema(workspace)
            for row in export_workspace(workspace):
                self.stdout.write(json.dumps(row))
        elif options["apply"]:
            if not options["reviewed_hash"] or not options["reason"] or not options["reason"].strip():
                raise CommandError("Apply requires the reviewed dry-run hash and an explicit reason.")
            self.stdout.write(
                json.dumps(
                    backfill(
                        actor=actor,
                        workspace=workspace,
                        reviewed_hash=options["reviewed_hash"],
                        timezone_name=options["timezone"],
                    )
                )
            )
        else:
            self.stdout.write(
                json.dumps(preview_backfill(actor=actor, workspace=workspace, timezone_name=options["timezone"]))
            )
