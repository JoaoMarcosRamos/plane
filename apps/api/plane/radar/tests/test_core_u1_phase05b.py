"""C18 canonical deadlines/assignments, immutable paged history and reviewed backfill."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.commands import create_object
from plane.radar.commands.execution import execute_command, run_internal
from plane.radar.models import (
    Object,
    ObjectType,
    OperationalEntry,
    OperationalRecord,
    PropertyDefinition,
    PropertyValue,
    Provenance,
)
from plane.radar.operational import deadline_projection, operation_projection, history_page, validate_payload
from plane.radar.operational_backfill import preview_backfill, backfill
from .fixture_writes import fixture_write
from .test_commands import create, execute, envelope
from .test_core import url
from .test_core_u1_phase02 import edit
from .test_runtime_contract import bind, endpoint
from . import test_runtime_contract as runtime_tests

runtime = runtime_tests.runtime
pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def evidence(state):
    ctx = state[0]
    doc = create_object(
        actor=ctx[5],
        workspace=ctx[3],
        object_type=ObjectType.objects.get(workspace=ctx[3], key="document").pk,
        title="Evidence",
        content="<p>Observed</p>",
    )
    bind(state, doc, "DOC")
    return doc


def delegation(state, due=None):
    ctx = state[0]
    action = create(ctx, "action", description="Deliver")
    bind(state, action, "ACT")
    data = {
        "action_id": str(action.pk),
        "executor_id": str(state[5].pk),
        "context": "company:test",
        "due_at": due or (timezone.now() - timedelta(hours=1)).isoformat(),
    }
    result = execute(ctx, "DelegateAction", data)
    return action, data, result


def record(state, obj, data):
    return fixture_write(lambda: OperationalRecord.objects.create(workspace=state[0][3], object=obj, data=data))


def counts():
    return tuple(
        model.objects.count() for model in (Object, OperationalEntry, OperationalRecord, PropertyValue, Provenance)
    )


def test_overdue_delegation_without_due_date_matches_today_object_and_runtime(runtime, client):
    ctx = runtime[0]
    action, _, result = delegation(runtime)
    assert not OperationalRecord.objects.filter(object=action).exists()
    entry = OperationalEntry.objects.get(object=action)
    action.refresh_from_db()
    assert entry.object_version == action.version == result["versions_after"][str(action.pk)]
    assert (
        entry.created_provenance.command_id == result["command_id"]
        or str(entry.created_provenance.command_id) == result["command_id"]
    )
    snapshot = client.get(url(ctx, f"objects/{action.pk}/operations/"), {"timezone": "America/Bahia"})
    queue = client.get(url(ctx, "today/"), {"timezone": "America/Bahia"})
    item = next(item for item in queue.data["overdue_actions"] if item["id"] == str(action.pk))
    assert item["due_date"] is None and item["deadline"] == snapshot.data["deadline"]
    code = (
        __import__("plane.radar.models", fromlist=["RuntimeObjectIdentity"])
        .RuntimeObjectIdentity.objects.get(object=action)
        .external_id
    )
    query = runtime[1].post(
        endpoint(runtime, "query"),
        {"method": "read_entity", "parameters": {"entity_id": code, "timezone": "America/Bahia"}},
        format="json",
    )
    assert query.data["metadata"]["operation_data"]["deadline"] == snapshot.data["deadline"]
    assert "reviews" not in query.data["metadata"]["operation_data"]


def test_exact_instants_date_semantics_timezone_and_conflicting_deadlines():
    now = datetime(2026, 10, 6, 2, 0, 0, 123456, tzinfo=dt_timezone.utc)
    properties = {"due_at": "2026-10-05T23:00:00.123455-03:00", "due_date": "2026-10-05"}
    bahia = deadline_projection(properties, "America/Bahia", now=now)
    assert bahia["source"] == "due_at" and bahia["overdue"] and not bahia["conflict"]
    utc = deadline_projection(properties, "UTC", now=now)
    assert utc["source"] == "conflict" and utc["effective_at"] is None and utc["effective_date"] is None
    assert not deadline_projection({"due_date": "2026-10-05"}, "America/Bahia", now=now)["overdue"]
    with pytest.raises(ValidationError):
        deadline_projection({}, "bad/zone")


def test_assignment_projection_follows_relations_and_property_without_changing_terms(runtime):
    ctx = runtime[0]
    action, _, _ = delegation(runtime)
    original = deepcopy(OperationalEntry.objects.get(object=action).payload)
    relation = __import__("plane.radar.models", fromlist=["Relation"]).Relation.objects.get(
        source=action, relation_type__key="assigned_to"
    )
    execute(ctx, "UnlinkObjects", {"relation_id": str(relation.pk)})
    execute(
        ctx,
        "LinkObjects",
        {
            "source_id": str(action.pk),
            "target_id": str(runtime[4].pk),
            "relation_type_id": str(relation.relation_type_id),
        },
    )
    snapshot = operation_projection(action)
    terms = snapshot["operation_data"]["assignment"]
    assert snapshot["executors"] == [str(runtime[4].pk)] and terms["executor_ids"] == snapshot["executors"]
    assert terms["state"] == "changed" and terms["acceptances"] == {} and terms["accepted_at"] is None
    execute(
        ctx,
        "UpdateObject",
        {"object_id": str(action.pk), "set_properties": {"due_at": (timezone.now() + timedelta(days=3)).isoformat()}},
    )
    assert operation_projection(action)["deadline"]["due_at"] != original["due_at"]
    assert OperationalEntry.objects.get(object=action).payload == original


def test_reviews_page_and_replay_have_no_unbounded_json_and_keep_evidence_actor_and_versions(runtime, client):
    ctx = runtime[0]
    obj, doc = create(ctx), evidence(runtime)
    bind(runtime, obj, "OBJ")
    data = {"target_id": str(obj.pk), "evidence_id": str(doc.pk), "assessment": "Reviewed", "context": "company:test"}
    last = None
    for index in range(23):
        request = envelope(ctx, "ReviewObject", {**data, "assessment": f"Review {index}"})
        last = execute_command(actor=ctx[5], workspace=ctx[3], envelope=request)
    before = counts()
    assert execute_command(actor=ctx[5], workspace=ctx[3], envelope=request) == last and counts() == before
    assert not OperationalRecord.objects.filter(object=obj).exists()
    first = client.get(url(ctx, f"objects/{obj.pk}/operational-history/"), {"limit": 7, "kind": "review"})
    assert len(first.data["items"]) == 7 and first.data["next_cursor"]
    all_ids = [row["id"] for row in first.data["items"]]
    cursor = first.data["next_cursor"]
    while cursor:
        response = client.get(
            url(ctx, f"objects/{obj.pk}/operational-history/"), {"limit": 7, "kind": "review", "cursor": cursor}
        )
        all_ids.extend(row["id"] for row in response.data["items"])
        cursor = response.data["next_cursor"]
    assert len(all_ids) == len(set(all_ids)) == 23
    entry = OperationalEntry.objects.get(pk=all_ids[0])
    assert entry.evidence == doc and entry.actor_type == "human" and entry.actor_id == ctx[0].pk
    assert first.data["items"][0]["command_id"] == last["command_id"]
    assert len(operation_projection(obj)["operation_data"]) == 1
    with pytest.raises(PermissionDenied):
        run_internal(actor=ctx[5], workspace=ctx[3], name="AttemptHistoryEdit", operation=lambda: entry.save())
    assert client.get(url(ctx, f"objects/{obj.pk}/operational-history/"), {"cursor": "bad"}).status_code == 400
    assert (
        client.get(
            url(ctx, f"objects/{doc.pk}/operational-history/"), {"cursor": first.data["next_cursor"], "kind": "review"}
        ).status_code
        == 400
    )


def test_measurements_are_paged_and_current_projection_uses_active_canonical_values(runtime, client):
    ctx = runtime[0]
    obj, doc = create(ctx, "indicator"), evidence(runtime)
    bind(runtime, obj, "IND")
    for index in range(3):
        execute(
            ctx,
            "RecordMeasurement",
            {
                "indicator_id": str(obj.pk),
                "evidence_id": str(doc.pk),
                "context": "company:test",
                "value": index,
                "measured_at": (timezone.now() - timedelta(days=10 - index)).isoformat(),
            },
        )
    page = history_page(ctx[3], obj, kind="measurement", limit=2)
    assert len(page["items"]) == 2 and page["next_cursor"]
    assert operation_projection(obj)["operation_data"]["measurement"]["value"] == 2
    definition = PropertyDefinition.objects.get(object_type=obj.object_type, key="current")
    edit(ctx, definition, {"is_active": False})
    assert "measurement" not in operation_projection(obj)["operation_data"]
    assert client.get(url(ctx, f"objects/{obj.pk}/operational-history/")).data["items"]


def test_legacy_backfill_dry_run_and_apply_preserve_raw_precision_sources_and_unknown_authorship(runtime):
    ctx = runtime[0]
    obj = create(ctx, "action", description="Legacy", due_date="2026-10-08")
    due = "2026-10-07T13:45:12.123456-03:00"
    source = {
        "assignment": {
            "executor_id": str(runtime[5].pk),
            "executor_ids": [str(runtime[5].pk)],
            "due_at": due,
            "next_review_at": None,
            "state": "proposed",
            "accepted_at": None,
            "acceptances": {},
            "proposed_by": str(ctx[0].pk),
            "proposed_at": "2026-10-06T12:00:00-03:00",
        }
    }
    old = record(runtime, obj, source)
    before = counts()
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3], timezone_name="America/Bahia")
    assert counts() == before and plan["counts"]["blocking_records"] == 0
    assert set(plan["records"][0]["divergences"]) == {"deadline_conflict", "executor_sets_differ_preserve_relations"}
    with pytest.raises(ValidationError):
        backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash="0" * 64)
    result = backfill(
        actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"], timezone_name="America/Bahia"
    )
    assert result["created_entries"] == result["materialized_deadlines"] == 1
    assert PropertyValue.objects.get(object=obj, definition__key="due_at").value == due
    entry = OperationalEntry.objects.get(object=obj)
    assert entry.source_data == source["assignment"] and entry.actor_type == "unknown" and entry.object_version is None
    assert (
        entry.created_provenance.actor_id == ctx[0].pk
        and entry.created_provenance.command_name == "BackfillOperationalHistory"
    )
    old.refresh_from_db()
    assert old.data == source and old.backfill_hash
    assert operation_projection(obj, timezone_name="America/Bahia")["deadline"]["conflict"]
    before = counts()
    assert (
        backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"], timezone_name="America/Bahia")[
            "created_entries"
        ]
        == 0
    )
    assert counts() == before


def test_partial_legacy_payloads_missing_times_keep_unknowns_and_migrate_each_history_item(runtime):
    ctx = runtime[0]
    obj, doc = create(ctx), evidence(runtime)
    rows = [{"assessment": f"Historical {index}", "evidence_id": str(doc.pk)} for index in range(3)]
    record(runtime, obj, {"reviews": rows, "review": rows[-1]})
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3])
    assert plan["counts"]["entries"] == 3
    backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"])
    assert all(
        row.occurred_at is None and row.actor_id is None and row.object_version is None
        for row in OperationalEntry.objects.filter(object=obj)
    )
    assert [row["payload"]["assessment"] for row in history_page(ctx[3], obj)["items"]] == [
        "Historical 2",
        "Historical 1",
        "Historical 0",
    ]


@pytest.mark.parametrize(
    "failure", ["foreign_reference", "invalid_kind_data", "conflicting_current", "changed_archive"]
)
def test_legacy_conflicts_are_reported_and_roll_back_everything(runtime, failure):
    ctx = runtime[0]
    obj = create(ctx, "action", description="Legacy")
    source = {
        "assignment": {"executor_ids": [str(runtime[5].pk)], "due_at": "2026-10-08T12:00:00Z", "state": "proposed"}
    }
    if failure == "foreign_reference":
        source["assignment"]["executor_ids"] = [str(uuid4())]
    if failure == "invalid_kind_data":
        source["assignment"]["due_at"] = "not a datetime"
    old = record(runtime, obj, source)
    if failure == "conflicting_current":
        execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"due_at": "2026-10-10T12:00:00Z"}})
    if failure == "changed_archive":
        fixture_write(lambda: OperationalRecord.objects.filter(pk=old.pk).update(backfill_hash="0" * 64))
    before = counts()
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3])
    assert plan["counts"]["blocking_records"] == 1
    with pytest.raises(ValidationError):
        backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"])
    assert counts() == before


def test_reconciled_archive_no_longer_accepts_old_writer_changes_and_new_operations_do_not_dual_write(runtime):
    ctx = runtime[0]
    obj, doc = create(ctx), evidence(runtime)
    bind(runtime, obj, "OBJ")
    old = record(runtime, obj, {})
    args = {"target_id": str(obj.pk), "evidence_id": str(doc.pk), "assessment": "New", "context": "company:test"}
    with pytest.raises(ValidationError) as exc:
        execute(ctx, "ReviewObject", args)
    assert exc.value.detail["code"] == "operational_backfill_required"
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3])
    backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"])
    execute(ctx, "ReviewObject", args)
    old.refresh_from_db()
    assert old.data == {} and OperationalEntry.objects.filter(object=obj).count() == 1
    fixture_write(
        lambda: OperationalRecord.objects.filter(pk=old.pk).update(
            data={"reviews": []}, last_provenance_id=OperationalEntry.objects.get(object=obj).created_provenance_id
        )
    )
    with pytest.raises(ValidationError):
        execute(ctx, "ReviewObject", args)


def test_historical_access_after_retirement_remains_scoped_and_guest_cannot_backfill(runtime, client):
    ctx = runtime[0]
    action, _, _ = delegation(runtime)
    edit(ctx, action.object_type, {"is_active": False})
    assert client.get(url(ctx, f"objects/{action.pk}/operations/")).status_code == 404
    assert client.get(url(ctx, f"objects/{action.pk}/operational-history/")).status_code == 200
    with pytest.raises(PermissionDenied):
        preview_backfill(actor=replace(ctx[5], actor_id=ctx[1].pk), workspace=ctx[3])
    client.force_authenticate(ctx[2])
    assert client.get(url(ctx, f"objects/{action.pk}/operational-history/")).status_code == 403


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("review", {"assessment": "x"}),
        ("measurement", {"value": float("inf")}),
        ("delegation", {"executor_ids": [], "due_at": "2026-10-06T00:00:00Z", "state": "proposed"}),
    ],
)
def test_records_validate_before_persisting(kind, payload):
    with pytest.raises(ValidationError):
        validate_payload(kind, payload)


def test_current_and_paged_reads_never_select_unbounded_archive_or_provenance(runtime):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    ctx = runtime[0]
    action, _, _ = delegation(runtime)
    with CaptureQueriesContext(connection) as queries:
        assert operation_projection(action)["operation_data"]["assignment"]
        assert len(history_page(ctx[3], action, limit=1)["items"]) == 1
    selected = [
        query["sql"].split(" FROM ")[0] for query in queries.captured_queries if query["sql"].startswith("SELECT")
    ]
    assert not any('"source_data"' in sql or '"changes"' in sql or '"data"' in sql for sql in selected)
    assert len(queries) <= 10
    with CaptureQueriesContext(connection) as page_queries:
        history_page(ctx[3], action, limit=100)
    assert len(page_queries) == 1


def test_backfill_export_preserves_acceptance_evidence_and_original_offsets(runtime):
    from plane.radar.operational_backfill import export_workspace

    ctx = runtime[0]
    obj, doc = create(ctx, "action", description="Legacy accepted"), evidence(runtime)
    person = str(runtime[5].pk)
    terms = {
        "executor_ids": [person],
        "state": "accepted",
        "due_at": "2026-10-09T12:00:00.987654-03:00",
        "proposed_at": "2026-10-06T12:00:00-03:00",
        "accepted_at": "2026-10-06T13:00:00-03:00",
        "acceptances": {person: {"accepted_at": "2026-10-06T13:00:00-03:00", "evidence_id": str(doc.pk)}},
    }
    archive = record(runtime, obj, {"assignment": terms})
    before = (archive.created_at, archive.updated_at)
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3])
    backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"])
    archive.refresh_from_db()
    assert (archive.created_at, archive.updated_at) == before
    exported = list(export_workspace(ctx[3]))
    assert exported[0]["data"]["assignment"] == exported[1]["source_data"] == terms
    assert exported[1]["actor_type"] == "unknown" and exported[1]["object_version"] is None
    assert exported[1]["payload"]["acceptances"][person]["evidence_id"] == str(doc.pk)


def test_backfill_reviewed_plan_changes_when_current_facts_change(runtime):
    ctx = runtime[0]
    obj = create(ctx, "action", description="Legacy")
    record(
        runtime,
        obj,
        {"assignment": {"executor_ids": [str(runtime[5].pk)], "due_at": "2026-10-08T12:00:00Z", "state": "proposed"}},
    )
    plan = preview_backfill(actor=ctx[5], workspace=ctx[3])
    execute(ctx, "UpdateObject", {"object_id": str(obj.pk), "set_properties": {"due_date": "2026-10-09"}})
    before = counts()
    with pytest.raises(ValidationError):
        backfill(actor=ctx[5], workspace=ctx[3], reviewed_hash=plan["reviewed_hash"])
    assert counts() == before


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("delegation", {"executor_ids": [str(uuid4())], "due_at": "2026-10-08T12:00:00", "state": "proposed"}),
        ("delegation", {"executor_ids": [str(uuid4())], "due_at": "2026-10-08T12:00:00Z", "state": "accepted"}),
        ("review", {"assessment": "x", "evidence_id": str(uuid4()), "at": "2026-10-06T12:00:00"}),
    ],
)
def test_typed_history_rejects_naive_instants_and_unproven_accepted_state(kind, payload):
    with pytest.raises(ValidationError):
        validate_payload(kind, payload)


def test_delegation_preview_includes_canonical_property_and_history_authority(runtime, client):
    from plane.radar.workspace_schema import schema_revision

    ctx = runtime[0]
    action = create(ctx, "action", description="Planned delegation")
    bind(runtime, action, "ACT")
    before = counts()
    response = client.post(
        url(ctx, "commands/preview/"),
        {
            "command_name": "DelegateAction",
            "command_version": 1,
            "reason": "Review all effects",
            "expected_schema_revision": schema_revision(ctx[3]),
            "input": {
                "action_id": str(action.pk),
                "executor_id": str(runtime[5].pk),
                "context": "company:test",
                "due_at": "2026-10-09T12:00:00Z",
            },
        },
        format="json",
    )
    assert response.status_code == 200 and counts() == before
    plan = response.data["effect_plan"]
    assert {"due_at", "assignment"} <= set(plan["authority"]["fields"])
    assert any(change["model"] == "radar.OperationalEntry" for change in plan["changes"])
    assert set(response.data["expected_versions"]) == {str(action.pk), str(runtime[5].pk)}


@pytest.mark.parametrize("metadata", [{"value_type": "string"}, {"is_active": False}])
def test_delegation_does_not_write_to_incompatible_or_retired_deadline_metadata(runtime, metadata):
    ctx = runtime[0]
    action = create(ctx, "action", description="Deadline contract")
    bind(runtime, action, "ACT")
    definition = PropertyDefinition.objects.get(object_type=action.object_type, key="due_at")
    if "value_type" in metadata:
        # Represents an existing local definition preserved by migration 0016.
        # The current editor already forbids changing a property's kind.
        fixture_write(lambda: PropertyDefinition.objects.filter(pk=definition.pk).update(**metadata))
    else:
        edit(ctx, definition, metadata)
    before = counts()
    with pytest.raises(ValidationError, match="active due_at datetime"):
        execute(
            ctx,
            "DelegateAction",
            {
                "action_id": str(action.pk),
                "executor_id": str(runtime[5].pk),
                "context": "company:test",
                "due_at": "2026-10-09T12:00:00Z",
            },
        )
    assert counts() == before


def test_runtime_deadline_projection_does_not_replace_a_workspace_property(runtime):
    from plane.radar.commands.schema import preview_upgrade, upgrade_schema
    from plane.radar.ontology.package import package_definitions
    from plane.radar.workspace_schema import schema_revision
    from plane.radar.models import RuntimeObjectIdentity

    ctx = runtime[0]
    candidate = package_definitions()
    candidate["properties:action.deadline"] = {
        "name": "Local planning note",
        "value_type": "string",
        "config": {},
        "is_required": False,
        "is_active": True,
    }
    plan = preview_upgrade(
        actor=ctx[5], workspace=ctx[3], expected_revision=schema_revision(ctx[3]), definitions=candidate
    )
    upgrade_schema(
        actor=ctx[5],
        workspace=ctx[3],
        expected_revision=plan["schema_revision"],
        reviewed_hash=plan["candidate_hash"],
        definitions=candidate,
        version="3.2.0+deadline",
    )
    action = create(ctx, "action", description="Preserve local semantics", deadline="A workspace planning note")
    bind(runtime, action, "ACT")
    execute(
        ctx,
        "DelegateAction",
        {
            "action_id": str(action.pk),
            "executor_id": str(runtime[5].pk),
            "context": "company:test",
            "due_at": "2026-10-09T12:00:00Z",
        },
    )
    response = runtime[1].post(
        endpoint(runtime, "query"),
        {
            "method": "read_entity",
            "parameters": {
                "entity_id": RuntimeObjectIdentity.objects.get(object=action).external_id,
                "timezone": "America/Bahia",
            },
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["metadata"]["deadline"] == "A workspace planning note"
    assert (
        response.data["metadata"]["operation_data"]["deadline"]
        == operation_projection(action, timezone_name="America/Bahia")["deadline"]
    )
