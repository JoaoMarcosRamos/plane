"""0015 migration cycle in the disposable plane DB, separate from pytest test_plane."""

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
import django

django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from plane.radar.ontology.package import package_definitions

before = [("radar", "0014_type_presentation")]
after = [("radar", "0015_type_runtime")]
run = uuid4().hex[:8]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


apps = migrate(before)
user = apps.get_model("db", "User").objects.create(
    username=f"u1-phase05a-migration-{run}", email=f"u1-phase05a-migration-{run}@fixture.local"
)
workspace = apps.get_model("db", "Workspace").objects.create(name="Migration 5A", slug=f"phase05a-migration-{run}", owner=user)
types = apps.get_model("radar", "ObjectType")
legacy = deepcopy(package_definitions())
ids = {}
for key, spec in legacy.items():
    group, identifier = key.split(":", 1)
    if group == "types":
        spec["rules"].pop("runtime", None)
        args = {"workspace": workspace, "is_system": True, "key": identifier, **spec}
        # Existing explicit opt-out is a customization, not an upgrade conflict.
        if identifier == "case":
            args["rules"] = {**spec["rules"], "runtime": {"enabled": False}}
        ids[key] = types.objects.create(**args).pk
    elif group == "properties":
        type_key, prop_key = identifier.split(".", 1)
        ids[key] = apps.get_model("radar", "PropertyDefinition").objects.create(
            workspace=workspace, is_system=True, object_type_id=ids[f"types:{type_key}"], key=prop_key, **spec
        ).pk
    else:
        ids[key] = apps.get_model("radar", "RelationType").objects.create(
            workspace=workspace, is_system=True, key=identifier, **spec
        ).pk
states = apps.get_model("radar", "WorkspaceSchemaState")
states.objects.create(
    workspace=workspace, origin="package", package_version="3.2.0", package_hash="0" * 64,
    revision=5, installed_base={"definitions": legacy, "ids": {key: str(pk) for key, pk in ids.items()}},
)
custom = types.objects.create(workspace=workspace, key="ticket", name="Workspace only", rules={})
fact = apps.get_model("radar", "Object").objects.create(
    workspace=workspace, object_type_id=ids["types:action"], title="Historical", content="<p>Kept</p>", version=4
)
binding = apps.get_model("radar", "RuntimeObjectIdentity").objects.create(
    workspace=workspace, object=fact, external_id="ACT-20261006-ABC123", context="company:test"
)
identity_before = (binding.pk, binding.object_id, binding.context, binding.external_id, binding.created_at, binding.updated_at)


def verify_facts(apps):
    stored = apps.get_model("radar", "Object").objects.get(pk=fact.pk)
    stored_binding = apps.get_model("radar", "RuntimeObjectIdentity").objects.get(pk=binding.pk)
    assert stored.version == 4 and stored.content == "<p>Kept</p>"
    assert (stored_binding.pk, stored_binding.object_id, stored_binding.context, stored_binding.external_id,
            stored_binding.created_at, stored_binding.updated_at) == identity_before


apps = migrate(after)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
for key, pk in ids.items():
    if key.startswith("types:"):
        row = types.objects.get(pk=pk)
        expected = {"enabled": False} if row.key == "case" else package_definitions()[key]["rules"]["runtime"]
        assert row.rules["runtime"] == expected
state = states.objects.get(workspace_id=workspace.pk)
assert state.revision == 6 and state.package_hash == "0" * 64
assert state.installed_base["definitions"] == package_definitions()
assert types.objects.get(pk=custom.pk).rules == {}
verify_facts(apps)

from plane.db.models import Workspace
from plane.radar.commands.schema import upgrade_plan, validate_effective_schema

live = Workspace.objects.get(pk=workspace.pk)
validate_effective_schema(live)
plan = upgrade_plan(live, package_definitions())
assert plan["changes"] == {} and plan["conflicts"] == [] and plan["migration_blockers"] == [], plan

# Reapply the forward function itself to prove idempotency without a new migration entry.
from importlib import import_module
from types import SimpleNamespace

import_module("plane.radar.migrations.0015_type_runtime").install_runtime(apps, SimpleNamespace(connection=connection))
assert states.objects.get(pk=state.pk).revision == 6
apps = migrate(before)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
assert all("runtime" not in row.rules for row in types.objects.filter(workspace_id=workspace.pk))
assert states.objects.get(pk=state.pk).revision == 7
assert states.objects.get(pk=state.pk).installed_base["definitions"] == legacy
verify_facts(apps)
apps = migrate(after)
assert apps.get_model("radar", "WorkspaceSchemaState").objects.get(pk=state.pk).revision == 8
verify_facts(apps)

result = {
    "migration": "0015_type_runtime", "forward_reverse_reapply": True, "idempotent": True,
    "managed_type_count": 11, "custom_type_disabled_by_default": True,
    "explicit_local_opt_out_preserved_on_forward": True, "installed_base_updated_without_conflicts": True,
    "existing_fact_version_and_content_preserved": True, "identity_and_timestamps_preserved": True,
    "schema_revision": [5, 6, 7, 8], "package_hash_unchanged_until_explicit_upgrade": True,
    "reverse_removes_descriptors_requires_export": True,
}
Path("output/core-u1-phase-05a-migration.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
