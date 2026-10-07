"""Actual 0015→0016 upgrade on disposable plane, preserving archives and facts."""
import os
import sys
sys.path.insert(0, "/code")
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
from importlib import import_module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.test")
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from plane.radar.ontology.package import package_definitions
run=uuid4().hex[:8]
before=[("radar","0015_type_runtime")]; after=[("radar","0016_operational_history")]
def migrate(target):
    executor=MigrationExecutor(connection); executor.migrate(target); return executor.loader.project_state(target).apps
apps=migrate(before)
user=apps.get_model("db","User").objects.create(username=f"c18-migration-{run}",email=f"c18-migration-{run}@fixture.local")
workspace=apps.get_model("db","Workspace").objects.create(name="Migration C18",slug=f"c18-migration-{run}",owner=user)
apps.get_model("db","WorkspaceMember").objects.create(workspace=workspace,member=user,role=20,is_active=True)
legacy=deepcopy(package_definitions()); legacy.pop("properties:action.due_at")
ids={}
for key,spec in legacy.items():
    group,ident=key.split(":",1)
    if group=="types": row=apps.get_model("radar","ObjectType").objects.create(workspace=workspace,is_system=True,key=ident,**spec)
    elif group=="properties":
        type_key,prop_key=ident.split(".",1)
        row=apps.get_model("radar","PropertyDefinition").objects.create(workspace=workspace,is_system=True,object_type_id=ids[f"types:{type_key}"],key=prop_key,**spec)
    else: row=apps.get_model("radar","RelationType").objects.create(workspace=workspace,is_system=True,key=ident,**spec)
    ids[key]=row.pk
state=apps.get_model("radar","WorkspaceSchemaState").objects.create(workspace=workspace,origin="package",package_version="3.2.0",package_hash="0"*64,revision=5,installed_base={"definitions":legacy,"ids":{k:str(v) for k,v in ids.items()}})
obj=apps.get_model("radar","Object").objects.create(workspace=workspace,object_type_id=ids["types:action"],title="Historical",version=4)
person=apps.get_model("radar","Object").objects.create(workspace=workspace,object_type_id=ids["types:person"],title="Person",version=1)
source={"assignment":{"executor_ids":[str(person.pk)],"due_at":"2026-10-07T13:45:12.123456-03:00","state":"proposed","proposed_at":"2026-10-06T12:00:00-03:00"}}
record=apps.get_model("radar","OperationalRecord").objects.create(workspace=workspace,object=obj,data=source)
identity=apps.get_model("radar","RuntimeObjectIdentity").objects.create(workspace=workspace,object=obj,external_id="ACT-20261006-ABC123",context="company:test")
custom_ws=apps.get_model("db","Workspace").objects.create(name="Custom",slug=f"c18-custom-{run}",owner=user)
custom_type=apps.get_model("radar","ObjectType").objects.create(workspace=custom_ws,is_system=True,key="action",name="Custom Action")
custom_prop=apps.get_model("radar","PropertyDefinition").objects.create(workspace=custom_ws,is_system=False,object_type=custom_type,key="due_at",name="Local override",value_type="string",is_active=False)
apps=migrate(after)
assert apps.get_model("radar","Object").objects.get(pk=obj.pk).version==4
stored=apps.get_model("radar","OperationalRecord").objects.get(pk=record.pk)
assert stored.data==source and stored.created_at==record.created_at and stored.updated_at==record.updated_at and stored.backfill_hash==""
assert not apps.get_model("radar","OperationalEntry").objects.exists()
assert apps.get_model("radar","RuntimeObjectIdentity").objects.get(pk=identity.pk).external_id==identity.external_id
state=apps.get_model("radar","WorkspaceSchemaState").objects.get(pk=state.pk)
assert state.revision==6 and state.installed_base["definitions"]==package_definitions()
local=apps.get_model("radar","PropertyDefinition").objects.get(pk=custom_prop.pk)
assert local.value_type=="string" and not local.is_active and local.name=="Local override"
import_module("plane.radar.migrations.0016_operational_history").install_deadline(apps,SimpleNamespace(connection=connection))
assert apps.get_model("radar","WorkspaceSchemaState").objects.get(pk=state.pk).revision==6
from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.operational_backfill import preview_backfill,backfill,export_workspace
from plane.radar.models import OperationalEntry, PropertyValue
from plane.radar.commands.schema import validate_effective_schema,upgrade_plan
actor=Actor(actor_type="human",actor_id=user.pk,source="fixture.migration",reason="Reviewed C18 backfill",correlation_id=uuid4())
live=Workspace.objects.get(pk=workspace.pk)
validate_effective_schema(live)
assert upgrade_plan(live,package_definitions())["changes"]=={}
plan=preview_backfill(actor=actor,workspace=live,timezone_name="America/Bahia")
assert plan["counts"]["blocking_records"]==0
result=backfill(actor=actor,workspace=live,reviewed_hash=plan["reviewed_hash"],timezone_name="America/Bahia")
assert result["created_entries"]==1 and result["materialized_deadlines"]==1
assert PropertyValue.objects.get(object_id=obj.pk,definition__key="due_at").value==source["assignment"]["due_at"]
entry=OperationalEntry.objects.get(object_id=obj.pk)
assert entry.source_data==source["assignment"] and entry.actor_type=="unknown" and entry.object_version is None
assert backfill(actor=actor,workspace=live,reviewed_hash=plan["reviewed_hash"],timezone_name="America/Bahia")["created_entries"]==0
export=list(export_workspace(live)); assert export[0]["data"]==source and export[1]["source_data"]==source["assignment"]
try: migrate(before)
except IrreversibleError: pass
else: raise AssertionError("Destructive reversal must be blocked")
assert OperationalEntry.objects.get(pk=entry.pk).source_data==source["assignment"]
from django.core.management import call_command
from io import StringIO
out=StringIO(); call_command("radar_operational_backfill",workspace=live.slug,admin_id=str(user.pk),export=True,stdout=out)
assert len(out.getvalue().splitlines())==2
result={"migration":"0016_operational_history","upgrade_preserves_archive_and_timestamps":True,"no_automatic_fact_backfill":True,"custom_due_at_definition_preserved":True,"installed_base_updated_without_conflicts":True,"schema_revision":[5,6],"forward_idempotent":True,"reviewed_backfill_idempotent":True,"raw_offset_and_microseconds_preserved":True,"unknown_original_authorship_preserved":True,"identity_preserved":True,"streaming_cli_export_verified":True,"destructive_reverse_blocked_and_history_preserved":True}
Path("output/core-u1-phase-05b-migration.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
