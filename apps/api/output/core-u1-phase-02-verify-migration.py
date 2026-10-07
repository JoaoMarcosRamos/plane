"""0012 forward/reverse/forward on the disposable plane DB, separate from pytest test_plane."""
import json
import os
from pathlib import Path
from uuid import uuid4
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from plane.radar.ontology.package import package_definitions

fixture_run = uuid4().hex[:8]
before = [("radar", "0011_objecttype_rules")]
after = [("radar", "0012_workspace_schema")]
executor = MigrationExecutor(connection)
executor.migrate(before)
apps = executor.loader.project_state(before).apps
user = apps.get_model("db", "User").objects.create(username=f"u1-phase02-migration-{fixture_run}", email=f"u1-phase02-migration-{fixture_run}@fixture.local")
workspace_model = apps.get_model("db", "Workspace")
workspaces = {key: workspace_model.objects.create(name=key, slug=f"phase02-migration-{fixture_run}-{key}", owner=user) for key in ("empty", "exact", "custom", "divergent")}
models_by_group = {key: apps.get_model("radar", name) for key, name in (("types", "ObjectType"), ("properties", "PropertyDefinition"), ("relations", "RelationType"))}
base = package_definitions()
ids = {}
for key, spec in base.items():
    group, identifier = key.split(":", 1)
    args = {"workspace": workspaces["exact"], "is_system": True, **spec}
    if group == "properties":
        type_key, prop_key = identifier.split(".", 1)
        args.update(object_type_id=ids[f"types:{type_key}"], key=prop_key)
    else:
        args["key"] = identifier
    ids[key] = models_by_group[group].objects.create(**args).pk
custom = models_by_group["types"].objects.create(workspace=workspaces["custom"], key="custom", name="Local", is_system=False)
divergent = models_by_group["types"].objects.create(workspace=workspaces["divergent"], key="objective", name="Local objective", is_system=True, is_active=False, rules=base["types:objective"]["rules"])
fact = apps.get_model("radar", "Object").objects.create(workspace=workspaces["divergent"], object_type=divergent, title="Historical fact", version=7)
executor = MigrationExecutor(connection); executor.migrate(after)
apps_after = executor.loader.project_state(after).apps
state = apps_after.get_model("radar", "WorkspaceSchemaState")
assert not state.objects.filter(workspace_id=workspaces["empty"].pk).exists()
exact = state.objects.get(workspace_id=workspaces["exact"].pk)
assert exact.origin == "legacy" and exact.package_version == "" and exact.package_hash == "" and exact.divergences == []
assert exact.installed_base["definitions"] == base
assert exact.installed_base["ids"] == {key: str(pk) for key, pk in ids.items()}
custom_state = state.objects.get(workspace_id=workspaces["custom"].pk)
assert custom_state.origin == "legacy" and custom_state.divergences
change = next(item for item in state.objects.get(workspace_id=workspaces["divergent"].pk).divergences if item["key"] == "types:objective")
assert change["local"]["name"] == "Local objective" and change["local"]["is_active"] is False
assert apps_after.get_model("radar", "Object").objects.get(pk=fact.pk).version == 7
assert apps_after.get_model("radar", "SchemaUpgrade").objects.filter(to_version="legacy-baseline").count() >= 3
executor = MigrationExecutor(connection); executor.migrate(before)
assert "radar_workspace_schema_states" not in connection.introspection.table_names()
executor = MigrationExecutor(connection); executor.migrate(after)
apps_after = executor.loader.project_state(after).apps
assert apps_after.get_model("radar", "ObjectType").objects.filter(pk__in=ids.values()).count() == 11
assert apps_after.get_model("radar", "ObjectType").objects.get(pk=custom.pk).name == "Local"
assert apps_after.get_model("radar", "Object").objects.get(pk=fact.pk).version == 7
result = {"empty_workspace_uninitialized": True, "exact_legacy_without_presumed_version": True, "custom_preserved": True, "divergences_recorded": True, "metadata_ids_preserved": True, "fact_version_preserved": 7, "reverse_forward_passed": True}
Path("output/core-u1-phase-02-migration.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
