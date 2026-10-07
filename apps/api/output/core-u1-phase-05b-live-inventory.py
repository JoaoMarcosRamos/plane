"""Read-only inventory before C18 migration. Never writes to the active database."""
import os
import json
import hashlib

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
import django
django.setup()
from django.db import connection, transaction

result = {"mode": "read_only_before_migration", "records": [], "counts": {}}
with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT to_regclass('radar_operational_records')")
        exists = cursor.fetchone()[0] is not None
        result["legacy_table_present"] = exists
        if exists:
            cursor.execute("SELECT id, workspace_id, object_id, data FROM radar_operational_records ORDER BY id")
            for pk, workspace, obj, data in cursor.fetchall():
                if isinstance(data, str):
                    data = json.loads(data)
                assignment = data.get("assignment", {})
                cursor.execute("""SELECT r.target_id FROM radar_relations r JOIN radar_relation_types t ON t.id=r.relation_type_id
                    WHERE r.source_id=%s AND r.workspace_id=%s AND r.deleted_at IS NULL
                    AND t.key='assigned_to' AND t.deleted_at IS NULL""", [obj, workspace])
                executors = sorted(str(row[0]) for row in cursor.fetchall())
                legacy_executors = assignment.get("executor_ids") or ([assignment["executor_id"]] if assignment.get("executor_id") else [])
                cursor.execute("""SELECT d.key, v.value FROM radar_property_values v JOIN radar_property_definitions d ON d.id=v.definition_id
                    WHERE v.object_id=%s AND v.deleted_at IS NULL AND d.deleted_at IS NULL AND d.key IN ('due_date','due_at')""", [obj])
                deadlines = {key: json.loads(value) if isinstance(value, str) and value.startswith('"') else value for key,value in cursor.fetchall()}
                reviews, measurements = data.get("reviews", []), data.get("measurements", [])
                row = {"record_id": str(pk), "workspace_id": str(workspace), "object_id": str(obj),
                    "data_sha256": hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                    "reviews": len(reviews), "measurements": len(measurements),
                    "legacy_due_at": assignment.get("due_at"), "properties": deadlines,
                    "executor_sets_differ": sorted(legacy_executors) != executors if assignment else False,
                    "deadline_sources_coexist": bool(assignment.get("due_at") and deadlines.get("due_date")),
                    "keys": sorted(data)}
                result["records"].append(row)
        result["counts"] = {"records": len(result["records"]), "reviews": sum(row["reviews"] for row in result["records"]),
            "measurements": sum(row["measurements"] for row in result["records"]),
            "executor_divergences": sum(row["executor_sets_differ"] for row in result["records"]),
            "coexisting_deadlines": sum(row["deadline_sources_coexist"] for row in result["records"])}
print(json.dumps(result, indent=2, default=str))
