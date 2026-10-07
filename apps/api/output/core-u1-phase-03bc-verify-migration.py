"""0013 forward/reverse/forward on the disposable plane DB, separate from pytest test_plane."""

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
from plane.radar.ontology.package import PACKAGE_BEHAVIOR, package_definitions

SECTIONS = ("creation", "lifecycle")
before = [("radar", "0012_workspace_schema")]
after = [("radar", "0013_type_descriptors")]
run = uuid4().hex[:8]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def strip(definitions):
    result = deepcopy(definitions)
    for key, spec in result.items():
        if key.startswith("types:"):
            spec["rules"] = {k: v for k, v in spec["rules"].items() if k not in SECTIONS}
    return result


apps = migrate(before)
user = apps.get_model("db", "User").objects.create(
    username=f"u1-phase03bc-migration-{run}", email=f"u1-phase03bc-migration-{run}@fixture.local"
)
workspace_model = apps.get_model("db", "Workspace")
workspaces = {
    key: workspace_model.objects.create(name=key, slug=f"phase03bc-migration-{run}-{key}", owner=user)
    for key in ("exact", "custom", "empty")
}
models = {
    group: apps.get_model("radar", name)
    for group, name in (("types", "ObjectType"), ("properties", "PropertyDefinition"), ("relations", "RelationType"))
}
legacy = strip(package_definitions())
ids = {}
for key, spec in legacy.items():
    group, identifier = key.split(":", 1)
    args = {"workspace": workspaces["exact"], "is_system": True, **spec}
    if group == "properties":
        type_key, prop_key = identifier.split(".", 1)
        args.update(object_type_id=ids[f"types:{type_key}"], key=prop_key)
    else:
        args["key"] = identifier
    ids[key] = models[group].objects.create(**args).pk
state_model = apps.get_model("radar", "WorkspaceSchemaState")
state_model.objects.create(
    workspace=workspaces["exact"],
    origin="package",
    package_version="3.2.0",
    package_hash="0" * 64,
    revision=3,
    installed_base={"definitions": legacy, "ids": {key: str(pk) for key, pk in ids.items()}},
)
# A pre-existing local section is never overwritten; an unknown workspace type is never touched.
local_lifecycle = {"property": "status", "initial": "active", "transitions": []}
local_objective = models["types"].objects.create(
    workspace=workspaces["custom"], key="objective", name="Local", rules={"invariants": [], "lifecycle": local_lifecycle}
)
ticket = models["types"].objects.create(workspace=workspaces["custom"], key="ticket", name="Ticket", rules={})
action_type = models["types"].objects.get(pk=ids["types:action"])
fact = apps.get_model("radar", "Object").objects.create(
    workspace=workspaces["exact"], object_type=action_type, title="Historical action", version=7
)
value = apps.get_model("radar", "PropertyValue").objects.create(
    workspace=workspaces["exact"], object=fact, definition_id=ids["properties:action.status"], value="in_progress"
)


def check_facts(apps):
    assert apps.get_model("radar", "Object").objects.get(pk=fact.pk).version == 7
    assert apps.get_model("radar", "PropertyValue").objects.get(pk=value.pk).value == "in_progress"


apps = migrate(after)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
for key in PACKAGE_BEHAVIOR:
    row = types.objects.get(pk=ids[f"types:{key}"])
    assert {k: v for k, v in row.rules.items() if k != "invariants"} == PACKAGE_BEHAVIOR[key], key
    assert row.rules["invariants"] == legacy[f"types:{key}"]["rules"]["invariants"], key
state = states.objects.get(workspace_id=workspaces["exact"].pk)
assert state.revision == 4 and state.package_hash == "0" * 64
assert state.installed_base["definitions"] == {
    key: (
        {**spec, "rules": {**spec["rules"], **PACKAGE_BEHAVIOR[key.split(":", 1)[1]]}} if key.startswith("types:") else spec
    )
    for key, spec in legacy.items()
}
assert types.objects.get(pk=local_objective.pk).rules["lifecycle"] == local_lifecycle
assert "creation" not in types.objects.get(pk=local_objective.pk).rules
assert types.objects.get(pk=ticket.pk).rules == {}
assert not states.objects.filter(workspace_id__in=[workspaces["custom"].pk, workspaces["empty"].pk]).exists()
check_facts(apps)

# Live code over the migrated workspace: descriptors are effectively valid and the package has no pending change.
from plane.db.models import Workspace
from plane.radar.commands.schema import upgrade_plan, validate_effective_schema

live = Workspace.objects.get(pk=workspaces["exact"].pk)
validate_effective_schema(live)
plan = upgrade_plan(live, package_definitions())
assert plan["changes"] == {} and plan["conflicts"] == [] and plan["migration_blockers"] == []

apps = migrate(before)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
assert all(not set(row.rules).intersection(SECTIONS) for row in types.objects.all())
state = states.objects.get(workspace_id=workspaces["exact"].pk)
assert state.revision == 5 and state.installed_base["definitions"] == legacy
check_facts(apps)

apps = migrate(after)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
assert types.objects.get(pk=ids["types:decision"]).rules["lifecycle"] == PACKAGE_BEHAVIOR["decision"]["lifecycle"]
# Downgrade is lossy by design for local sections; the reapplied package value is explicit.
assert types.objects.get(pk=local_objective.pk).rules["lifecycle"] == PACKAGE_BEHAVIOR["objective"]["lifecycle"]
assert states.objects.get(workspace_id=workspaces["exact"].pk).revision == 6
check_facts(apps)

result = {
    "migration": "0013_type_descriptors",
    "seeded_types_installed": len(PACKAGE_BEHAVIOR),
    "invariants_preserved": True,
    "installed_base_updated_for_managed_ids": True,
    "schema_revision": {"before": 3, "forward": 4, "reverse": 5, "reapplied": 6},
    "package_hash_unchanged_until_explicit_upgrade": True,
    "preexisting_local_lifecycle_preserved_on_forward": True,
    "unknown_type_untouched": True,
    "empty_workspace_without_state": True,
    "fact_version_and_state_preserved": {"version": 7, "status": "in_progress"},
    "live_effective_schema_valid": True,
    "live_upgrade_plan_without_changes_or_conflicts": True,
    "reverse_strips_sections_including_local": True,
    "reverse_forward_passed": True,
}
Path("output/core-u1-phase-03bc-migration.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
