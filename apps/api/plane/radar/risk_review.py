"""Evidence validation and trusted coordination of separately reviewed commands."""

import json
from dataclasses import replace
from uuid import UUID

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.active import active_relation_types
from plane.radar.agent_runtime import binding_for, fingerprint, load_context, verify_snapshot, RuntimeConflict
from plane.radar.commands.actor import Actor
from plane.radar.commands.control import review_command
from plane.radar.commands.execution import execute_command, run_internal, command_envelope
from plane.radar.commands.handlers import references
from plane.radar.commands.effects import check_grant, plan_command
from plane.radar.commands.inputs import AssertionInput, StrictSerializer, INPUTS
from plane.radar.models import RiskReview, RiskReviewProposal


class EvidenceInput(StrictSerializer):
    object_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    field = serializers.CharField(max_length=80)
    quote = serializers.CharField(max_length=500, trim_whitespace=False)


class RelationInput(StrictSerializer):
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    relation = serializers.ChoiceField(choices=["threatens"])


class ActionInput(StrictSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(max_length=2000)
    next_step = serializers.CharField(max_length=500)
    mitigates_risk_id = serializers.UUIDField()


class SuggestionInput(StrictSerializer):
    explanation = serializers.CharField(max_length=2000)
    suggested_relation = RelationInput()
    suggested_action = ActionInput(allow_null=True)
    confidence = serializers.JSONField()
    evidence = EvidenceInput(many=True, min_length=2, max_length=10)
    context_used = serializers.ListField(child=serializers.UUIDField(), max_length=40)

    def validate_confidence(self, value):
        parsed = AssertionInput(data={"kind": "inferred", "confidence": value})
        parsed.is_valid(raise_exception=True)
        return value


class OutputInput(StrictSerializer):
    summary = serializers.CharField(max_length=2000)
    suggestions = SuggestionInput(many=True, max_length=5)


def validate_output(result, snapshot):
    parsed = OutputInput(data=result)
    parsed.is_valid(raise_exception=True)
    objects = {UUID(o["id"]): o for o in snapshot["objects"]}
    edges = {UUID(r["id"]) for r in snapshot["relations"]}
    pairs = set()
    for item in parsed.validated_data["suggestions"]:
        relation = item["suggested_relation"]
        source, target = objects.get(relation["source_id"]), objects.get(relation["target_id"])
        if (
            source is None
            or source["type"] != "risk"
            or target is None
            or target["type"] not in {"objective", "project"}
        ):
            raise ValidationError("Risk Review requires a visible Risk and Objective/Project.")
        pair = (source["id"], target["id"])
        if pair in pairs:
            raise ValidationError("Duplicate Risk Review pair.")
        pairs.add(pair)
        action = item["suggested_action"]
        if action and str(action["mitigates_risk_id"]) != source["id"]:
            raise ValidationError("Mitigation must reference the suggested Risk.")
        if not set(item["context_used"]) <= edges or len(set(item["context_used"])) != len(item["context_used"]):
            raise ValidationError("Context Relations must belong to the supplied snapshot.")
        cited = set()
        for evidence in item["evidence"]:
            obj = objects.get(evidence["object_id"])
            if obj is None or obj["version"] != evidence["version"]:
                raise ValidationError("Evidence must belong to the versioned snapshot.")
            field = evidence["field"]
            if field in {"title", "content"}:
                value = obj[field]
            elif field.startswith("properties:") and field[11:] in obj["properties"]:
                raw = obj["properties"][field[11:]]
                value = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, sort_keys=True)
            else:
                raise ValidationError("Evidence field unavailable in snapshot.")
            if not evidence["quote"].strip() or evidence["quote"] not in value:
                raise ValidationError("Evidence quote must be an exact snapshot excerpt.")
            cited.add(obj["id"])
        if not {source["id"], target["id"]} <= cited:
            raise ValidationError("Cite both Risk and Objective/Project.")
    # Preserve literal evidence strings; serializer normalization is used only for validation.
    return result


def access_run(user, workspace, run):
    binding, grant, identity, objects = binding_for(user=user, workspace=workspace, binding_id=run.binding_id)
    if identity != run.request_data["identity"]:
        raise RuntimeConflict({"code": "authorization_stale"})
    if run.request_data.get("skill") != "risk_review":
        raise ValidationError("This run did not invoke Risk Review.")
    ids = [o["id"] for o in run.request_data["context"]["objects"]]
    if objects.filter(pk__in=ids).count() != len(ids):
        raise RuntimeConflict({"code": "context_unavailable"})
    return binding, grant, objects


def proposal_actor(run, suggestion, *, metadata=None):
    return Actor(
        actor_type="agent",
        actor_id=run.binding.actor_id,
        run_id=run.pk,
        on_behalf_of=run.user_id,
        source="radar.skill.risk_review",
        correlation_id=run.pk,
        reason=suggestion["explanation"],
        confidence=suggestion["confidence"],
        metadata={
            "context": run.binding.context,
            "binding_id": str(run.binding_id),
            "context_hash": fingerprint(run.request_data["context"]),
            "evidence": suggestion["evidence"],
            "context_used": suggestion["context_used"],
            **(metadata or {}),
        },
    )


def command_input(workspace, suggestion, component):
    if component == "relation":
        relation = suggestion["suggested_relation"]
        kind = active_relation_types(workspace).filter(key="threatens").first()
        if kind is None:
            raise ValidationError("The workspace schema does not support threatens.")
        return "LinkObjects", {
            "source_id": relation["source_id"],
            "target_id": relation["target_id"],
            "relation_type_id": str(kind.pk),
        }
    action = suggestion["suggested_action"]
    return "CreateAction", {key: action[key] for key in ("title", "description", "next_step")} | {
        "mitigates_risk_ids": [action["mitigates_risk_id"]]
    }


def current_context(objects, grant, snapshot):
    """An explicit human edit obtains a fresh, field-filtered snapshot for its preview."""
    ids = [UUID(o["id"]) for o in snapshot["objects"]]
    visible = objects.filter(pk__in=ids)
    if visible.count() != len(ids):
        raise PermissionDenied("Original context is no longer available.")
    merged_objects, merged_edges, truncated = {}, {}, False
    for offset in range(0, len(ids), 10):
        part = load_context(visible, grant, ids[offset : offset + 10])
        merged_objects.update({o["id"]: o for o in part["objects"]})
        merged_edges.update({e["id"]: e for e in part["relations"]})
        truncated |= part["truncated"]
    from plane.radar.workspace_schema import schema_revision

    result = {
        "schema_revision": schema_revision(visible.first().workspace_id),
        "objects": sorted(merged_objects.values(), key=lambda o: o["id"]),
        "relations": sorted(merged_edges.values(), key=lambda e: e["id"])[:40],
        "truncated": truncated or len(merged_edges) > 40,
    }
    if len(json.dumps(result, ensure_ascii=True)) > 30000:
        result["truncated"] = True
        for obj in result["objects"]:
            obj["content"], obj["properties"] = obj["content"][:200], {}
    return result


def prepare_component(review, ordinal, component, grant, objects, *, edited=None, previous=None):
    run, suggestion = review.run, review.result["suggestions"][ordinal]
    name, data = command_input(run.workspace, suggestion, component)
    if edited is not None:
        data = edited
    parsed = INPUTS[name](data=data)
    parsed.is_valid(raise_exception=True)
    data = parsed.validated_data
    # An edit remains this skill's exact effect family; it cannot become an arbitrary writer.
    relation = suggestion["suggested_relation"]
    if component == "relation":
        kind = active_relation_types(run.workspace).filter(pk=data["relation_type_id"]).first()
        by_id = {str(o.pk): o.object_type.key for o in objects.filter(pk__in=[data["source_id"], data["target_id"]])}
        if (
            kind is None
            or kind.key != "threatens"
            or str(data["source_id"]) != relation["source_id"]
            or by_id.get(str(data["source_id"])) != "risk"
            or by_id.get(str(data["target_id"])) not in {"objective", "project"}
        ):
            raise ValidationError("Edit must remain Risk threatens Objective/Project.")
    elif (
        set(data) - {"title", "description", "next_step", "mitigates_risk_ids", "executor_person_ids"}
        or data["executor_person_ids"]
        or data["mitigates_risk_ids"] != [UUID(relation["source_id"])]
    ):
        raise ValidationError("Edit must remain a mitigation of the original Risk.")
    assertion = {
        "kind": "inferred",
        "confidence": suggestion["confidence"],
        "evidence_ids": sorted({e["object_id"] for e in suggestion["evidence"]}),
    }
    reviewed_context = (
        current_context(objects, grant, run.request_data["context"]) if previous else run.request_data["context"]
    )
    actor = proposal_actor(
        run,
        suggestion,
        metadata={
            "edited_by": str(run.user_id),
            "previous_proposal_id": str(previous.pk),
            "reviewed_context_hash": fingerprint(reviewed_context),
        }
        if previous
        else None,
    )
    plan = plan_command(
        actor=actor, workspace=run.workspace, name=name, data=data, evidence_ids=assertion["evidence_ids"]
    )
    refs = {UUID(pk) for pk in plan.dependencies}
    # All read dependencies must remain in the authorized run snapshot.
    # Legacy direct references are already included in the shared plan.
    if objects.filter(pk__in=refs).count() != len(refs) or not refs <= {
        UUID(o["id"]) for o in run.request_data["context"]["objects"]
    }:
        raise PermissionDenied("Command references must remain in the authorized run snapshot.")
    if name not in grant.commands:
        raise PermissionDenied("Configuration does not permit this proposed command.")
    check_grant(run.workspace, grant, name, data, plan=plan)
    versions = {str(o.pk): o.version for o in objects.filter(pk__in=refs)}
    revision = previous.revision + 1 if previous else 1
    envelope = {
        "command_name": name,
        "command_version": 1,
        "idempotency_key": f"risk-review:{run.pk}:{ordinal}:{component}:{revision}",
        "expected_versions": versions,
        "reason": actor.reason,
        "input": data,
        "assertion": assertion,
    }
    pending = execute_command(actor=actor, workspace=run.workspace, envelope=envelope)
    if pending["status"] != "pending_approval":
        raise RuntimeConflict({"code": "review_required"})
    human = Actor(
        actor_type="human",
        actor_id=run.user_id,
        source="radar.session.risk_review",
        correlation_id=run.pk,
        run_id=run.pk,
        reason="Save edited Risk Review" if previous else "Save Risk Review proposal",
        metadata={"previous_proposal_id": str(previous.pk) if previous else None},
    )
    return run_internal(
        actor=human,
        workspace=run.workspace,
        name="EditRiskReview" if previous else "SaveRiskReviewProposal",
        operation=lambda: RiskReviewProposal.objects.create(
            workspace=run.workspace,
            review=review,
            ordinal=ordinal,
            component=component,
            revision=revision,
            reviewed_context=reviewed_context,
            previous=previous,
            execution_id=pending["command_id"],
            created_by_id=run.user_id,
            updated_by_id=run.user_id,
        ),
    )


@transaction.atomic
def save_review(user, workspace, run, result):
    from plane.db.models import Workspace

    Workspace.objects.select_for_update().get(pk=workspace.pk)
    _, grant, objects = access_run(user, workspace, run)
    existing = RiskReview.objects.filter(run=run).first()
    if existing:
        return existing
    verify_snapshot(objects, run.request_data["context"])
    output = validate_output(result, run.request_data["context"])
    review = RiskReview.objects.create(run=run, result=output)
    for ordinal, item in enumerate(output["suggestions"]):
        prepare_component(review, ordinal, "relation", grant, objects)
        if item["suggested_action"] is not None:
            prepare_component(review, ordinal, "action", grant, objects)
    return review


@transaction.atomic
def resolve_proposal(user, workspace, proposal, *, decision, rationale, intent_hash, edited_input=None):
    from plane.db.models import Workspace

    Workspace.objects.select_for_update().get(pk=workspace.pk)
    proposal = RiskReviewProposal.objects.select_related("review__run__binding", "execution").get(pk=proposal.pk)
    run, execution = proposal.review.run, proposal.execution
    _, grant, objects = access_run(user, workspace, run)
    if execution.intent_hash != intent_hash:
        raise RuntimeConflict({"code": "intent_stale"})
    # A retry reports the saved result without asking the model or writing again.
    if decision == "accept" and execution.status in {"executed", "noop"}:
        return proposal
    if decision == "reject" and execution.status == "rejected":
        return proposal
    if decision == "edit" and hasattr(proposal, "replacement"):
        replacement = proposal.replacement
        expected = INPUTS[execution.command_name](data=edited_input)
        expected.is_valid(raise_exception=True)
        from plane.radar.mutation import json_value

        if replacement.execution.envelope["input"] != json_value(expected.validated_data):
            raise RuntimeConflict({"code": "edit_conflict"})
        return replacement
    if execution.status != "pending_approval":
        raise RuntimeConflict({"code": "proposal_closed"})
    human = Actor(
        actor_type="human",
        actor_id=user.pk,
        source="radar.session.risk_review",
        correlation_id=run.pk,
        run_id=run.pk,
        reason=rationale,
        metadata={"proposal_id": str(proposal.pk), "decision": decision},
    )
    if decision == "edit":
        # Prepare the replacement first: failure rolls back retirement and replacement.
        replacement = prepare_component(
            proposal.review,
            proposal.ordinal,
            proposal.component,
            grant,
            objects,
            edited=edited_input,
            previous=proposal,
        )
        review_command(
            actor=human,
            workspace=workspace,
            command_id=execution.pk,
            intent_hash=intent_hash,
            approve=False,
            rationale=rationale,
        )
        return replacement
    if decision == "accept":
        name = execution.command_name
        parsed = INPUTS[name](data=execution.envelope["input"])
        parsed.is_valid(raise_exception=True)
        refs = references(workspace, name, parsed.validated_data) | {
            UUID(pk) for pk in execution.envelope["assertion"]["evidence_ids"]
        }
        if name not in grant.commands or objects.filter(pk__in=refs).count() != len(refs):
            raise PermissionDenied("Proposal exceeds the effective configuration.")
        # review_command below replans and checks complete authority before acceptance.
    approval = review_command(
        actor=human,
        workspace=workspace,
        command_id=execution.pk,
        intent_hash=intent_hash,
        approve=decision == "accept",
        rationale=rationale,
    )
    if decision == "accept":
        suggestion = proposal.review.result["suggestions"][proposal.ordinal]
        actor = replace(
            proposal_actor(run, suggestion), approval_id=approval.pk, metadata=execution.actor_context["metadata"]
        )
        execute_command(
            actor=actor,
            workspace=workspace,
            envelope=command_envelope(execution),
        )
    return proposal
