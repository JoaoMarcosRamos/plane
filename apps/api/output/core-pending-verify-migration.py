"""Run only on the disposable database, with real migrations enabled."""
import sys
sys.path.insert(0, "/code")
import django
django.setup()
import json
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from plane.radar.models import Object, Relation
old, new = ("radar", "0016_operational_history"), ("radar", "0017_query_page_indexes")
originals = {model.__name__: list(model.all_objects.order_by("pk").values()) for model in (Object, Relation)}
for target in (old, new, old, new):
    MigrationExecutor(connection).migrate([target])
    assert {model.__name__: list(model.all_objects.order_by("pk").values()) for model in (Object, Relation)} == originals
with connection.cursor() as cursor:
    indices = connection.introspection.get_constraints(cursor, "radar_objects")
assert indices["radar_object_ws_page_idx"]["index"]
result = {"roundtrip": True, "objects_preserved": len(originals["Object"]), "relations_preserved": len(originals["Relation"]), "index_installed": True}
print(json.dumps(result))
open("output/core-pending-migration.json", "w").write(json.dumps(result, indent=2))
