"""0014 forward/reverse/forward on the disposable plane DB, separate from pytest test_plane."""

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
from plane.radar.ontology.package import PACKAGE_PRESENTATION, package_definitions

before = [("radar", "0013_type_descriptors")]
after = [("radar", "0014_type_presentation")]
run = uuid4().hex[:8]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return executor.loader.project_state(target).apps


def strip(definitions):
    result = deepcopy(definitions)
    for key, spec in result.items():
        if key.startswith("types:"):
            spec["rules"] = {k: v for k, v in spec["rules"].items() if k != "presentation"}
    return result


apps = migrate(before)
user = apps.get_model("db", "User").objects.create(
    username=f"u1-phase04-migration-{run}", email=f"u1-phase04-migration-{run}@fixture.local"
)
workspace_model = apps.get_model("db", "Workspace")
workspaces = {
    key: workspace_model.objects.create(name=key, slug=f"phase04-migration-{run}-{key}", owner=user)
    for key in ("exact", "custom")
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
apps.get_model("radar", "WorkspaceSchemaState").objects.create(
    workspace=workspaces["exact"],
    origin="package",
    package_version="3.2.0",
    package_hash="0" * 64,
    revision=5,
    installed_base={"definitions": legacy, "ids": {key: str(pk) for key, pk in ids.items()}},
)
local_layout = {"narrative": "content", "sections": []}
local_case = models["types"].objects.create(
    workspace=workspaces["custom"], key="case", name="Local case", rules={"presentation": local_layout}
)
action_type = models["types"].objects.get(pk=ids["types:action"])
fact = apps.get_model("radar", "Object").objects.create(
    workspace=workspaces["exact"], object_type=action_type, title="Historical", content="<p>Kept</p>", version=4
)

apps = migrate(after)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
for key, presentation in PACKAGE_PRESENTATION.items():
    rules = types.objects.get(pk=ids[f"types:{key}"]).rules
    assert rules["presentation"] == presentation and rules["lifecycle"] == legacy[f"types:{key}"]["rules"]["lifecycle"]
state = states.objects.get(workspace_id=workspaces["exact"].pk)
assert state.revision == 6 and state.package_hash == "0" * 64
assert state.installed_base["definitions"]["types:action"]["rules"]["presentation"] == PACKAGE_PRESENTATION["action"]
assert types.objects.get(pk=local_case.pk).rules == {"presentation": local_layout}
stored = apps.get_model("radar", "Object").objects.get(pk=fact.pk)
assert stored.version == 4 and stored.content == "<p>Kept</p>"

from plane.db.models import Workspace
from plane.radar.commands.schema import upgrade_plan, validate_effective_schema

live = Workspace.objects.get(pk=workspaces["exact"].pk)
validate_effective_schema(live)
plan = upgrade_plan(live, package_definitions())
assert plan["changes"] == {} and plan["conflicts"] == [] and plan["migration_blockers"] == []

apps = migrate(before)
types, states = apps.get_model("radar", "ObjectType"), apps.get_model("radar", "WorkspaceSchemaState")
assert all("presentation" not in row.rules for row in types.objects.all())
assert all("lifecycle" in types.objects.get(pk=ids[f"types:{key}"]).rules for key in PACKAGE_PRESENTATION)
assert states.objects.get(workspace_id=workspaces["exact"].pk).installed_base["definitions"] == legacy
apps = migrate(after)
types = apps.get_model("radar", "ObjectType")
assert types.objects.get(pk=local_case.pk).rules["presentation"] == PACKAGE_PRESENTATION["case"]
assert apps.get_model("radar", "WorkspaceSchemaState").objects.get(workspace_id=workspaces["exact"].pk).revision == 8

result = {
    "migration": "0014_type_presentation",
    "seeded_types_installed": len(PACKAGE_PRESENTATION),
    "creation_lifecycle_invariants_preserved": True,
    "installed_base_updated_for_managed_ids": True,
    "schema_revision": {"before": 5, "forward": 6, "reverse": 7, "reapplied": 8},
    "package_hash_unchanged_until_explicit_upgrade": True,
    "preexisting_local_presentation_preserved_on_forward": True,
    "fact_version_and_content_preserved": {"version": 4, "content": "<p>Kept</p>"},
    "live_effective_schema_valid": True,
    "live_upgrade_plan_without_changes_or_conflicts": True,
    "reverse_strips_presentation_including_local": True,
    "reverse_forward_passed": True,
}
Path("output/core-u1-phase-04-migration.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
