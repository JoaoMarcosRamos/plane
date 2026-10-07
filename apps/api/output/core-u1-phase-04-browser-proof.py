"""Independent ledger/database proof of the phase 4 browser flows."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/code")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
import django

django.setup()
from plane.radar.models import ActionCompletion, CommandExecution, DecisionApproval, Object, PropertyValue, Provenance
from plane.radar.workspace_schema import schema_revision


def values(obj):
    return {item.definition.key: item.value for item in PropertyValue.objects.filter(object=obj).select_related("definition")}


ticket = Object.objects.get(workspace__slug="u1-phase04-browser", object_type__key="ticket", title="Printer offline")
action = Object.objects.get(workspace__slug="u1-phase04-browser", title="Negotiate licenses")
decision = Object.objects.get(workspace__slug="u1-phase04-browser", title="Adopt enterprise licenses")
workspace = ticket.workspace
ticket_values, action_values, decision_values = values(ticket), values(action), values(decision)
# Only intentions sent by the browser session; fixture provisioning uses its own source.
browser = CommandExecution.objects.filter(workspace=workspace, actor_context__source="radar.session-api")
envelopes = [
    {"command": e.command_name, "status": e.status, "expected_schema_revision": e.envelope.get("expected_schema_revision")}
    for e in browser.order_by("created_at")
]
result = {
    "schema_revision": schema_revision(workspace),
    "ticket": {"values": ticket_values, "version": ticket.version},
    "action": {"status": action_values["status"], "completed_at": action_values.get("completed_at")},
    "decision": {"status": decision_values["status"], "decided_at": decision_values.get("decided_at")},
    "completion_outcome": ActionCompletion.objects.get(action=action).outcome,
    "approvals": DecisionApproval.objects.filter(decision=decision).count(),
    "commands": envelopes,
    "provenance_commands": sorted(
        set(Provenance.objects.filter(workspace=workspace, outcome="executed").values_list("command_name", flat=True))
    ),
}
assert ticket_values["summary"] == "Third floor printer is offline" and ticket_values["status"] == "closed"
assert ticket_values.get("closed_at")
assert action_values["status"] == "done" and action_values.get("completed_at")
assert decision_values["status"] == "decided" and decision_values.get("decided_at")
assert result["completion_outcome"] == "Enterprise terms signed" and result["approvals"] == 1
assert {"CreateObject", "UpdateObject", "CompleteAction", "ApproveDecision"} <= {e["command"] for e in envelopes}
assert all(e["status"] == "executed" for e in envelopes)
assert all(e["expected_schema_revision"] == result["schema_revision"] for e in envelopes)
Path("output/core-u1-phase-04-browser-proof.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
