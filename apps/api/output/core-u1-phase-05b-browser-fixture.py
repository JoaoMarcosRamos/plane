"""Disposable C18 harness: real API, commands, authentication and PostgreSQL."""
import sys
import json
from uuid import uuid4
from datetime import timedelta
sys.path.insert(0, "/code")
import django
django.setup()
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from rest_framework.test import APIClient
from wsgiref.simple_server import make_server
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import create_object, initialize_semantic_model, execute_command
from plane.radar.commands.actor import Actor
from plane.radar.commands.context import command_now
from plane.radar.commands.execution import run_internal
from plane.radar.runtime_identity import bind_identity
from plane.radar.models import ObjectType, OperationalEntry, OperationalRecord
from plane.radar.tests.fixture_writes import fixture_write
from plane.radar.operational_backfill import preview_backfill, backfill
call_command("migrate", verbosity=0)
users = {name: User.objects.create(email=f"c18-{name}-{uuid4().hex[:8]}@fixture.local", username=f"c18-{name}-{uuid4().hex[:8]}") for name in ("admin", "guest", "outsider")}
workspace = Workspace.objects.create(name="C18 browser", slug=f"c18-browser-{uuid4().hex[:8]}", owner=users["admin"])
for name, role in (("admin",20),("guest",5)):
    WorkspaceMember.objects.create(workspace=workspace, member=users[name], role=role, is_active=True)
def actor(): return Actor(actor_type="human", actor_id=users["admin"].pk, source="fixture.browser", reason="C18 browser fixture", correlation_id=uuid4())
initialize_semantic_model(actor=actor(),workspace=workspace)
def obj(kind,title,**kwargs):
    return create_object(actor=actor(),workspace=workspace,object_type=ObjectType.objects.get(workspace=workspace,key=kind).pk,title=title,**kwargs)
def bind(item):
    return run_internal(actor=actor(),workspace=workspace,name="BindFixtureIdentity",operation=lambda: bind_identity(workspace,item,"company:test",user_id=users["admin"].pk,at=command_now()))
def command(name,data,items):
    for item in items: item.refresh_from_db()
    return execute_command(actor=actor(),workspace=workspace,envelope={"command_name":name,"command_version":1,"idempotency_key":str(uuid4()),"expected_versions":{str(i.pk):i.version for i in items},"input":data,"reason":"C18 browser fixture","assertion":{"kind":"asserted"}})
executor = obj("person","Executor C18")
doc = obj("document","Evidence C18",content="<p>Verified observation</p>")
action = obj("action","Delegação atrasada sem data",properties={"description":"Datetime controls the deadline"})
conflict = obj("action","Revisar prazos divergentes",properties={"description":"Both sources stay explicit","due_date":(timezone.now()+timedelta(days=2)).date().isoformat()})
indicator = obj("indicator","Indicador C18",properties={"description":"Observed indicator"})
for item in (executor,doc,action,conflict,indicator): bind(item)
for item in (action,conflict):
    command("DelegateAction",{"action_id":str(item.pk),"executor_id":str(executor.pk),"context":"company:test","due_at":(timezone.now()-timedelta(hours=1)).isoformat()},[item,executor])
for index in range(23):
    command("ReviewObject",{"target_id":str(action.pk),"evidence_id":str(doc.pk),"context":"company:test","assessment":f"Review C18 {index:02d}"},[action,doc])
for index in range(3):
    command("RecordMeasurement",{"indicator_id":str(indicator.pk),"evidence_id":str(doc.pk),"context":"company:test","value":index,"measured_at":(timezone.now()-timedelta(days=3-index)).isoformat()},[indicator,doc])
legacy = obj("action","Autoria legada preservada",properties={"description":"Backfill preserves unknowns"})
fixture_write(lambda: OperationalRecord.objects.create(workspace=workspace,object=legacy,data={"review":{"assessment":"Review original legado","evidence_id":str(doc.pk)}}))
plan=preview_backfill(actor=actor(),workspace=workspace)
backfill(actor=actor(),workspace=workspace,reviewed_hash=plan["reviewed_hash"])
objects={"action":str(action.pk),"conflict":str(conflict.pk),"indicator":str(indicator.pk),"legacy":str(legacy.pk)}
settings.ALLOWED_HOSTS=["localhost","127.0.0.1","host.docker.internal"]
settings.SESSION_COOKIE_SECURE=False
application=get_wsgi_application()
def fixture(environ,start_response):
    path=environ.get("PATH_INFO","")
    if path.startswith("/fixture/login/"):
        name=path.rstrip("/").split("/")[-1]
        client=APIClient(); client.force_login(users[name]); cookie=client.cookies[settings.SESSION_COOKIE_NAME]
        query=dict(item.split("=",1) for item in environ.get("QUERY_STRING","").split("&") if "=" in item)
        start_response("302 Found",[("Set-Cookie",f"{settings.SESSION_COOKIE_NAME}={cookie.value}; Path=/; HttpOnly; SameSite=Lax"),("Location",f"/{workspace.slug}/radar/{query.get('to','today')}?mode={name}")]); return [b""]
    if path == "/fixture/info/":
        start_response("200 OK",[("Content-Type","application/json")]); return [json.dumps({"workspace_slug":workspace.slug,"objects":objects}).encode()]
    return application(environ,start_response)
print("U1_PHASE05B_BROWSER_READY",flush=True)
make_server("0.0.0.0",8956,fixture).serve_forever()
