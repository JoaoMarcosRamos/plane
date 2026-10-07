"""Phase 1.8: assert the final PostgreSQL state and provenance (run inside the API container).

    docker exec -i -e RADAR_E2E_STATE="$(cat e2e-state.json)" plane-radar-api-1 \
      python manage.py shell --settings=plane.settings.local < verify_db.py
"""

import json
import os
from uuid import UUID

from plane.radar.models import (
    AgentRuntimeRun,
    CommandApproval,
    DomainEvent,
    Object,
    Provenance,
    Relation,
    RiskReview,
    RiskReviewProposal,
    RuntimeObjectIdentity,
)

state = json.loads(os.environ["RADAR_E2E_STATE"])
risk, objective, project = (
    UUID(state["objects"][k]) for k in ("risk", "objective", "project")
)
action = UUID(state["action"])
run_id = UUID(state["runs"]["scripted"]["run_id"])
checks = []


def check(name, ok, detail=None):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def provenance_row(execution):
    rows = Provenance.objects.filter(command_id=execution.pk).order_by("timestamp")
    return [
        {
            "command": p.command_name,
            "actor_type": p.actor_type,
            "actor_id": str(p.actor_id),
            "reason": p.reason,
            "source": p.source,
            "run_id": str(p.run_id) if p.run_id else None,
            "approval_id": str(p.approval_id) if p.approval_id else None,
            "confidence": p.confidence,
            "correlation_id": str(p.correlation_id),
            "on_behalf_of": p.context.get("actor", {}).get("on_behalf_of"),
            "outcome": p.outcome,
        }
        for p in rows
    ]


slug = state["workspace"]
runs = AgentRuntimeRun.objects.filter(
    workspace__slug=slug, request_data__skill="risk_review"
)
run = AgentRuntimeRun.objects.get(pk=run_id)
check(
    "one scripted run for the replayed start",
    runs.filter(idempotency_key=run.idempotency_key).count() == 1,
)
check(
    "one review for the run, prepared once",
    RiskReview.objects.filter(run=run).count() == 1,
)

threatens = Relation.objects.filter(
    relation_type__key="threatens", source_id=risk, deleted_at__isnull=True
)
check(
    "exactly one threatens relation Risk -> Objective",
    list(threatens.values_list("target_id", flat=True)) == [objective],
)
check(
    "rejected Risk -> Project threat was not created",
    not threatens.filter(target_id=project).exists(),
)
mitigates = Relation.objects.filter(
    relation_type__key="mitigates",
    source_id=action,
    target_id=risk,
    deleted_at__isnull=True,
)
check("Action mitigates Risk exactly once", mitigates.count() == 1)
created_actions = Object.objects.filter(
    workspace__slug=slug, object_type__key="action", deleted_at__isnull=True
)
check(
    "exactly one Action exists (retries and rejection created none)",
    list(created_actions.values_list("pk", flat=True)) == [action],
)
check(
    "Action has a canonical runtime identity in the agent context",
    RuntimeObjectIdentity.objects.filter(
        object_id=action, context=f"company:{slug}", external_id__startswith="ACT-"
    ).exists(),
)

evidence = {}
for key, proposal_id in (
    ("relation", state["accepted_relation"]["proposal"]),
    ("action", state["accepted_action"]["proposal"]),
):
    proposal = RiskReviewProposal.objects.select_related("execution").get(
        pk=proposal_id
    )
    execution = proposal.execution
    approval = CommandApproval.objects.get(execution=execution)
    rows = provenance_row(execution)
    domain = [r for r in rows if r["command"] == execution.command_name]
    row = domain[-1] if domain else {}
    evidence[key] = {
        "command": execution.command_name,
        "execution_status": execution.status,
        "approval": {
            "status": approval.status,
            "approver_id": str(approval.approver_id),
            "rationale": approval.rationale,
        },
        "provenance": rows,
        "events": list(
            DomainEvent.objects.filter(execution_id=execution.pk).values_list(
                "event_type", flat=True
            )
        ),
    }
    check(
        f"{key}: executed once; single-use human approval consumed",
        execution.status == "executed" and approval.status == "consumed",
    )  # approved, then consumed once
    check(
        f"{key}: provenance actor is the agent",
        row.get("actor_type") == "agent"
        and row.get("actor_id") == str(run.binding.actor_id),
    )
    check(
        f"{key}: provenance names the human (on behalf of + approver)",
        row.get("on_behalf_of") == str(run.user_id)
        and str(approval.approver_id) == str(run.user_id),
    )
    check(
        f"{key}: provenance approval_id links the human approval",
        row.get("approval_id") == str(approval.pk),
    )
    check(
        f"{key}: provenance reason is the agent explanation",
        row.get("reason")
        == proposal.review.result["suggestions"][proposal.ordinal]["explanation"],
    )
    check(
        f"{key}: provenance source is the skill",
        row.get("source") == "radar.skill.risk_review",
    )
    check(
        f"{key}: provenance run_id is the Risk Review run",
        row.get("run_id") == str(run_id),
    )
    check(
        f"{key}: provenance confidence is the suggestion confidence",
        row.get("confidence") == 0.8,
    )
    check(
        f"{key}: domain event persisted in the same commit",
        len(evidence[key]["events"]) >= 1,
    )

rejections = {}
for key in ("relation", "action"):
    proposal = RiskReviewProposal.objects.select_related("execution").get(
        pk=state["rejected"][key]["proposal"]
    )
    approval = CommandApproval.objects.get(execution=proposal.execution)
    review_rows = Provenance.objects.filter(
        run_id=run_id,
        actor_type="human",
        context__actor__metadata__proposal_id=str(proposal.pk),
    )
    rejections[key] = {
        "execution_status": proposal.execution.status,
        "approval": {
            "status": approval.status,
            "approver_id": str(approval.approver_id),
            "rationale": approval.rationale,
        },
        "human_review_provenance": list(
            review_rows.values(
                "command_name", "actor_type", "reason", "source", "outcome"
            )
        ),
    }
    check(
        f"rejected {key}: not executed, rationale stored",
        proposal.execution.status == "rejected" and approval.rationale,
    )
    check(
        f"rejected {key}: human review provenance recorded",
        review_rows.exists()
        or Provenance.objects.filter(
            command_id=proposal.execution.pk, actor_type="human"
        ).exists(),
    )

print(
    "VERIFY "
    + json.dumps(
        {"checks": checks, "accepted": evidence, "rejected": rejections},
        default=str,
        ensure_ascii=False,
    )
)
