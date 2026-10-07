from datetime import datetime, timezone as dt_timezone

import pytest
from django.utils import timezone

from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, Provenance, RiskReviewProposal
from .test_commands import ready, create as create_fixture  # noqa: F401
from .test_risk_review import scenario, product, runtime, prepare, resolve  # noqa: F401
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def create(ctx, kind, **properties):
    # Build canonical initial states, then arrange terminal states only in the test fixture.
    status = properties.pop("status", None)
    required = {
        "risk": {"description": "Licensing risk"},
        "action": {"description": "Follow up"},
        "decision": {"context": "Licensing", "decision": "Choose an alternative", "rationale": "Delivery"},
    }[kind]
    obj = create_fixture(ctx, kind, **(required | properties))
    if status:
        fixture_write(lambda: PropertyValue.objects.filter(object=obj, definition__key="status").update(value=status))
    return obj


def url(workspace):
    return f"/api/workspaces/{workspace.slug}/radar/today/"


def test_attention_filters_defaults_ordering_and_no_writes(ready, client, monkeypatch):  # noqa: F811
    high = create(ready, "risk", likelihood=3, impact=5)
    critical = create(ready, "risk", likelihood=5, impact=5)
    review = create(ready, "risk", review_date="2026-10-04")
    create(ready, "risk", likelihood=5, impact=5, status="closed")
    create(ready, "risk", likelihood=3, impact=4, review_date="2026-10-05")
    create(ready, "risk")
    pending = create(ready, "decision")
    for status in ["decided", "superseded", "revoked"]:
        create(ready, "decision", status=status)
    overdue = create(ready, "action", due_date="2026-10-04")
    oldest = create(ready, "action", due_date="2026-10-01", status="waiting")
    create(ready, "action", due_date="2026-10-05")
    create(ready, "action", due_date="2026-10-06")
    create(ready, "action")
    for status in ["done", "cancelled"]:
        create(ready, "action", due_date="2026-10-01", status=status)
    deleted = create(ready, "risk", likelihood=5, impact=5)
    fixture_write(lambda: Object.objects.filter(pk=deleted.pk).update(deleted_at=timezone.now()))
    before = (Object.objects.count(), PropertyValue.objects.count(), Provenance.objects.count())
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 5, 12, tzinfo=dt_timezone.utc))
    response = client.get(url(ready[3]), {"timezone": "America/Bahia"})
    assert response.status_code == 200, response.data
    assert [item["id"] for item in response.data["risks"]] == [str(critical.pk), str(high.pk), str(review.pk)]
    assert response.data["risks"][-1]["review_overdue"] is True
    assert [item["id"] for item in response.data["decisions"]] == [str(pending.pk)]
    assert [item["id"] for item in response.data["overdue_actions"]] == [str(oldest.pk), str(overdue.pk)]
    assert response.data["suggestions"] == []
    assert response.data["date"] == "2026-10-05"
    assert before == (Object.objects.count(), PropertyValue.objects.count(), Provenance.objects.count())


def test_local_day_boundary_and_timezone_validation(ready, client, monkeypatch):  # noqa: F811
    create(ready, "action", due_date="2026-10-04")
    monkeypatch.setattr(timezone, "now", lambda: datetime(2026, 10, 5, 1, tzinfo=dt_timezone.utc))
    assert client.get(url(ready[3]), {"timezone": "UTC"}).data["overdue_actions"]
    local = client.get(url(ready[3]), {"timezone": "America/Bahia"})
    assert local.data["date"] == "2026-10-04" and local.data["overdue_actions"] == []
    assert client.get(url(ready[3]), {"timezone": "invalid/zone"}).status_code == 400
    assert client.get(url(ready[3]), {"timezone": ""}).status_code == 400


def test_workspace_access_and_empty_read_does_not_seed(context, client):
    before = (ObjectType.objects.count(), PropertyDefinition.objects.count(), Provenance.objects.count())
    response = client.get(url(context[3]))
    assert response.status_code == 200
    assert all(response.data[key] == [] for key in ["risks", "decisions", "overdue_actions", "suggestions"])
    assert before == (ObjectType.objects.count(), PropertyDefinition.objects.count(), Provenance.objects.count())
    assert client.get(url(context[4])).status_code == 403
    client.force_authenticate(user=context[2])
    assert client.get(url(context[3])).status_code == 403
    client.force_authenticate(user=None)
    assert client.get(url(context[3])).status_code in {401, 403}


def test_only_live_properties_and_types_contribute(ready, client):  # noqa: F811
    risk = create(ready, "risk", likelihood=5, impact=5)
    fixture_write(
        lambda: PropertyValue.objects.filter(object=risk, definition__key="score").update(deleted_at=timezone.now())
    )
    assert client.get(url(ready[3])).data["risks"] == []
    create(ready, "risk", likelihood=5, impact=5)
    fixture_write(lambda: ObjectType.objects.filter(workspace=ready[3], key="risk").update(is_active=False))
    assert client.get(url(ready[3])).data["risks"] == []


def test_pending_proposals_focus_and_human_resolution(scenario):  # noqa: F811
    proposals = prepare(scenario).data["proposals"]
    ctx, client = scenario[0][0][0], scenario[0][2]
    response = client.get(url(ctx[3]))
    assert {item["id"] for item in response.data["suggestions"]} == {p["id"] for p in proposals}
    focused = client.get(f"/api/workspaces/{ctx[3].slug}/radar/risk-reviews/", {"proposal": proposals[0]["id"]})
    assert len(focused.data["runs"]) == 1
    assert proposals[0]["id"] in {p["id"] for p in focused.data["proposals"]}
    assert resolve(scenario, proposals[0], "reject").status_code == 200
    assert [p["id"] for p in client.get(url(ctx[3])).data["suggestions"]] == [proposals[1]["id"]]
    client.force_authenticate(user=ctx[1])
    assert client.get(url(ctx[3])).data["suggestions"] == []
    assert client.get(f"/api/workspaces/{ctx[3].slug}/radar/risk-reviews/", {"proposal": proposals[1]["id"]}).data == {
        "runs": [],
        "proposals": [],
    }


@pytest.mark.parametrize("change", ["expires", "grant", "deleted_context", "edit"])
def test_expired_inaccessible_and_superseded_suggestions(scenario, change):  # noqa: F811
    proposals = prepare(scenario).data["proposals"]
    ctx, client = scenario[0][0][0], scenario[0][2]
    if change == "expires":
        from plane.radar.models import CommandApproval

        fixture_write(lambda: CommandApproval.objects.update(expires_at=timezone.now()))
    elif change == "grant":
        from plane.radar.models import ActorGrant

        fixture_write(lambda: ActorGrant.objects.filter(actor_id=scenario[0][1].actor_id).update(is_active=False))
    elif change == "deleted_context":
        fixture_write(lambda: Object.objects.filter(pk=scenario[4].pk).update(deleted_at=timezone.now()))
    else:
        action = next(p for p in proposals if p["component"] == "action")
        edited = resolve(scenario, action, "edit", edited_input={**action["input"], "title": "Revised action"})
        assert edited.status_code == 200
        result = client.get(url(ctx[3])).data["suggestions"]
        assert action["id"] not in {p["id"] for p in result}
        assert next(p for p in result if p["id"] == edited.data["id"])["title"] == "Revised action"
        return
    assert client.get(url(ctx[3])).data["suggestions"] == []
    assert RiskReviewProposal.objects.count() == 2
