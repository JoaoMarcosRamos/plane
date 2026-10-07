"""Session-only review API; no actor or executable envelope supplied by the browser."""

from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from plane.radar.agent_runtime import fingerprint, runtime_request, RuntimeConflict, RuntimeUnavailable
from plane.radar.commands.inputs import StrictSerializer
from plane.radar.models import AgentRuntimeRun, RiskReview, RiskReviewProposal
from plane.radar.risk_review import access_run, save_review, resolve_proposal
from .views import RadarAPIView


class PrepareInput(StrictSerializer):
    run_id = serializers.UUIDField()


class ResolveInput(StrictSerializer):
    decision = serializers.ChoiceField(choices=["accept", "edit", "reject"])
    rationale = serializers.CharField(max_length=2000)
    intent_hash = serializers.RegexField(r"^[a-f0-9]{64}$")
    edited_input = serializers.JSONField(required=False)

    def validate(self, data):
        if (data["decision"] == "edit") != ("edited_input" in data):
            raise serializers.ValidationError("Only Edit requires edited_input.")
        return data


def proposal_data(proposal):
    proposal.execution.refresh_from_db()
    execution = proposal.execution
    raw_preview = execution.result.get("data", {}).get("effect_plan")
    preview = (
        None
        if raw_preview is None
        else {
            "preview_only": True,
            "changes": [
                {
                    "model": item["model"],
                    "id": item["id"],
                    "operation": "create" if item["before"] is None else "update",
                }
                for item in raw_preview["changes"]
            ],
            "events": [{"event_type": event["event_type"]} for event in raw_preview["events"]],
        }
    )
    # Command previews contain full audit rows. The review API returns effect summaries
    # and a minimal receipt so field restrictions also hold on this transport.
    result = {key: value for key, value in execution.result.items() if key != "data"}
    created = execution.result.get("data", {}).get("object")
    result["data"] = {"object": {"id": created["id"]}} if created else {}
    return {
        "id": str(proposal.pk),
        "run_id": str(proposal.review_id),
        "ordinal": proposal.ordinal,
        "component": proposal.component,
        "revision": proposal.revision,
        "previous_id": str(proposal.previous_id) if proposal.previous_id else None,
        "status": execution.status,
        "intent_hash": execution.intent_hash,
        "suggestion": proposal.review.result["suggestions"][proposal.ordinal],
        "command_name": execution.command_name,
        "input": execution.envelope["input"],
        "expected_versions": execution.envelope["expected_versions"],
        "reviewed_context": proposal.reviewed_context,
        "preview": preview,
        "result": result,
        "approval": {
            "status": execution.commandapproval.status,
            "rationale": execution.commandapproval.rationale,
            "expires_at": execution.commandapproval.expires_at,
        },
    }


class RiskReviewsView(RadarAPIView):
    def get(self, request, slug):
        workspace = self.workspace()
        runs, proposals = [], []
        candidates = AgentRuntimeRun.objects.filter(
            workspace=workspace, user=request.user, request_data__skill="risk_review"
        ).order_by("-created_at")
        proposal_id = request.query_params.get("proposal")
        if proposal_id:
            proposal_id = serializers.UUIDField().run_validation(proposal_id)
            candidates = candidates.filter(riskreview__proposals__pk=proposal_id)
        else:
            candidates = candidates[:30]
        for run in candidates:
            try:
                access_run(request.user, workspace, run)
            except APIException:
                continue
            review = RiskReview.objects.filter(run=run).first()
            runs.append(
                {
                    "run_id": str(run.pk),
                    "binding_id": str(run.binding_id),
                    "created_at": run.created_at,
                    "result": review.result if review else None,
                    "context": run.request_data["context"],
                }
            )
            if review:
                proposals.extend(
                    proposal_data(p)
                    for p in review.proposals.select_related("execution").order_by("ordinal", "component", "revision")
                )
        return Response({"runs": runs, "proposals": proposals})

    def post(self, request, slug):
        parsed = PrepareInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        workspace = self.workspace()
        run = get_object_or_404(
            AgentRuntimeRun, workspace=workspace, user=request.user, pk=parsed.validated_data["run_id"]
        )
        access_run(request.user, workspace, run)
        review = RiskReview.objects.filter(run=run).first()
        if review is None:
            remote = runtime_request(
                f"runs/{run.pk}/status",
                {
                    "identity": run.request_data["identity"],
                    "context_hash": fingerprint(run.request_data["context"]),
                    "after": 0,
                },
            )
            if remote.get("run_id") != str(run.pk):
                raise RuntimeUnavailable()
            if remote.get("status") != "completed":
                return Response(remote, status=202)
            result = remote.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("risk_review"), dict):
                raise RuntimeUnavailable()
            sources = result.get("sources")
            expected = [{"id": obj["id"], "version": obj["version"]} for obj in run.request_data["context"]["objects"]]
            if sources != expected or result.get("truncated") != run.request_data["context"]["truncated"]:
                raise RuntimeConflict({"code": "invalid_runtime_sources"})
            review = save_review(request.user, workspace, run, result["risk_review"])
        return Response(
            {
                "run_id": str(run.pk),
                "status": "completed",
                "result": review.result,
                "proposals": [proposal_data(p) for p in review.proposals.order_by("ordinal", "component", "revision")],
            }
        )


class RiskReviewResolveView(RadarAPIView):
    def post(self, request, slug, proposal_id):
        parsed = ResolveInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        workspace = self.workspace()
        proposal = get_object_or_404(
            RiskReviewProposal, pk=proposal_id, workspace=workspace, review__run__user=request.user
        )
        proposal = resolve_proposal(request.user, workspace, proposal, **parsed.validated_data)
        return Response(proposal_data(proposal))
