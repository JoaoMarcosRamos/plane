"""U1 phase 1: actor summaries, public application contracts and exact defaults replay."""

import ast
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from django.db import transaction
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from plane.db.models import WorkspaceMember
from plane.radar.api.serializers import ObjectSerializer, RelationSerializer
from plane.radar.api.semantic_views import property_snapshot
from plane.radar.authorship import AUTHOR_RELATIONS
from plane.radar.commands import create_object, initialize_object_properties, initialize_semantic_model, update_object
from plane.radar.commands.execution import CommandConflict, execute_command
from plane.radar.commands.results import object_data, relation_result, property_snapshot_result
from plane.radar.commands.semantic import initialize_properties_command
from plane.radar.models import (
    Object,
    ObjectType,
    PropertyDefinition,
    PropertyValue,
    CommandExecution,
    DomainEvent,
    Provenance,
    Relation,
    RelationType,
)
from plane.radar.mutation import json_value
from .fixture_writes import fixture_write
from .test_commands import approved_agent, accept, envelope
from .test_core import url

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def seeded(context):
    initialize_semantic_model(actor=context[5], workspace=context[3])
    return context


def create(ctx, actor=None):
    return create_object(
        actor=actor or ctx[5],
        workspace=ctx[3],
        object_type=ObjectType.objects.get(workspace=ctx[3], key="objective").pk,
        title="U1 object",
    )


def snapshot(obj):
    obj = Object.objects.select_related(*AUTHOR_RELATIONS).get(pk=obj.pk)
    return json_value(ObjectSerializer(obj).data)


def counts():
    return tuple(model.objects.count() for model in (Object, PropertyValue, CommandExecution, Provenance, DomainEvent))


@pytest.mark.parametrize("actor_type", ["human", "agent", "system", "integration"])
def test_author_summary_uses_real_actor(seeded, actor_type):
    ctx = seeded
    actor = ctx[5] if actor_type == "human" else approved_agent(ctx, actor_type, requires_approval=False)
    data = {"object_type_id": str(ObjectType.objects.get(workspace=ctx[3], key="objective").pk), "title": "Authored"}
    request = envelope(ctx, "CreateObject", data, actor=actor)
    result = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    if result["status"] == "pending_approval":
        vote = accept(ctx, result)
        result = execute_command(actor=replace(actor, approval_id=vote.pk), workspace=ctx[3], envelope=request)
    obj = Object.objects.get(pk=result["data"]["object"]["id"])
    result = snapshot(obj)
    assert result["created_actor"]["actor_type"] == actor_type
    assert result["created_actor"]["actor_id"] == str(actor.actor_id)
    assert result["created_actor"]["source"] == actor.source
    assert result["created_actor"]["provenance_id"]
    assert result["updated_actor"] == result["created_actor"]
    assert result["created_by"] == (str(actor.actor_id) if actor_type == "human" else None)
    assert result["created_actor"]["user_status"] == ("available" if actor_type == "human" else "not_applicable")


def test_authorship_tracks_editor_without_replacing_creator(seeded):
    obj = create(seeded)
    actor = approved_agent(seeded, "integration", requires_approval=False)
    result = execute_command(
        actor=actor,
        workspace=seeded[3],
        envelope=envelope(
            seeded,
            "UpdateObject",
            {"object_id": str(obj.pk), "changes": {"title": "Edited by integration"}},
            actor=actor,
        ),
    )
    data = snapshot(obj)
    assert data["created_actor"]["actor_id"] == str(seeded[0].pk)
    assert data["updated_actor"]["actor_id"] == str(actor.actor_id)
    assert data["updated_actor"]["actor_type"] == "integration"
    assert data["updated_actor"]["provenance_id"] == result["provenance_id"]
    assert data["created_by"] == str(seeded[0].pk) and data["updated_by"] is None


def test_deleted_human_and_missing_provenance_have_distinct_fallbacks(seeded):
    # Historical fixture: a validated human identity whose User no longer exists.
    actor_id = uuid4()
    record = Provenance.objects.create(
        workspace=seeded[3],
        command_id=uuid4(),
        command_name="CreateObject",
        actor_type="human",
        actor_id=actor_id,
        reason="Historical creation",
        source="historical.session-api",
        correlation_id=uuid4(),
        outcome="executed",
    )
    kind = ObjectType.objects.get(workspace=seeded[3], key="objective")
    obj = fixture_write(
        lambda: Object.objects.create(
            workspace=seeded[3],
            object_type=kind,
            title="Deleted human author",
            created_provenance=record,
            last_provenance=record,
        )
    )
    data = snapshot(obj)
    assert data["created_by"] is None
    assert data["created_actor"]["actor_type"] == "human"
    assert data["created_actor"]["actor_id"] == str(actor_id)
    assert data["created_actor"]["user_status"] == "deleted"
    legacy = fixture_write(
        lambda: Object.objects.create(
            workspace=seeded[3], object_type=obj.object_type, title="Unknown legacy", created_by_id=None
        )
    )
    assert snapshot(legacy)["created_actor"]["actor_type"] == "unknown"
    assert snapshot(legacy)["created_actor"]["actor_id"] is None
    assert snapshot(legacy)["created_actor"]["provenance_id"] is None


def test_legacy_human_without_provenance_is_resolved(seeded):
    kind = ObjectType.objects.get(workspace=seeded[3], key="objective")
    obj = fixture_write(
        lambda: Object.objects.create(workspace=seeded[3], object_type=kind, title="Legacy", created_by_id=seeded[0].pk)
    )
    author = snapshot(obj)["created_actor"]
    assert author["actor_type"] == "human" and author["user_status"] == "available"
    assert author["provenance_id"] is None and author["source"] is None


def test_author_list_resolves_humans_in_a_constant_query_budget(seeded):
    for actor in [seeded[5], replace(seeded[5], actor_id=seeded[1].pk)]:
        for _ in range(3):
            create(seeded, actor)
    with CaptureQueriesContext(connection) as queries:
        data = ObjectSerializer(Object.objects.filter(workspace=seeded[3]), many=True).data
    assert len(data) == 6
    assert len(queries) == 2  # Objects/type/provenance join, then all human names.


def test_application_results_preserve_v1_object_relation_and_property_representation(seeded):
    obj, target = create(seeded), create(seeded)
    object_payload = dict(snapshot(obj))
    object_payload.pop("created_actor")
    object_payload.pop("updated_actor")
    assert object_data(obj) == object_payload
    kind = fixture_write(
        lambda: RelationType.objects.create(
            workspace=seeded[3],
            key="u1_relation",
            forward_label="links",
            reverse_label="linked by",
            source_types=["objective"],
            target_types=["objective"],
            cardinality="0..n",
        )
    )
    edge = fixture_write(
        lambda: Relation.objects.create(workspace=seeded[3], relation_type=kind, source=obj, target=target)
    )
    assert relation_result(edge) == json_value(dict(RelationSerializer(edge).data))
    with transaction.atomic():
        http = json_value(property_snapshot(seeded[3], obj.pk))
    http["object"].pop("created_actor")
    http["object"].pop("updated_actor")
    assert property_snapshot_result(obj) == http


def add_default(ctx, obj, key="u1_default", value="seeded"):
    return fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=ctx[3],
            object_type=obj.object_type,
            key=key,
            name=key,
            value_type="string",
            config={"default": value},
        )
    )


def test_defaults_replay_precedes_stale_version_check_and_preserves_historical_snapshot(seeded):
    obj = create(seeded)
    definition = add_default(seeded, obj)
    kwargs = dict(
        actor=seeded[5],
        workspace=seeded[3],
        object_id=obj.pk,
        expected_versions={str(obj.pk): obj.version},
        idempotency_key="defaults-once",
    )
    result = initialize_properties_command(**kwargs)
    before = counts()
    assert result["status"] == "executed" and result["data"]["object"]["version"] == 2
    assert result["data"]["object"]["updated_actor"]["provenance_id"] == result["provenance_id"]
    assert initialize_properties_command(**kwargs) == result and counts() == before
    update_object(actor=seeded[5], workspace=seeded[3], object_id=obj.pk, changes={"title": "Later"})
    changed = counts()
    assert initialize_properties_command(**kwargs) == result and counts() == changed
    assert PropertyValue.objects.get(object=obj, definition=definition).value == "seeded"
    assert result["data"]["object"]["title"] == "U1 object"


def test_defaults_http_replays_confirmed_snapshot_after_lost_response(seeded):
    obj = create(seeded)
    add_default(seeded, obj)
    client = APIClient()
    client.force_authenticate(seeded[0])
    headers = {"HTTP_IDEMPOTENCY_KEY": "http-defaults", "HTTP_X_RADAR_EXPECTED_VERSIONS": '{"%s":1}' % obj.pk}
    path = url(seeded, f"objects/{obj.pk}/properties/")
    first = client.post(path, {}, format="json", **headers)
    assert first.status_code == 200 and first.data["object"]["version"] == 2
    update_object(actor=seeded[5], workspace=seeded[3], object_id=obj.pk, changes={"title": "Later"})
    before = counts()
    replay = client.post(path, {}, format="json", **headers)
    assert replay.status_code == 200 and replay.data == first.data and counts() == before


def test_trusted_defaults_caller_reuses_saved_versions_when_only_key_is_supplied(seeded):
    obj = create(seeded)
    add_default(seeded, obj)
    kwargs = dict(actor=seeded[5], workspace=seeded[3], object_id=obj.pk, idempotency_key="trusted-defaults")
    first = initialize_object_properties(**kwargs)
    assert first.version == 2
    before = counts()
    assert initialize_object_properties(**kwargs).pk == first.pk and counts() == before


def test_defaults_key_conflict_noop_and_authority_revocation(seeded):
    obj, other = create(seeded), create(seeded)
    kwargs = dict(
        actor=seeded[5],
        workspace=seeded[3],
        expected_versions={str(obj.pk): obj.version},
        idempotency_key="defaults-noop",
        object_id=obj.pk,
    )
    result = initialize_properties_command(**kwargs)
    assert result["status"] == "noop"
    before = counts()
    assert initialize_properties_command(**kwargs) == result and counts() == before
    with pytest.raises(CommandConflict):
        initialize_properties_command(**{**kwargs, "object_id": other.pk, "expected_versions": {str(other.pk): 1}})
    WorkspaceMember.objects.filter(workspace=seeded[3], member=seeded[0]).update(is_active=False)
    with pytest.raises(PermissionDenied):
        initialize_properties_command(**kwargs)
    assert counts() == before


@pytest.mark.parametrize("actor_type", ["agent", "system", "integration"])
def test_defaults_command_remains_human_only_even_with_forged_grant(seeded, actor_type):
    from plane.radar.models import ActorGrant

    obj = create(seeded)
    actor = approved_agent(seeded, actor_type, requires_approval=False)
    fixture_write(
        lambda: ActorGrant.objects.filter(actor_id=actor.actor_id).update(commands=["InitializeObjectProperties"])
    )
    before = counts()
    with pytest.raises(PermissionDenied):
        initialize_properties_command(
            actor=actor,
            workspace=seeded[3],
            object_id=obj.pk,
            expected_versions={str(obj.pk): 1},
            idempotency_key="human-only",
        )
    assert counts() == before


def test_invalid_defaults_roll_back_ledger_properties_and_provenance(seeded):
    from rest_framework.exceptions import ValidationError

    obj = create(seeded)
    add_default(seeded, obj)
    fixture_write(
        lambda: PropertyDefinition.objects.create(
            workspace=seeded[3],
            object_type=obj.object_type,
            key="z_invalid",
            name="Invalid default",
            value_type="integer",
            config={"default": "invalid"},
        )
    )
    before = counts()
    with pytest.raises(ValidationError):
        initialize_properties_command(
            actor=seeded[5],
            workspace=seeded[3],
            object_id=obj.pk,
            expected_versions={str(obj.pk): 1},
            idempotency_key="invalid-defaults",
        )
    obj.refresh_from_db()
    assert obj.version == 1 and counts() == before


def test_command_modules_do_not_depend_on_api_serializers_or_private_cross_module_interfaces():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(item.name.startswith("_") for item in node.names), (path, node.lineno)
                if path.parent.name == "commands":
                    assert not (node.module or "").startswith("plane.radar.api"), (path, node.lineno)
