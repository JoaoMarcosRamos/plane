"""Read-only managerial attention projection; no schema initialization or agent calls."""

from datetime import date
from zoneinfo import ZoneInfo

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import APIException

from plane.radar.models import RiskReviewProposal
from plane.radar.active import active_definitions, active_values, active_objects
from plane.radar.risk_review import access_run
from plane.radar.operational import deadline_projection


def overdue(value, today):
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value) < today
    except ValueError:
        return False


def attention_queue(workspace, user, timezone_name):
    now = timezone.now()
    today = now.astimezone(ZoneInfo(timezone_name)).date()
    groups = {"risks": [], "decisions": [], "overdue_actions": [], "suggestions": []}
    definitions = (
        active_definitions(workspace)
        .filter(object_type__key__in=["risk", "decision", "action"])
        .select_related("object_type")
    )
    defaults = {}
    for definition in definitions:
        defaults.setdefault(definition.object_type_id, {})[definition.key] = definition.config.get("default")
    values = active_values(workspace).select_related("definition")
    objects = (
        active_objects(workspace)
        .filter(
            object_type__key__in=["risk", "decision", "action"],
            object_type__is_active=True,
            object_type__deleted_at__isnull=True,
        )
        .select_related("object_type")
        .prefetch_related(Prefetch("property_values", queryset=values))
    )
    for obj in objects:
        properties = defaults.get(obj.object_type_id, {}).copy()
        properties.update({item.definition.key: item.value for item in obj.property_values.all()})
        item = {"id": str(obj.pk), "title": obj.title, "status": properties.get("status")}
        kind = obj.object_type.key
        if kind == "risk" and properties.get("status") in {"identified", "monitoring", "mitigating", "accepted"}:
            score = properties.get("score")
            high = isinstance(score, int) and not isinstance(score, bool) and score >= 15
            review_overdue = overdue(properties.get("review_date"), today)
            if high or review_overdue:
                groups["risks"].append(
                    item
                    | {"score": score, "review_date": properties.get("review_date"), "review_overdue": review_overdue}
                )
        elif kind == "decision" and properties.get("status") == "proposed":
            groups["decisions"].append(item)
        elif kind == "action" and properties.get("status") in {"todo", "in_progress", "waiting"}:
            deadline = deadline_projection(properties, timezone_name, now=now)
            if deadline["overdue"] or deadline["conflict"]:
                groups["overdue_actions"].append(item | {"due_date": properties.get("due_date"), "deadline": deadline})
    groups["risks"].sort(key=lambda item: (-(item["score"] or 0), item["review_date"] or "9999", item["id"]))
    groups["overdue_actions"].sort(
        key=lambda item: (item["deadline"]["due_at"] or item["due_date"] or "9999", item["id"])
    )

    proposals = (
        RiskReviewProposal.objects.filter(
            workspace=workspace,
            review__run__workspace=workspace,
            review__run__user=user,
            execution__status="pending_approval",
            execution__commandapproval__status="pending",
            execution__commandapproval__expires_at__gt=now,
            replacement__isnull=True,
        )
        .select_related("review__run", "execution")
        .order_by("created_at", "id")
    )
    accessible = {}
    for proposal in proposals:
        run = proposal.review.run
        if run.pk not in accessible:
            try:
                access_run(user, workspace, run)
                accessible[run.pk] = True
            except APIException:
                accessible[run.pk] = False
        if not accessible[run.pk]:
            continue
        suggestion = proposal.review.result["suggestions"][proposal.ordinal]
        context = {obj["id"]: obj for obj in proposal.reviewed_context["objects"]}
        payload = proposal.execution.envelope["input"]
        title = (
            payload["title"]
            if proposal.component == "action"
            else f"{context[payload['source_id']]['title']} → {context[payload['target_id']]['title']}"
        )
        groups["suggestions"].append(
            {
                "id": str(proposal.pk),
                "title": title,
                "component": proposal.component,
                "explanation": suggestion["explanation"],
                "confidence": suggestion["confidence"],
            }
        )
    return {"date": today.isoformat(), "timezone": timezone_name, **groups}
