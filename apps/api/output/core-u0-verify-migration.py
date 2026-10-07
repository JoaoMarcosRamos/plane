"""Migration round trip on the disposable Compose database, using historical models."""
import json
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
import django

django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

before = [("radar", "0010_object_collaboration")]
after = [("radar", "0011_objecttype_rules")]
executor = MigrationExecutor(connection)
executor.migrate(before)
apps = executor.loader.project_state(before).apps
user = apps.get_model("db", "User").objects.create(username="u0-migration", email="u0-migration@fixture.local")
workspace = apps.get_model("db", "Workspace").objects.create(name="Migration fixture", slug="u0-migration", owner=user)
model = apps.get_model("radar", "ObjectType")
rows = {key: model.objects.create(workspace=workspace, key=key, name=key).pk for key in ["objective", "risk", "custom"]}
executor = MigrationExecutor(connection)
executor.migrate(after)
model = executor.loader.project_state(after).apps.get_model("radar", "ObjectType")
assert model.objects.get(pk=rows["risk"]).rules == {"invariants": [{"kind": "product", "result": "score", "factors": ["likelihood", "impact"]}]}
assert model.objects.get(pk=rows["objective"]).rules == {"invariants": [{"kind": "ordered_dates", "first": "start_date", "second": "due_date"}]}
assert model.objects.get(pk=rows["custom"]).rules == {}
executor = MigrationExecutor(connection)
executor.migrate(before)
assert "rules" not in {c.name for c in connection.introspection.get_table_description(connection.cursor(), "radar_object_types")}
executor = MigrationExecutor(connection)
executor.migrate(after)
model = executor.loader.project_state(after).apps.get_model("radar", "ObjectType")
assert model.objects.filter(pk__in=rows.values()).count() == 3
result = {"legacy_types_backfilled": 2, "custom_type_preserved": True, "identities_preserved": True, "reverse_forward_passed": True}
Path("output/core-u0-migration.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
