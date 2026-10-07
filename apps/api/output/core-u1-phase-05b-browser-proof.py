"""Independent PostgreSQL/ledger proof of the C18 browser fixture."""
import sys
import json
from pathlib import Path
sys.path.insert(0,"/code")
import django
django.setup()
from plane.db.models import Workspace
from plane.radar.models import Object, OperationalEntry, OperationalRecord, CommandExecution
from plane.radar.operational import operation_projection, history_page
workspace=Workspace.objects.filter(slug__startswith="c18-browser-").latest("created_at")
action=Object.objects.get(workspace=workspace,title="Delegação atrasada sem data")
conflict=Object.objects.get(workspace=workspace,title="Revisar prazos divergentes")
indicator=Object.objects.get(workspace=workspace,title="Indicador C18")
legacy=Object.objects.get(workspace=workspace,title="Autoria legada preservada")
current=operation_projection(action,timezone_name="America/Bahia")
assert current["deadline"]["overdue"] and current["deadline"]["due_date"] is None
assert current["executors"]==current["operation_data"]["assignment"]["executor_ids"]
assert OperationalEntry.objects.filter(object=action,kind="review").count()==23
assert OperationalEntry.objects.filter(object=indicator,kind="measurement").count()==3
assert not OperationalRecord.objects.filter(object__in=[action,conflict,indicator]).exists()
assert operation_projection(conflict,timezone_name="America/Bahia")["deadline"]["conflict"]
first=history_page(workspace,action,kind="review",limit=20)
second=history_page(workspace,action,kind="review",limit=20,cursor=first["next_cursor"])
assert len(first["items"])==20 and len(second["items"])==3 and not second["next_cursor"]
assert len({row["id"] for row in first["items"]+second["items"]})==23
original=OperationalEntry.objects.get(object=legacy)
assert original.actor_type=="unknown" and original.actor_id is None and original.occurred_at is None and original.object_version is None
entries=OperationalEntry.objects.filter(workspace=workspace,origin="command").select_related("created_provenance")
assert all(entry.created_provenance.command_name in {"DelegateAction","ReviewObject","RecordMeasurement"} and CommandExecution.objects.filter(workspace=workspace,id=entry.created_provenance.command_id,status="executed").exists() for entry in entries)
result={"workspace_slug":workspace.slug,"overdue_delegation_without_date":True,"conflict_explicit":True,"canonical_executors_consistent":True,"review_pages":[20,3],"measurement_entries":3,"new_operations_without_legacy_writes":True,"unknown_legacy_author_and_time_preserved":True,"command_execution_provenance_links":True}
Path("output/core-u1-phase-05b-browser-proof.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
