"""Independent PostgreSQL checks of browser-created facts and paged relation reads."""
import sys
sys.path.insert(0, "/code")
import django
django.setup()
import json
from rest_framework.test import APIClient
from plane.db.models import Workspace
from plane.radar.models import Object, PropertyValue, Relation, Provenance
created = Object.objects.select_related("workspace", "created_provenance").get(title="Integrated UI ticket")
values = dict(PropertyValue.objects.filter(object=created).values_list("definition__key", "value"))
assert created.version == 3 and values["status"] == "working"
assert values["summary"] == "Created from the configured required field"
edge = Relation.objects.select_related("target").get(source=created, relation_type__key="ticket_refs")
assert edge.target.title == "Objective 110" and created.created_provenance.source == "radar.session-api"
workspace = Workspace.objects.get(slug="pending-browser-aa0578a3")
existing = Object.objects.get(workspace=workspace, title="Existing ticket")
removed = Relation.all_objects.select_related("source").get(workspace=workspace, target=existing, source__title="Objective 030", relation_type__key="backlinks_ticket")
assert removed.deleted_at is not None and removed.last_provenance.command_name == "UnlinkObjects"
api = APIClient(); api.force_authenticate(user=workspace.owner)
path = f"/api/workspaces/{workspace.slug}/radar/objects/{existing.pk}/relations/"
first = api.get(path).data
second = api.get(path, {"cursor": first["next_cursor"]}).data
assert len(first["relations"]) == 50 and len(second["relations"]) == 5
assert second["next_cursor"] is None
capacities = api.get(f"/api/workspaces/{workspace.slug}/radar/objects/{existing.pk}/capabilities/").data
assert len(capacities["relations"]) == 50
ids = [edge["id"] for edge in second["relations"]]
assert len(api.get(f"/api/workspaces/{workspace.slug}/radar/objects/{existing.pk}/capabilities/", {"relation_ids": ",".join(ids)}).data["relations"]) == 5
result = {"created": str(created.pk), "version": created.version, "summary": values["summary"], "status": values["status"], "related_title": edge.target.title, "created_actor": created.created_provenance.actor_type, "pages_after_removal": [50, 5], "capability_pages": [50, 5], "removed_relation": str(removed.pk), "provenance": str(removed.last_provenance_id)}
open("output/core-pending-browser-proof.json", "w").write(json.dumps(result, indent=2))
print(json.dumps(result))
