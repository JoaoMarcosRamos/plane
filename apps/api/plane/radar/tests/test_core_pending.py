"""C13 bounded reads, C14 lock observation and cross-layer acceptance."""

import json
import logging
from uuid import UUID, uuid4
from time import perf_counter
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from plane.db.models import WorkspaceMember
from plane.radar.commands import create_object, initialize_object_types, create_relation
from plane.radar.models import Object, ObjectType, RelationType
from plane.radar.commands.execution import run_internal
from .fixture_writes import fixture_write
from .test_core import url
from . import test_runtime_contract as runtime_tests

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def populate(context, count=110):
    types = initialize_object_types(actor=context[5], workspace=context[3])
    selected = next(t for t in types if t.key == "objective")
    # Increasing fixtures exercise query/payload limits without paying command setup per row.
    objects = fixture_write(
        lambda: list(
            [
                Object.objects.create(
                    id=UUID(int=i + 1),
                    workspace=context[3],
                    object_type=selected,
                    title=f"Item {i:04}",
                    content="x" * 10000,
                )
                for i in range(count)
            ]
        )
    )
    return selected, objects


def test_summary_pages_search_stable_order_and_scope(context, client):
    selected, objects = populate(context)
    first = client.get(url(context), {"limit": 7})
    assert len(first.data) == 7 and first.data[0]["id"] == str(objects[0].pk)
    assert "content" not in first.data[0] and "object_type_detail" not in first.data[0]
    cursor = first["X-Radar-Next-Cursor"]
    second = client.get(url(context), {"limit": 7, "cursor": cursor})
    assert second.data[0]["id"] == str(objects[7].pk)
    assert client.get(url(context), {"cursor": cursor, "q": "Item"}).status_code == 400
    assert client.get(url(context), {"cursor": cursor + "bad"}).status_code == 400
    found = client.get(url(context), {"q": "0109", "object_type": str(selected.pk)})
    assert [row["id"] for row in found.data] == [str(objects[109].pk)]
    assert client.get(url(context), {"object_type": str(uuid4())}).data == []


@pytest.mark.parametrize("limit", [0, 101, "bad", -1])
def test_invalid_page_limits(context, client, limit):
    assert client.get(url(context), {"limit": limit}).status_code == 400


def test_cursor_invalidated_by_schema_change_and_other_workspace(context, client):
    selected, _ = populate(context)
    cursor = client.get(url(context), {"limit": 1})["X-Radar-Next-Cursor"]
    from .test_core_u1_phase02 import edit

    edit(context, selected, {"name": "Changed"})
    assert client.get(url(context), {"cursor": cursor}).status_code == 400
    WorkspaceMember.objects.create(workspace=context[4], member=context[0], role=15)
    assert client.get(f"/api/workspaces/{context[4].slug}/radar/objects/", {"cursor": cursor}).status_code == 400


def test_relation_candidates_cardinality_pairs_direction_and_authority(context, client):
    _, objects = populate(context)
    anchor = create_object(
        actor=context[5],
        workspace=context[3],
        object_type=ObjectType.objects.get(workspace=context[3], key="project").pk,
        title="Anchor",
    )
    kind = fixture_write(
        lambda: RelationType.objects.create(
            workspace=context[3],
            key="one",
            forward_label="one",
            reverse_label="reverse",
            source_types=["project"],
            target_types=["objective"],
            allowed_pairs=[["project", "objective"]],
            cardinality="0..1",
        )
    )
    params = {"relation_type": str(kind.pk), "object_id": str(anchor.pk), "q": "0109"}
    found = client.get(url(context), params)
    assert [row["id"] for row in found.data] == [str(objects[-1].pk)]
    create_relation(
        actor=context[5], workspace=context[3], relation_type_id=kind.pk, source_id=anchor.pk, target_id=objects[0].pk
    )
    assert client.get(url(context), params).data == []
    incoming = {"relation_type": str(kind.pk), "object_id": str(objects[-1].pk), "direction": "incoming"}
    assert client.get(url(context), incoming).data == []  # source is occupied, even at another target
    assert client.get(url(context), {**params, "direction": "bad"}).status_code == 400
    assert client.get(url(context), {**params, "object_id": str(uuid4())}).status_code == 404
    WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(role=5)
    assert client.get(url(context)).status_code == 200
    assert client.get(url(context), params).status_code == 403


def test_relation_pages_include_only_scoped_endpoint_summaries(context, client):
    _, objects = populate(context)
    kind = fixture_write(
        lambda: RelationType.objects.create(
            workspace=context[3],
            key="many",
            forward_label="many",
            reverse_label="reverse",
            source_types=["objective"],
            target_types=["objective"],
            cardinality="0..n",
        )
    )
    anchor = objects[0]
    for obj in objects[1:5]:
        create_relation(
            actor=context[5], workspace=context[3], relation_type_id=kind.pk, source_id=obj.pk, target_id=anchor.pk
        )
    endpoint = url(context, f"objects/{anchor.pk}/relations/")
    first = client.get(endpoint, {"limit": 2})
    assert len(first.data["relations"]) == len(first.data["endpoints"]) == 2
    assert all("content" not in item for item in first.data["endpoints"])
    second = client.get(endpoint, {"limit": 2, "cursor": first.data["next_cursor"]})
    assert len(second.data["relations"]) == 2 and second.data["next_cursor"] is None
    assert {r["id"] for r in first.data["relations"]}.isdisjoint(r["id"] for r in second.data["relations"])


def test_creation_capability_filter_and_invalid_query(context, client):
    populate(context, 2)
    assert len(client.get(url(context), {"capability": "CreateObject"}).data) == 2
    assert client.get(url(context), {"capability": "UpdateObject"}).status_code == 400
    assert client.get(url(context), {"capability": "unknown"}).status_code == 400
    assert client.get(url(context), {"object_type": "bad"}).status_code == 400
    assert client.get(url(context), {"q": "x" * 256}).status_code == 400


def test_payload_and_selected_rows_bounded_with_growing_fixture(context, client):
    _, objects = populate(context, 10)
    observations = []
    for size in (10, 110, 1010):
        if size > 10:
            selected = objects[0].object_type
            fixture_write(
                lambda: list(
                    [
                        Object.objects.create(
                            workspace=context[3], object_type=selected, title="Extra", content="x" * 10000
                        )
                        for _ in range(size - Object.objects.filter(workspace=context[3]).count())
                    ]
                )
            )
        started = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url(context), {"limit": 5})
        observations.append(
            {
                "fixture": size,
                "rows": len(response.data),
                "bytes": len(response.content),
                "queries": len(queries),
                "elapsed_ms": (perf_counter() - started) * 1000,
            }
        )
        object_select = [q["sql"] for q in queries if 'FROM "radar_objects"' in q["sql"]]
        assert all("LIMIT 6" in sql for sql in object_select)
        assert all('"radar_objects"."content"' not in sql for sql in object_select)
    assert len({row["bytes"] for row in observations}) == 1
    assert len({row["queries"] for row in observations}) == 1
    print("C13_BASELINE=" + json.dumps(observations))


def test_lock_observation_success_rollback_and_nested(context, caplog):
    caplog.set_level(logging.INFO, logger="plane.radar.locks")

    def nested():
        return run_internal(actor=context[5], workspace=context[3], name="Nested", operation=lambda: 1)

    assert run_internal(actor=context[5], workspace=context[3], name="Outer", operation=nested) == 1
    records = [r for r in caplog.records if r.msg == "radar_workspace_lock_finished"]
    assert len(records) == 1 and records[0].outcome == "committed"
    assert records[0].wait_ms >= 0 and records[0].held_ms >= 0

    def fail():
        raise ValueError("rollback")

    with pytest.raises(ValueError):
        run_internal(actor=context[5], workspace=context[3], name="Fail", operation=fail)
    assert caplog.records[-1].outcome == "rollback"


@pytest.mark.django_db(transaction=True)
def test_workspace_lock_concurrency_baseline(context, caplog):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import close_old_connections, connections
    from plane.db.models import Workspace
    from plane.radar.locks import observed_atomic, lock_workspace

    caplog.set_level(logging.INFO, logger="plane.radar.locks")
    acquired, competing = Event(), Event()

    @observed_atomic
    def hold():
        lock_workspace(context[3], operation="baseline_hold")
        acquired.set()
        assert competing.wait(10)
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT pg_sleep(0.2)")

    @observed_atomic
    def probe(workspace, operation):
        assert acquired.wait(10)
        competing.set()
        lock_workspace(workspace, operation=operation)

    def worker(function, *args):
        close_old_connections()
        try:
            return function(*args)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(worker, hold),
            pool.submit(worker, probe, Workspace.objects.get(pk=context[3].pk), "same_workspace"),
            pool.submit(worker, probe, Workspace.objects.get(pk=context[4].pk), "other_workspace"),
        ]
        for future in futures:
            future.result(timeout=15)
    rows = [
        {"operation": r.operation, "wait_ms": r.wait_ms, "held_ms": r.held_ms, "outcome": r.outcome}
        for r in caplog.records
        if r.msg == "radar_workspace_lock_finished"
    ]
    same = next(row for row in rows if row["operation"] == "same_workspace")
    other = next(row for row in rows if row["operation"] == "other_workspace")
    assert same["wait_ms"] >= 100 and other["wait_ms"] < same["wait_ms"]
    print("C14_BASELINE=" + json.dumps(rows))


runtime = runtime_tests.runtime


def test_integrated_custom_type_configuration_facts_lifecycle_runtime_and_replay(runtime, client):
    from rest_framework.exceptions import PermissionDenied
    from plane.radar.commands.execution import execute_command, CommandConflict
    from plane.radar.models import Provenance, PropertyDefinition, RuntimeObjectIdentity
    from plane.radar.workspace_schema import schema_revision
    from .test_commands import create, envelope, approved_agent
    from .test_core_u1_phase02 import edit
    from .test_core_u1_phase03bc import ticket_type, TICKET_LIFECYCLE
    from .test_core_u1_phase05a import descriptor, query
    from .test_runtime_contract import bind

    ctx = runtime[0]
    selected = ticket_type(ctx, TICKET_LIFECYCLE)
    edit(
        ctx,
        selected,
        {
            "rules": {
                **selected.rules,
                "creation": {"capability": "CreateObject"},
                "presentation": {
                    "narrative": "summary",
                    "sections": [{"key": "state", "label": "State", "properties": ["status", "closed_at"]}],
                },
            }
        },
    )

    def configure():
        return RelationType.objects.create(
            workspace=ctx[3],
            key="ticket_goal",
            forward_label="goal",
            reverse_label="ticket",
            source_types=["ticket"],
            target_types=["objective"],
            cardinality="1..1",
        )

    relation_type = run_internal(
        actor=ctx[5], workspace=ctx[3], name="ConfigureAcceptanceRelation", operation=configure
    )
    target = create(ctx)
    assert (
        client.post(url(ctx), {"object_type": str(selected.pk), "title": "Missing summary"}, format="json").status_code
        == 400
    )
    response = client.post(
        url(ctx),
        {"object_type": str(selected.pk), "title": "Integrated", "properties": {"summary": "Required narrative"}},
        format="json",
    )
    assert response.status_code == 201, response.data
    obj = Object.objects.get(pk=response.data["id"])
    assert response.data["created_actor"]["actor_type"] == "human"
    capacities = client.get(url(ctx, f"objects/{obj.pk}/capabilities/")).data
    assert capacities["presentation"]["narrative"]["field"] == "summary"
    status_definition = PropertyDefinition.objects.get(object_type=selected, key="status")
    status_url = url(ctx, f"objects/{obj.pk}/properties/{status_definition.pk}/")
    assert client.put(status_url, {"value": "working"}, format="json").status_code == 400
    candidates = client.get(url(ctx), {"relation_type": str(relation_type.pk), "object_id": str(obj.pk)})
    assert str(target.pk) in {row["id"] for row in candidates.data}
    assert (
        client.post(
            url(ctx, "relations/"),
            {"relation_type": str(relation_type.pk), "source": str(obj.pk), "target": str(target.pk)},
            format="json",
        ).status_code
        == 201
    )
    assert client.put(status_url, {"value": "working"}, format="json").status_code == 200
    with pytest.raises(PermissionDenied):
        bind(runtime, obj, "TKT")
    selected.refresh_from_db()
    edit(ctx, selected, {"rules": {**selected.rules, "runtime": descriptor()}})
    bind(runtime, target, "OBJ")
    code = bind(runtime, obj, "TKT")
    assert query(runtime, "read_entity", entity_id=code).data["metadata"]["type"] == "ticket"
    assert RuntimeObjectIdentity.objects.get(object=obj).created_provenance.actor_type == "human"
    obj.refresh_from_db()
    intent = envelope(
        ctx,
        "UpdateObject",
        {"object_id": str(obj.pk), "changes": {"title": "Committed once"}},
        versions={str(obj.pk): obj.version},
    )
    intent["expected_schema_revision"] = schema_revision(ctx[3])
    result = execute_command(actor=ctx[5], workspace=ctx[3], envelope=intent)
    agent = approved_agent(ctx)
    pending_intent = envelope(
        ctx, "UpdateObject", {"object_id": str(obj.pk), "changes": {"title": "Agent proposal"}}, actor=agent
    )
    pending = execute_command(actor=agent, workspace=ctx[3], envelope=pending_intent)
    assert pending["status"] == "pending_approval"
    selected.refresh_from_db()
    edit(ctx, selected, {"name": "Renamed ticket"})
    assert execute_command(actor=ctx[5], workspace=ctx[3], envelope=intent) == result
    with pytest.raises(CommandConflict):
        execute_command(actor=agent, workspace=ctx[3], envelope=pending_intent)
    assert Provenance.objects.filter(command_id=result["command_id"]).count() == 1
    selected.refresh_from_db()
    edit(ctx, selected, {"is_active": False})
    assert client.get(url(ctx), {"object_type": str(selected.pk)}).data == []
    assert client.get(url(ctx, f"objects/{obj.pk}/")).status_code == 404
    assert client.get(url(ctx, f"objects/{obj.pk}/provenance/")).status_code == 200


def test_relation_capacities_are_bounded_and_scoped(context, client):
    from plane.radar.models import Relation

    _, objects = populate(context, 61)
    kind = fixture_write(
        lambda: RelationType.objects.create(
            workspace=context[3],
            key="capacity_page",
            forward_label="links",
            reverse_label="linked",
            source_types=["objective"],
            target_types=["objective"],
            cardinality="0..n",
        )
    )
    edges = fixture_write(
        lambda: [
            Relation.objects.create(
                id=UUID(int=2000 + i), workspace=context[3], relation_type=kind, source=objects[0], target=target
            )
            for i, target in enumerate(objects[1:])
        ]
    )
    endpoint = url(context, f"objects/{objects[0].pk}/capabilities/")
    assert len(client.get(endpoint).data["relations"]) == 50
    page = client.get(endpoint, {"relation_ids": str(edges[-1].pk)}).data["relations"]
    assert list(page) == [str(edges[-1].pk)]
    assert client.get(endpoint, {"relation_ids": str(uuid4())}).data["relations"] == {}
    assert client.get(endpoint, {"relation_ids": "bad"}).status_code == 400
    assert client.get(endpoint, {"relation_ids": ",".join([str(edges[0].pk)] * 101)}).status_code == 400


def test_creation_search_includes_default_capability_for_custom_type(context, client):
    populate(context, 2)

    def configure():
        return ObjectType.objects.create(workspace=context[3], key="custom", name="Custom", rules={})

    kind = run_internal(actor=context[5], workspace=context[3], name="ConfigureSearchType", operation=configure)
    obj = create_object(actor=context[5], workspace=context[3], object_type=kind.pk, title="Custom")
    response = client.get(url(context), {"capability": "CreateObject", "type_keys": "*"})
    assert str(obj.pk) in {row["id"] for row in response.data}
