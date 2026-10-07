"""C19: explicit workspace opt-in, immutable identities and common runtime scope."""

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command
from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.agent_runtime import binding_for, load_context
from plane.radar.commands import create_object
from plane.radar.commands.execution import CommandConflict, execute_command
from plane.radar.commands.rules import validate_type_rules
from plane.radar.commands.runtime_control import bind_runtime_object, issue_runtime_credential
from plane.radar.models import (
    ActorGrant,
    Object,
    ObjectType,
    Provenance,
    RelationType,
    RuntimeObjectIdentity,
    WorkspaceSchemaState,
)
from plane.radar.ontology.package import package_definitions
from plane.radar.ontology.schema import load_schema
from plane.radar.runtime_identity import runtime_identities
from plane.radar.workspace_schema import SchemaConflict, schema_revision
from .fixture_writes import fixture_write
from .test_commands import envelope
from .test_core import url
from .test_core_u1_phase02 import edit, upgrade
from .test_runtime_contract import bind, endpoint, prepare, resolve
from . import test_runtime_contract as runtime_tests

runtime = runtime_tests.runtime

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def descriptor(prefix="TKT", contexts=None):
    return {
        "enabled": True,
        "identity": {"strategy": "dated_token_v1", "prefix": prefix},
        "contexts": ["company", "manager"] if contexts is None else contexts,
    }


def ticket(state, *, enabled=False):
    ctx = state[0]
    candidate = package_definitions()
    candidate["types:ticket"] = {
        "name": "Ticket",
        "description": "Workspace only",
        "icon": "",
        "is_active": True,
        "rules": {"runtime": descriptor()} if enabled else {},
    }
    upgrade(ctx, candidate)
    kind = ObjectType.objects.get(workspace=ctx[3], key="ticket")
    obj = create_object(actor=ctx[5], workspace=ctx[3], object_type=kind.pk, title="Workspace ticket")
    return kind, obj


def change(ctx, kind, runtime_descriptor):
    kind.refresh_from_db()
    return edit(ctx, kind, {"rules": {**kind.rules, "runtime": runtime_descriptor}})


def query(state, method, **parameters):
    return state[1].post(endpoint(state, "query"), {"method": method, "parameters": parameters}, format="json")


def counts():
    return (Object.objects.count(), RuntimeObjectIdentity.objects.count(), Provenance.objects.count())


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        {"enabled": "true"},
        {"enabled": 1},
        {"enabled": False, "identity": {}},
        {"enabled": True},
        {**descriptor(), "script": "anything"},
        {**descriptor(), "identity": {"strategy": "python", "prefix": "TKT"}},
        {**descriptor(), "identity": {"strategy": "dated_token_v1", "prefix": "TKT", "pattern": ".*"}},
        descriptor(".*"),
        descriptor("tkt"),
        descriptor("X"),
        descriptor("A" * 17),
        descriptor(contexts=[]),
        descriptor(contexts=["company", "company"]),
        descriptor(contexts=["other"]),
        descriptor(contexts=[{}]),
    ],
)
def test_invalid_runtime_metadata_is_rejected_before_persisting(runtime, invalid):
    ctx = runtime[0]
    kind = ObjectType.objects.get(workspace=ctx[3], key="action")
    before, revision = deepcopy(kind.rules), schema_revision(ctx[3])
    with pytest.raises(ValidationError):
        change(ctx, kind, invalid)
    kind.refresh_from_db()
    assert kind.rules == before and schema_revision(ctx[3]) == revision


def test_defaults_do_not_create_runtime_authority_and_custom_opt_in_is_audited(runtime, client):
    ctx = runtime[0]
    kind, obj = ticket(runtime)
    assert "ticket" not in load_schema()["object_types"]
    assert validate_type_rules({}, full=True)["runtime"] == {"enabled": False}
    before = counts()
    with pytest.raises(PermissionDenied):
        bind(runtime, obj, "TKT")
    assert counts() == before and not runtime_identities(ctx[3], "company:test").filter(object=obj).exists()
    revision = schema_revision(ctx[3])
    change(ctx, kind, descriptor())
    kind.refresh_from_db()
    assert schema_revision(ctx[3]) == revision + 1 and kind.last_provenance.command_name == "UpdateSchemaMetadata"
    assert not RuntimeObjectIdentity.objects.filter(object=obj).exists()
    code = bind(runtime, obj, "TKT")
    identity = RuntimeObjectIdentity.objects.get(object=obj)
    assert identity.created_provenance.actor_id == ctx[0].pk
    assert identity.created_provenance.command_name == "RuntimeObjectBound"
    assert identity.external_id == code and identity.context == "company:test"
    result = query(runtime, "read_entity", entity_id=code)
    assert result.status_code == 200 and result.data["metadata"]["type"] == "ticket"
    search = query(runtime, "search_entities", entity_type="ticket")
    assert search.status_code == 200 and search.data[0]["status"] is None
    capabilities = runtime[1].get(endpoint(runtime, "capabilities"))
    assert capabilities.data["schema_revision"] == schema_revision(ctx[3])
    assert result.data["metadata"]["schema_revision"] == schema_revision(ctx[3])
    assert capabilities.data["object_types"]["ticket"] == descriptor()
    assert "ticket" in capabilities.data["definitions"]["review"]["target_types"]
    assert client.get(url(ctx, "object-types/")).status_code == 200


def test_binding_is_immutable_idempotent_and_collisions_are_validation_errors(runtime):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    code = bind(runtime, obj, "TKT")
    original = RuntimeObjectIdentity.objects.get(object=obj)
    args = dict(actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id=code, context="company:test")
    assert bind_runtime_object(**args).pk == original.pk
    for patch in ({"external_id": "TKT-20261006-ABC123"}, {"context": "manager:test"}):
        with pytest.raises(ValidationError):
            bind_runtime_object(**{**args, **patch})
    other = create_object(actor=ctx[5], workspace=ctx[3], object_type=kind.pk, title="Other")
    before = counts()
    with pytest.raises(ValidationError) as error:
        bind_runtime_object(**{**args, "object_id": other.pk})
    assert "already bound" in str(error.value.detail) and counts() == before
    original.refresh_from_db()
    assert original.external_id == code and original.context == "company:test"


@pytest.mark.parametrize(
    "invalid", ["TKT-20261006-abc123", "ACT-20261006-ABC123", "TKT-20261006-ABC123x", "TKT-123456-ABC123", None]
)
def test_binding_uses_the_workspace_format(runtime, invalid):
    ctx = runtime[0]
    _, obj = ticket(runtime, enabled=True)
    # Public provisioning must provide an ID; omission must not select automatic generation.
    with pytest.raises(ValidationError):
        bind_runtime_object(
            actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id=invalid, context="company:test"
        )
    assert not RuntimeObjectIdentity.objects.filter(object=obj).exists()


def test_context_kind_schema_revision_and_admin_are_revalidated(runtime):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    change(ctx, kind, descriptor(contexts=["company"]))
    args = dict(
        actor=ctx[5], workspace=ctx[3], object_id=obj.pk, external_id="TKT-20261006-ABC123", context="company:test"
    )
    with pytest.raises(SchemaConflict):
        bind_runtime_object(**args, expected_schema_revision=schema_revision(ctx[3]) - 1)
    with pytest.raises(PermissionDenied):
        bind_runtime_object(**{**args, "context": "manager:test"})
    with pytest.raises(ValidationError):
        bind_runtime_object(**{**args, "context": "company:"})
    with pytest.raises(PermissionDenied):
        bind_runtime_object(**{**args, "actor": replace(ctx[5], actor_id=ctx[1].pk)})
    result = bind_runtime_object(**args, expected_schema_revision=schema_revision(ctx[3]))
    assert result.object_id == obj.pk


def test_descriptor_change_preserves_historical_identities_and_revocation_hides_context(runtime):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    code = bind(runtime, obj, "TKT")
    before, revision = counts(), schema_revision(ctx[3])
    for candidate in (descriptor("OTHER"), descriptor(contexts=["manager"])):
        with pytest.raises(ValidationError):
            change(ctx, kind, candidate)
        assert counts() == before and schema_revision(ctx[3]) == revision
    change(ctx, kind, {"enabled": False})
    assert query(runtime, "read_entity", entity_id=code).status_code == 404
    assert (
        "ticket" not in runtime[1].get(endpoint(runtime, "capabilities")).data["definitions"]["review"]["target_types"]
    )
    assert RuntimeObjectIdentity.objects.get(object=obj).external_id == code
    change(ctx, kind, descriptor())
    assert query(runtime, "read_entity", entity_id=code).status_code == 200


def test_custom_review_uses_registered_effects_approval_and_replay(runtime):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    code = bind(runtime, obj, "TKT")
    doc_kind = ObjectType.objects.get(workspace=ctx[3], key="document")
    evidence = create_object(
        actor=ctx[5], workspace=ctx[3], object_type=doc_kind.pk, title="Evidence", content="<p>Observed</p>"
    )
    evidence_code = bind(runtime, evidence, "DOC")
    pending = prepare(runtime, "review", code, {"assessment": "Reviewed custom type", "evidence_id": evidence_code})
    assert pending.status_code == 202, pending.data
    result = resolve(runtime, pending.data)
    assert result.status_code == 200 and result.data["target_id"] == code, result.data
    before = counts()
    assert resolve(runtime, pending.data).data == result.data and counts() == before
    # An intention open under a previous descriptor cannot reuse its old review.
    stale = prepare(runtime, "review", code, {"assessment": "Second review", "evidence_id": evidence_code})
    assert stale.status_code == 202
    change(ctx, kind, descriptor(contexts=["company"]))
    assert resolve(runtime, stale.data).data["code"] == "approval_stale"


def test_internal_runtime_creation_uses_descriptor_and_retries_keep_the_generated_id(runtime):
    ctx = runtime[0]
    kind, _ = ticket(runtime, enabled=True)
    # Use the common composed-effect identity writer without a global type branch.
    from plane.radar.commands.operations import identify_runtime_object
    from plane.radar.commands.execution import run_internal

    obj = create_object(actor=ctx[5], workspace=ctx[3], object_type=kind.pk, title="Generated")

    def operation():
        return identify_runtime_object(ctx[3], obj, "company:test")

    identity = run_internal(actor=ctx[5], workspace=ctx[3], name="TestGeneratedIdentity", operation=operation)
    again = run_internal(actor=ctx[5], workspace=ctx[3], name="TestGeneratedIdentity", operation=operation)
    assert identity.pk == again.pk and identity.external_id.startswith("TKT-")
    action_kind = ObjectType.objects.get(workspace=ctx[3], key="case")
    change(ctx, action_kind, {"enabled": False})
    before = counts()
    assert "capture_issue" not in runtime[1].get(endpoint(runtime, "capabilities")).data["definitions"]
    assert prepare(runtime).status_code == 403
    assert counts() == before


def test_grants_context_and_person_revocation_apply_to_both_channels(runtime):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    code = bind(runtime, obj, "TKT")
    binding, _ = issue_runtime_credential(
        actor=ctx[5],
        workspace=ctx[3],
        actor_id=runtime[2].actor_id,
        context="company:test",
        channel="plane",
        external_author=f"plane:{ctx[0].pk}",
        reviewer_id=ctx[0].pk,
        person_id=runtime[4].pk,
    )
    _, grant, _, objects = binding_for(user=ctx[0], workspace=ctx[3], binding_id=binding.pk)
    snapshot = load_context(objects, grant, [obj.pk])
    assert snapshot["objects"][0]["type"] == "ticket"
    change(ctx, kind, {"enabled": False})
    _, grant, _, objects = binding_for(user=ctx[0], workspace=ctx[3], binding_id=binding.pk)
    assert not objects.filter(pk=obj.pk).exists()
    assert query(runtime, "read_entity", entity_id=code).status_code == 404
    change(ctx, kind, descriptor())
    grant.object_types = ["person", "document"]
    fixture_write(lambda: grant.save())
    assert query(runtime, "read_entity", entity_id=code).status_code == 404
    assert not binding_for(user=ctx[0], workspace=ctx[3], binding_id=binding.pk)[3].filter(pk=obj.pk).exists()
    assert (
        "ticket" not in runtime[1].get(endpoint(runtime, "capabilities")).data["definitions"]["review"]["target_types"]
    )
    grant.is_active = False
    fixture_write(lambda: grant.save())
    assert query(runtime, "read_entity", entity_id=code).status_code == 401
    with pytest.raises(PermissionDenied):
        binding_for(user=ctx[0], workspace=ctx[3], binding_id=binding.pk)
    grant.is_active, grant.object_types = True, ["*"]
    fixture_write(lambda: grant.save())
    change(ctx, ObjectType.objects.get(pk=runtime[4].object_type_id), {"enabled": False})
    assert runtime[1].get(endpoint(runtime, "capabilities")).status_code == 401
    with pytest.raises(PermissionDenied):
        binding_for(user=ctx[0], workspace=ctx[3], binding_id=binding.pk)


def test_cli_grants_current_eligible_custom_types_and_excludes_disabled_types(runtime):
    ctx = runtime[0]
    ticket(runtime, enabled=True)
    change(ctx, ObjectType.objects.get(workspace=ctx[3], key="risk"), {"enabled": False})
    agent = uuid4()
    output = StringIO()
    call_command(
        "radar_runtime_provision",
        workspace=ctx[3].slug,
        admin_id=ctx[0].pk,
        context="company:test",
        agent_id=agent,
        reviewer_id=ctx[0].pk,
        person_id=runtime[4].pk,
        channel="plane",
        stdout=output,
    )
    grant = ActorGrant.objects.get(actor_id=agent)
    assert "ticket" in grant.object_types and "risk" not in grant.object_types and "*" not in grant.object_types


def test_migration_is_idempotent_and_preserves_custom_opt_out_and_bindings(runtime):
    ctx = runtime[0]
    migration = import_module("plane.radar.migrations.0015_type_runtime")
    editor = SimpleNamespace(connection=SimpleNamespace(alias="default"))
    kind, _ = ticket(runtime)
    identities = list(RuntimeObjectIdentity.objects.values("id", "object_id", "external_id", "context"))
    action = ObjectType.objects.get(workspace=ctx[3], key="action")
    case = ObjectType.objects.get(workspace=ctx[3], key="case")
    change(ctx, case, {"enabled": False})
    fixture_write(
        lambda: ObjectType.objects.filter(pk=action.pk).update(
            rules={k: v for k, v in action.rules.items() if k != "runtime"}
        )
    )
    revision = schema_revision(ctx[3])
    fixture_write(lambda: migration.install_runtime(django_apps, editor))
    assert schema_revision(ctx[3]) == revision + 1
    action.refresh_from_db()
    kind.refresh_from_db()
    case.refresh_from_db()
    assert action.rules["runtime"] == descriptor("ACT") and "runtime" not in kind.rules
    assert case.rules["runtime"] == {"enabled": False}
    fixture_write(lambda: migration.install_runtime(django_apps, editor))
    assert schema_revision(ctx[3]) == revision + 1
    state = WorkspaceSchemaState.objects.get(workspace=ctx[3])
    assert state.installed_base["definitions"]["types:action"]["rules"]["runtime"] == descriptor("ACT")
    assert list(RuntimeObjectIdentity.objects.values("id", "object_id", "external_id", "context")) == identities


def test_pending_generic_runtime_intent_cannot_ignore_a_changed_schema(runtime):
    ctx = runtime[0]
    _, obj = ticket(runtime, enabled=True)
    bind(runtime, obj, "TKT")
    actor = replace(ctx[5], actor_type="agent", actor_id=runtime[2].actor_id, run_id=uuid4(), on_behalf_of=ctx[0].pk)
    request = envelope(ctx, "CreateObject", {"object_type_id": str(obj.object_type_id), "title": "Intent"}, actor=actor)
    pending = execute_command(actor=actor, workspace=ctx[3], envelope=request)
    assert pending["status"] == "pending_approval"
    change(ctx, obj.object_type, {"enabled": False})
    with pytest.raises(CommandConflict):
        execute_command(actor=actor, workspace=ctx[3], envelope=request)


@pytest.mark.parametrize("case", ["missing_grant", "wrong_delegator", "scope_without_person", "other_context"])
def test_credential_provisioning_requires_authority_and_person_in_exact_scope(runtime, case):
    ctx = runtime[0]
    args = dict(
        actor=ctx[5],
        workspace=ctx[3],
        actor_id=runtime[2].actor_id,
        context="company:test",
        external_author="telegram:42",
        reviewer_id=ctx[0].pk,
        person_id=runtime[4].pk,
    )
    if case == "missing_grant":
        args["actor_id"] = uuid4()
    elif case == "wrong_delegator":
        args["reviewer_id"] = ctx[1].pk
    elif case == "scope_without_person":
        args["object_ids"] = [RuntimeObjectIdentity.objects.get(object=runtime[5]).external_id]
    else:
        args["context"] = "company:other"
    before = counts()
    with pytest.raises((PermissionDenied, ValidationError)):
        issue_runtime_credential(**args)
    assert counts() == before


def test_custom_type_retirement_and_wrong_context_hide_current_data_but_preserve_provenance(runtime, client):
    ctx = runtime[0]
    kind, obj = ticket(runtime, enabled=True)
    code = bind(runtime, obj, "TKT")
    assert query(runtime, "read_entity", entity_id=code, context="company:other").status_code == 400
    edit(ctx, kind, {"is_active": False})
    assert query(runtime, "read_entity", entity_id=code).status_code == 404
    assert client.get(url(ctx, f"objects/{obj.pk}/provenance/")).status_code == 200
    assert RuntimeObjectIdentity.objects.get(object=obj).external_id == code


def test_composed_creation_binds_then_validates_the_final_required_graph(runtime):
    ctx = runtime[0]
    relation = RelationType.objects.get(workspace=ctx[3], key="contains")
    edit(
        ctx,
        relation,
        {"source_types": ["case"], "target_types": ["management_item"], "allowed_pairs": [], "cardinality": "1..1"},
    )
    pending = prepare(runtime)
    assert pending.status_code == 202, pending.data
    result = resolve(runtime, pending.data)
    assert result.status_code == 200 and len(result.data["created_ids"]) == 3, result.data
    assert RuntimeObjectIdentity.objects.filter(workspace=ctx[3], object__object_type__key="case").count() == 1
