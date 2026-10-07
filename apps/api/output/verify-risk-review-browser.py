import json
import sys
sys.path.insert(0, "/code")
import django
django.setup()
from plane.db.models import Workspace
from plane.radar.models import Object, Relation, RiskReviewProposal, Provenance, RuntimeObjectIdentity
workspace = Workspace.objects.get(slug="risk-review-browser")
actions = Object.objects.filter(workspace=workspace, object_type__key="action")
assert actions.count() == 1
assert actions.get().title == "Confirmar prazo de licenciamento do Sandbox IA"
assert RuntimeObjectIdentity.objects.filter(object=actions.get(), context="company:browser").exists()
assert Relation.objects.filter(workspace=workspace, relation_type__key="threatens").count() == 1
assert Relation.objects.filter(workspace=workspace, relation_type__key="mitigates").count() == 1
rejected = RiskReviewProposal.objects.get(workspace=workspace, component="action", execution__commandapproval__rationale="A mitigação já foi registrada; rejeitar a ação duplicada.")
assert rejected.execution.status == "rejected"
feedback = Provenance.objects.filter(workspace=workspace, command_name="ReviewCommand", reason="A mitigação já foi registrada; rejeitar a ação duplicada.").get()
assert feedback.context["actor"]["metadata"]["decision"] == "reject" and feedback.run_id is not None
print(json.dumps({"action_count": actions.count(), "action_title": actions.get().title,
    "threatens_count": 1, "mitigates_count": 1, "runtime_identity": True, "rejection_provenance": str(feedback.pk),
    "proposal_statuses": list(RiskReviewProposal.objects.filter(workspace=workspace).values("component", "revision", "execution__status"))}, ensure_ascii=False, indent=2))
