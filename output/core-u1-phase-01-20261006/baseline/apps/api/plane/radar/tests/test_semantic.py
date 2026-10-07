from dataclasses import replace
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from plane.db.models import WorkspaceMember
from plane.radar.commands import (
    initialize_semantic_model,
    initialize_object_properties,
    create_object,
    update_object,
    set_property_value,
    remove_property_value,
    create_relation,
    remove_relation,
)
from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, RelationType, Relation
from plane.radar.ontology.schema import load_schema
from .test_core import url
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def semantic(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def obj(ctx, key="objective", title="Semantic Object"):
    properties = {"description": "Executable work or uncertain event"} if key in {"action", "risk"} else {}
    if key == "decision":
        properties = {"context": "Governance", "decision": "A proposed choice", "rationale": "Reviewable reasons"}
    return create_object(
        actor=ctx[5],
        workspace=ctx[3],
        object_type=ObjectType.objects.get(workspace=ctx[3], key=key).pk,
        title=title,
        properties=properties,
    )


def definition(ctx, key="status", type_key="objective"):
    return PropertyDefinition.objects.get(workspace=ctx[3], object_type__key=type_key, key=key)


def set_value(ctx, result, selected, value, actor=None):
    return set_property_value(
        actor=actor or ctx[5], workspace=ctx[3], object_id=result.pk, definition_id=selected.pk, value=value
    )


def link(ctx, source, target, key="advances", actor=None):
    return create_relation(
        actor=actor or ctx[5],
        workspace=ctx[3],
        source_id=source.pk,
        target_id=target.pk,
        relation_type_id=RelationType.objects.get(workspace=ctx[3], key=key).pk,
    )


def test_normative_seed_idempotent_and_minimal(semantic):
    ctx = semantic
    before = list(PropertyDefinition.objects.values_list("id", "config", "updated_at"))
    initialize_semantic_model(actor=replace(ctx[5], actor_id=ctx[1].pk), workspace=ctx[3])
    assert list(PropertyDefinition.objects.values_list("id", "config", "updated_at")) == before
    schema = load_schema()
    assert set(ObjectType.objects.values_list("key", flat=True)) == set(schema["object_types"])
    assert set(RelationType.objects.values_list("key", flat=True)) == set(schema["link_types"])
    assert not RelationType.objects.filter(key__in=["supports", "affects"]).exists()
    assert definition(ctx).config["choices"] == schema["vocabularies"]["objective_status"]
    assert RelationType.objects.get(key="creates").allowed_pairs == [
        ["decision", "action"],
        ["management_item", "risk"],
    ]
    assert not PropertyDefinition.objects.filter(workspace=ctx[4]).exists()
    assert all(item.created_by_id == ctx[0].pk for item in PropertyDefinition.objects.all())


def test_defaults_and_legacy_materialization(semantic):
    ctx = semantic
    result = obj(ctx)
    assert PropertyValue.objects.get(object=result, definition=definition(ctx)).value == "draft"
    assert result.version == 1
    legacy = fixture_write(
        lambda: Object.objects.create(
            workspace=ctx[3], object_type=result.object_type, title="Legacy", created_by=ctx[0], updated_by=ctx[0]
        )
    )
    initialize_object_properties(actor=replace(ctx[5], actor_id=ctx[1].pk), workspace=ctx[3], object_id=legacy.pk)
    legacy.refresh_from_db()
    assert legacy.version == 2 and legacy.created_by_id == ctx[0].pk and legacy.updated_by_id == ctx[1].pk
    initialize_object_properties(actor=ctx[5], workspace=ctx[3], object_id=legacy.pk)
    legacy.refresh_from_db()
    assert legacy.version == 2


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", "Text"),
        ("string_list", ["a", "b"]),
        ("number", 2.5),
        ("integer", 2),
        ("boolean", False),
        ("enum", "active"),
        ("date", "2026-10-03"),
        ("datetime", "2026-10-03T12:00:00Z"),
        ("email", "person@example.com"),
        ("uri", "https://example.com/evidence"),
    ],
)
def test_supported_values(semantic, kind, value):
    ctx = semantic
    result = obj(ctx)
    selected = fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3],
            object_type=result.object_type,
            key="custom",
            name="Custom",
            value_type=kind,
            config={"choices": ["active"]},
        )
    )
    saved = set_value(ctx, result, selected, value)
    assert saved.value == value
    assert saved.created_by_id == ctx[0].pk
    result.refresh_from_db()
    assert result.version == 2
    set_value(ctx, result, selected, value, actor=replace(ctx[5], actor_id=ctx[1].pk))
    result.refresh_from_db()
    assert result.version == 2  # No-op retries preserve provenance and versions.


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", 1),
        ("string_list", [1]),
        ("integer", True),
        ("integer", 1.5),
        ("number", True),
        ("number", float("inf")),
        ("number", float("nan")),
        ("boolean", "false"),
        ("enum", "invented"),
        ("date", "2026-02-30"),
        ("date", "20261003"),
        ("datetime", "2026-10-03T12:00:00"),
        ("email", "invalid"),
        ("uri", "javascript:alert(1)"),
        ("user", "invalid"),
        ("string", None),
    ],
)
def test_invalid_values_atomic(semantic, kind, value):
    ctx = semantic
    result = obj(ctx)
    selected = fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3],
            object_type=result.object_type,
            key="custom",
            name="Custom",
            value_type=kind,
            config={"choices": ["active"]},
        )
    )
    with pytest.raises(ValidationError):
        set_value(ctx, result, selected, value)
    result.refresh_from_db()
    assert result.version == 1
    assert not PropertyValue.objects.filter(object=result, definition=selected).exists()


@pytest.mark.parametrize("key,value", [("progress", -1), ("progress", 101)])
def test_numeric_bounds(semantic, key, value):
    with pytest.raises(ValidationError):
        set_value(semantic, obj(semantic), definition(semantic, key), value)


def test_user_reference_membership_and_type_validation(semantic):
    ctx = semantic
    result = obj(ctx)
    selected = fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3], object_type=result.object_type, key="reviewer", name="Reviewer", value_type="user"
        )
    )
    assert set_value(ctx, result, selected, str(ctx[1].pk)).value == str(ctx[1].pk)
    with pytest.raises(ValidationError):
        set_value(ctx, result, selected, str(ctx[2].pk))
    with pytest.raises(ValidationError):
        set_value(ctx, result, definition(ctx, "status", "action"), "todo")


def test_property_soft_delete_audit_recreate_and_protected_defaults(semantic):
    ctx = semantic
    result = obj(ctx)
    selected = definition(ctx, "due_date")
    saved = set_value(ctx, result, selected, "2026-10-03")
    remove_property_value(
        actor=replace(ctx[5], actor_id=ctx[1].pk), workspace=ctx[3], object_id=result.pk, definition_id=selected.pk
    )
    tombstone = PropertyValue.all_objects.get(pk=saved.pk)
    assert tombstone.deleted_at and tombstone.created_by_id == ctx[0].pk and tombstone.updated_by_id == ctx[1].pk
    assert not PropertyValue.objects.filter(pk=saved.pk).exists()
    recreated = set_value(ctx, result, selected, "2026-10-04")
    assert recreated.pk != saved.pk
    with pytest.raises(ValidationError):
        remove_property_value(actor=ctx[5], workspace=ctx[3], object_id=result.pk, definition_id=definition(ctx).pk)
    for operation in [saved.delete, PropertyValue.all_objects.all().delete]:
        with pytest.raises(NotImplementedError):
            operation()


def test_relation_direction_audit_duplicate_soft_delete_recreate(semantic):
    ctx = semantic
    source, target = obj(ctx, "project"), obj(ctx)
    saved = link(ctx, source, target)
    source.refresh_from_db()
    target.refresh_from_db()
    assert source.version == target.version == 2
    assert list(source.outgoing_relations.all()) == list(target.incoming_relations.all()) == [saved]
    again = link(ctx, source, target, actor=replace(ctx[5], actor_id=ctx[1].pk))
    source.refresh_from_db()
    assert again.pk == saved.pk and source.version == 2 and again.updated_by_id == ctx[0].pk
    remove_relation(actor=replace(ctx[5], actor_id=ctx[1].pk), workspace=ctx[3], relation_id=saved.pk)
    source.refresh_from_db()
    target.refresh_from_db()
    assert source.version == target.version == 3
    tombstone = Relation.all_objects.get(pk=saved.pk)
    assert tombstone.deleted_at and tombstone.updated_by_id == ctx[1].pk and tombstone.created_by_id == ctx[0].pk
    assert link(ctx, source, target).pk != saved.pk
    for operation in [saved.delete, Relation.all_objects.all().delete]:
        with pytest.raises(NotImplementedError):
            operation()


def test_relation_cardinality_and_normative_pairs(semantic):
    ctx = semantic
    action, person, second_person = obj(ctx, "action"), obj(ctx, "person"), obj(ctx, "person")
    link(ctx, action, person, "owned_by")
    with pytest.raises(ValidationError):
        link(ctx, action, second_person, "owned_by")
    decision, risk = obj(ctx, "decision"), obj(ctx, "risk")
    with pytest.raises(ValidationError):
        link(ctx, decision, risk, "creates")
    with pytest.raises(ValidationError, match="decided"):
        link(ctx, decision, action, "creates")
    with pytest.raises(ValidationError):
        link(ctx, action, decision, "creates")
    with pytest.raises(ValidationError):
        link(ctx, person, person, "reports_to")
    person.refresh_from_db()
    version = person.version
    assert link(ctx, person, person, "relates_to")
    person.refresh_from_db()
    assert person.version == version + 1


@pytest.mark.parametrize("resource", ["object", "type", "definition", "relation_type"])
@pytest.mark.parametrize("state", ["deleted", "inactive"])
def test_inactive_deleted_resources_rejected(semantic, resource, state):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    selected = definition(ctx, "status", "action")
    kind = RelationType.objects.get(key="advances")
    item = {"object": source, "type": source.object_type, "definition": selected, "relation_type": kind}[resource]
    if resource == "object" and state == "inactive":
        return  # Objects have no is_active; lifecycle is a property.
    fields = {"deleted_at": timezone.now()} if state == "deleted" else {"is_active": False}
    fixture_write(lambda: item.__class__.all_objects.filter(pk=item.pk).update(**fields))
    with pytest.raises((ValidationError, NotFound)):
        if resource == "relation_type":
            create_relation(
                actor=ctx[5], workspace=ctx[3], source_id=source.pk, target_id=target.pk, relation_type_id=kind.pk
            )
        else:
            set_value(ctx, source, selected, "todo")


def test_cross_workspace_schema_and_endpoints_rejected(semantic):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    WorkspaceMember.objects.create(workspace=ctx[4], member=ctx[0], role=15)
    initialize_semantic_model(actor=ctx[5], workspace=ctx[4])
    foreign_type = ObjectType.objects.get(workspace=ctx[4], key="objective")
    foreign = create_object(actor=ctx[5], workspace=ctx[4], object_type=foreign_type.pk, title="Foreign")
    foreign_def = PropertyDefinition.objects.get(workspace=ctx[4], object_type__key="action", key="status")
    with pytest.raises(ValidationError):
        set_value(ctx, source, foreign_def, "todo")
    with pytest.raises(NotFound):
        link(ctx, source, foreign)
    with pytest.raises(ValidationError):
        create_relation(
            actor=ctx[5],
            workspace=ctx[3],
            source_id=source.pk,
            target_id=target.pk,
            relation_type_id=RelationType.objects.get(workspace=ctx[4], key="advances").pk,
        )


@pytest.mark.parametrize("actor_type", ["agent", "system", "integration", "nonmember", "guest"])
def test_all_semantic_commands_authorize(semantic, actor_type):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    saved = link(ctx, source, target)
    actor = ctx[5]
    if actor_type == "nonmember":
        actor = replace(actor, actor_id=ctx[2].pk)
    elif actor_type == "guest":
        WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=5)
    else:
        actor = replace(actor, actor_type=actor_type)
    operations = [
        lambda: set_value(ctx, source, definition(ctx, "status", "action"), "done", actor),
        lambda: remove_property_value(
            actor=actor, workspace=ctx[3], object_id=source.pk, definition_id=definition(ctx, "due_date", "action").pk
        ),
        lambda: link(ctx, source, target, actor=actor),
        lambda: remove_relation(actor=actor, workspace=ctx[3], relation_id=saved.pk),
        lambda: initialize_object_properties(actor=actor, workspace=ctx[3], object_id=source.pk),
    ]
    for operation in operations:
        with pytest.raises(PermissionDenied):
            operation()


@pytest.mark.parametrize("operation", ["value", "relation", "remove_value", "remove_relation", "defaults"])
def test_semantic_writes_rollback_on_version_failure(semantic, operation):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    selected = definition(ctx, "due_date", "action")
    saved_value = set_value(ctx, source, selected, "2026-10-03")
    saved_link = link(ctx, source, target)
    legacy = fixture_write(
        lambda: Object.objects.create(workspace=ctx[3], object_type=target.object_type, title="Legacy")
    )
    operations = {
        "value": lambda: set_value(ctx, source, selected, "2026-10-04"),
        "relation": lambda: link(ctx, source, target, "relates_to"),
        "remove_value": lambda: remove_property_value(
            actor=ctx[5], workspace=ctx[3], object_id=source.pk, definition_id=selected.pk
        ),
        "remove_relation": lambda: remove_relation(actor=ctx[5], workspace=ctx[3], relation_id=saved_link.pk),
        "defaults": lambda: initialize_object_properties(actor=ctx[5], workspace=ctx[3], object_id=legacy.pk),
    }
    before = list(Object.objects.values_list("id", "version"))
    with (
        patch.object(Object, "save", side_effect=IntegrityError("version write failed")),
        pytest.raises(IntegrityError),
    ):
        operations[operation]()
    assert list(Object.objects.values_list("id", "version")) == before
    saved_value.refresh_from_db()
    saved_link.refresh_from_db()
    assert saved_value.value == "2026-10-03" and saved_value.deleted_at is None and saved_link.deleted_at is None
    assert Relation.objects.count() == 1
    assert not PropertyValue.objects.filter(object=legacy).exists()


def test_database_constraints(semantic):
    ctx = semantic
    result = obj(ctx)
    selected = definition(ctx)
    with pytest.raises(IntegrityError), transaction.atomic():
        fixture_write(
            lambda: PropertyValue.objects.create(workspace=ctx[3], object=result, definition=selected, value="active")
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        fixture_write(
            lambda: PropertyDefinition.objects.create(
                workspace=ctx[3], object_type=result.object_type, key="status", name="Dup"
            )
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        fixture_write(
            lambda: RelationType.objects.create(
                workspace=ctx[3], key="custom", forward_label="x", reverse_label="y", cardinality="2..5"
            )
        )
    source = obj(ctx, "action")
    edge = link(ctx, source, result)
    with pytest.raises(IntegrityError), transaction.atomic():
        fixture_write(
            lambda: Relation.objects.create(
                workspace=ctx[3], relation_type=edge.relation_type, source=source, target=result
            )
        )


def test_type_change_guard(semantic):
    ctx = semantic
    result = obj(ctx)
    with pytest.raises(ValidationError):
        update_object(
            actor=ctx[5],
            workspace=ctx[3],
            object_id=result.pk,
            changes={"object_type": ObjectType.objects.get(key="action").pk},
        )
    result.refresh_from_db()
    assert result.object_type.key == "objective" and result.version == 1


def test_api_semantic_flow_and_reverse_lookup(client, semantic):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    definitions = client.get(url(ctx, f"property-definitions/?object_type={source.object_type_id}"))
    assert definitions.status_code == 200 and all(
        item["object_type"] == source.object_type_id for item in definitions.data
    )
    selected = definition(ctx, "due_date", "action")
    properties_url = url(ctx, f"objects/{source.pk}/properties/")
    assert client.get(properties_url).status_code == 200
    response = client.put(properties_url + f"{selected.pk}/", {"value": "2026-10-03"}, format="json")
    assert response.status_code == 200 and response.data["object"]["version"] == 2
    assert client.delete(properties_url + f"{selected.pk}/").data["object"]["version"] == 3
    kind = next(item for item in client.get(url(ctx, "relation-types/")).data if item["key"] == "advances")
    response = client.post(
        url(ctx, "relations/"),
        {"relation_type": str(kind["id"]), "source": str(source.pk), "target": str(target.pk)},
        format="json",
    )
    assert response.status_code == 201
    edge = response.data["relation"]
    forward = client.get(url(ctx, f"objects/{source.pk}/relations/?direction=outgoing"))
    reverse = client.get(url(ctx, f"objects/{target.pk}/relations/?direction=incoming"))
    assert forward.data["relations"][0]["id"] == reverse.data["relations"][0]["id"] == edge["id"]
    assert reverse.data["relations"][0]["relation_type_detail"]["reverse_label"] == "advanced_by"
    assert client.get(url(ctx, f"objects/{source.pk}/relations/?direction=invalid")).status_code == 400
    assert client.delete(url(ctx, f"relations/{edge['id']}/")).status_code == 200
    assert client.get(url(ctx, f"objects/{target.pk}/relations/")).data["relations"] == []


def test_api_legacy_defaults_get_is_read_only(client, semantic):
    ctx = semantic
    legacy = fixture_write(
        lambda: Object.objects.create(
            workspace=ctx[3], object_type=ObjectType.objects.get(key="objective"), title="Legacy"
        )
    )
    endpoint = url(ctx, f"objects/{legacy.pk}/properties/")
    response = client.get(endpoint)
    status_row = next(row for row in response.data["properties"] if row["definition"]["key"] == "status")
    assert status_row["stored_value"] is None and status_row["value"] == "draft" and status_row["has_value"]
    assert not PropertyValue.objects.filter(object=legacy).exists()
    assert client.post(endpoint, {}, format="json").data["object"]["version"] == 2
    assert client.post(endpoint, {}, format="json").data["object"]["version"] == 2


@pytest.mark.parametrize("access", ["anonymous", "nonmember", "guest"])
def test_api_access_matrix(client, semantic, access):
    ctx = semantic
    source, target = obj(ctx, "action"), obj(ctx)
    saved = link(ctx, source, target)
    if access == "guest":
        WorkspaceMember.objects.filter(workspace=ctx[3], member=ctx[0]).update(role=5)
    else:
        client.force_authenticate(user=None if access == "anonymous" else ctx[2])
    denied_status = 401 if access == "anonymous" else 403
    endpoints = [
        "property-definitions/",
        "relation-types/",
        f"objects/{source.pk}/properties/",
        f"objects/{source.pk}/relations/",
    ]
    for endpoint in endpoints:
        assert client.get(url(ctx, endpoint)).status_code == (200 if access == "guest" else denied_status)
    selected = definition(ctx, "due_date", "action")
    assert (
        client.put(
            url(ctx, f"objects/{source.pk}/properties/{selected.pk}/"), {"value": "2026-10-03"}, format="json"
        ).status_code
        == denied_status
    )
    assert client.delete(url(ctx, f"objects/{source.pk}/properties/{selected.pk}/")).status_code == denied_status
    assert client.post(url(ctx, f"objects/{source.pk}/properties/"), {}, format="json").status_code == denied_status
    assert (
        client.post(
            url(ctx, "relations/"),
            {"relation_type": str(saved.relation_type_id), "source": str(source.pk), "target": str(target.pk)},
            format="json",
        ).status_code
        == denied_status
    )
    assert client.delete(url(ctx, f"relations/{saved.pk}/")).status_code == denied_status


def test_api_rejects_invalid_and_forged_payloads(client, semantic):
    ctx = semantic
    source = obj(ctx, "action")
    endpoint = url(ctx, f"objects/{source.pk}/properties/{definition(ctx, 'status', 'action').pk}/")
    for payload in [{"value": "invented"}, {"value": "done", "updated_by": str(ctx[1].pk)}, {"value": None}]:
        assert client.put(endpoint, payload, format="json").status_code == 400
    assert client.get(url(ctx, "property-definitions/?object_type=invalid")).status_code == 400
    source.refresh_from_db()
    assert source.version == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("case", ["cardinality", "duplicate", "properties", "seed"])
def test_real_concurrency(context, case):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections
    from plane.db.models import Workspace

    ctx = context
    if case != "seed":
        initialize_semantic_model(actor=ctx[5], workspace=ctx[3])
        source, first, second = obj(ctx, "action"), obj(ctx, "person"), obj(ctx, "person")
    barrier = Barrier(2)

    def run(index):
        close_old_connections()
        try:
            workspace = Workspace.objects.get(pk=ctx[3].pk)
            barrier.wait(timeout=10)
            if case == "seed":
                initialize_semantic_model(actor=ctx[5], workspace=workspace)
                return PropertyDefinition.objects.count()
            if case == "properties":
                return set_property_value(
                    actor=ctx[5],
                    workspace=workspace,
                    object_id=source.pk,
                    definition_id=definition(ctx, "due_date", "action").pk,
                    value=f"2026-10-0{index + 3}",
                ).value
            return create_relation(
                actor=ctx[5],
                workspace=workspace,
                source_id=source.pk,
                target_id=first.pk if case == "duplicate" or index == 0 else second.pk,
                relation_type_id=RelationType.objects.get(key="owned_by").pk,
            ).pk
        except ValidationError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [0, 1]))
    if case != "seed":
        source.refresh_from_db()
    if case == "cardinality":
        assert results.count("rejected") == 1 and Relation.objects.count() == 1 and source.version == 2
    elif case == "duplicate":
        assert results[0] == results[1] and Relation.objects.count() == 1 and source.version == 2
    elif case == "properties":
        assert (
            source.version == 3 and PropertyValue.objects.filter(object=source, definition__key="due_date").count() == 1
        )
    else:
        assert results[0] == results[1]


def test_normative_ordered_dates_in_both_edit_directions(semantic):
    ctx = semantic
    result = obj(ctx)
    set_value(ctx, result, definition(ctx, "start_date"), "2026-10-03")
    with pytest.raises(ValidationError):
        set_value(ctx, result, definition(ctx, "due_date"), "2026-10-02")
    set_value(ctx, result, definition(ctx, "due_date"), "2026-10-04")
    with pytest.raises(ValidationError):
        set_value(ctx, result, definition(ctx, "start_date"), "2026-10-05")
    result.refresh_from_db()
    assert result.version == 3


def test_normative_risk_score_derived_atomically(semantic):
    ctx = semantic
    result = obj(ctx, "risk")
    actor = replace(ctx[5], actor_id=ctx[1].pk)
    set_value(ctx, result, definition(ctx, "likelihood", "risk"), 5, actor)
    score = PropertyValue.objects.get(object=result, definition__key="score")
    assert score.value == 15 and score.created_by_id == ctx[0].pk and score.updated_by_id == ctx[1].pk
    with pytest.raises(ValidationError):
        set_value(ctx, result, definition(ctx, "score", "risk"), 9)
    set_value(ctx, result, definition(ctx, "impact", "risk"), 4)
    score.refresh_from_db()
    result.refresh_from_db()
    assert score.value == 20 and result.version == 3


def test_property_update_preserves_creator_and_rejects_cross_object_reads(client, semantic):
    ctx = semantic
    result = obj(ctx)
    saved = set_value(ctx, result, definition(ctx), "active", actor=replace(ctx[5], actor_id=ctx[1].pk))
    saved.refresh_from_db()
    assert saved.created_by_id == ctx[0].pk and saved.updated_by_id == ctx[1].pk
    WorkspaceMember.objects.create(workspace=ctx[4], member=ctx[0], role=15)
    for suffix in [f"objects/{result.pk}/properties/", f"objects/{result.pk}/relations/"]:
        foreign = f"/api/workspaces/{ctx[4].slug}/radar/{suffix}"
        assert client.get(foreign).status_code == 404
    endpoint = f"/api/workspaces/{ctx[4].slug}/radar/objects/{result.pk}/properties/{definition(ctx).pk}/"
    assert client.put(endpoint, {"value": "achieved"}, format="json").status_code == 404


def test_api_uses_real_session_cookie(semantic):
    from .conftest import SnapshotClient

    ctx = semantic
    result = obj(ctx)
    api = SnapshotClient()
    api.force_login(ctx[0])
    assert api.get(url(ctx, f"objects/{result.pk}/properties/")).status_code == 200
    assert (
        api.put(
            url(ctx, f"objects/{result.pk}/properties/{definition(ctx).pk}/"), {"value": "active"}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.django_db(transaction=True)
def test_reverse_concurrent_links_share_deterministic_locks(semantic):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections
    from plane.db.models import Workspace

    ctx = semantic
    first, second = obj(ctx, "person"), obj(ctx, "person")
    kind = RelationType.objects.get(key="relates_to")
    barrier = Barrier(2)

    def write(pair):
        close_old_connections()
        try:
            workspace = Workspace.objects.get(pk=ctx[3].pk)
            barrier.wait(timeout=10)
            return create_relation(
                actor=ctx[5], workspace=workspace, relation_type_id=kind.pk, source_id=pair[0], target_id=pair[1]
            ).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [(first.pk, second.pk), (second.pk, first.pk)]))
    first.refresh_from_db()
    second.refresh_from_db()
    assert len(set(results)) == 2 and first.version == second.version == 3


@pytest.mark.parametrize("payload", [[{"value": "active"}], [], 123, "active"])
def test_api_non_object_payload_rejected(client, semantic, payload):
    ctx = semantic
    result = obj(ctx)
    endpoint = url(ctx, f"objects/{result.pk}/properties/{definition(ctx).pk}/")
    assert client.put(endpoint, payload, format="json").status_code == 400
    result.refresh_from_db()
    assert result.version == 1


def test_required_definition_without_default_blocks_incomplete_create(semantic):
    ctx = semantic
    selected = ObjectType.objects.get(key="objective")
    fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3],
            object_type=selected,
            key="required",
            name="Required",
            value_type="string",
            is_required=True,
        )
    )
    with pytest.raises(ValidationError):
        obj(ctx)
    assert not Object.objects.exists()
    assert not PropertyValue.objects.exists()
