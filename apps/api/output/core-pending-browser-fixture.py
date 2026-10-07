"""Disposable C13/C23 acceptance harness, real session/API/commands/PostgreSQL."""
import sys
sys.path.insert(0, "/code")
import json
from uuid import uuid4, UUID
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from rest_framework.test import APIClient
from wsgiref.simple_server import make_server
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import initialize_semantic_model, create_object, create_relation
from plane.radar.commands.actor import Actor
from plane.radar.commands.execution import run_internal
from plane.radar.models import Object, ObjectType, RelationType
from plane.radar.tests.test_core_u1_phase03bc import ticket_type, TICKET_LIFECYCLE
from plane.radar.tests.test_core_u1_phase02 import edit
call_command("migrate", verbosity=0)
user = User.objects.create(email=f"pending-{uuid4().hex[:8]}@fixture.local", username=f"pending-{uuid4().hex[:8]}")
workspace = Workspace.objects.create(name="Core pending browser", slug=f"pending-browser-{uuid4().hex[:8]}", owner=user)
WorkspaceMember.objects.create(workspace=workspace, member=user, role=20, is_active=True)
actor = Actor(actor_type="human", actor_id=user.pk, source="fixture.browser", reason="Core acceptance", correlation_id=uuid4())
ctx = (user, user, user, workspace, workspace, actor)
initialize_semantic_model(actor=actor, workspace=workspace)
selected = ticket_type(ctx, TICKET_LIFECYCLE)
edit(ctx, selected, {"name": "Service tickets", "rules": {**selected.rules, "creation": {"capability": "CreateObject"}, "presentation": {"narrative": "summary", "sections": [{"key": "lifecycle", "label": "Lifecycle", "properties": ["status", "closed_at"]}]}}})
objective_type = ObjectType.objects.get(workspace=workspace, key="objective")
object_namespace = (uuid4().int >> 64) << 64
def configure():
    one = RelationType.objects.create(workspace=workspace, key="ticket_refs", forward_label="references", reverse_label="referenced_by", source_types=["ticket"], target_types=["objective"], allowed_pairs=[["ticket", "objective"]], cardinality="1..1")
    many = RelationType.objects.create(workspace=workspace, key="backlinks_ticket", forward_label="links_ticket", reverse_label="linked_from", source_types=["objective"], target_types=["ticket"], cardinality="0..n")
    objects = [Object.objects.create(id=UUID(int=object_namespace+1000+i), workspace=workspace, object_type=objective_type, title=f"Objective {i:03}", content="<p>Full narrative</p>") for i in range(111)]
    return one, many, objects
one, many, candidates = run_internal(actor=actor, workspace=workspace, name="AcceptanceSchemaAndVolume", operation=configure)
existing = create_object(actor=actor, workspace=workspace, object_type=selected.pk, title="Existing ticket", properties={"summary": "Narrative from metadata"})
create_relation(actor=actor,workspace=workspace,relation_type_id=one.pk,source_id=existing.pk,target_id=candidates[0].pk)
for obj in candidates[:55]:
    create_relation(actor=actor,workspace=workspace,relation_type_id=many.pk,source_id=obj.pk,target_id=existing.pk)
settings.ALLOWED_HOSTS=["localhost","127.0.0.1","host.docker.internal"]
settings.SESSION_COOKIE_SECURE=False
application=get_wsgi_application()
def fixture(environ,start_response):
    if environ.get("PATH_INFO", "").startswith("/fixture/login/"):
        client=APIClient(); client.force_login(user); cookie=client.cookies[settings.SESSION_COOKIE_NAME]
        start_response("302 Found",[("Set-Cookie",f"{settings.SESSION_COOKIE_NAME}={cookie.value}; Path=/; HttpOnly; SameSite=Lax"),("Location",f"/{workspace.slug}/radar/type-ticket/")]); return [b""]
    if environ.get("PATH_INFO") == "/fixture/info/":
        start_response("200 OK",[("Content-Type","application/json")]); return [json.dumps({"workspace_slug":workspace.slug,"existing":str(existing.pk),"remote":str(candidates[-1].pk),"type":str(selected.pk),"one":str(one.pk)}).encode()]
    return application(environ,start_response)
print("CORE_PENDING_BROWSER_READY",flush=True)
make_server("0.0.0.0",8957,fixture).serve_forever()
