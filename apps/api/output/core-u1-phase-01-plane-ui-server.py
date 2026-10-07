"""Disposable browser fixture. Product APIs, session auth and database remain real."""
import json
import sys
sys.path.insert(0, "/code")
from uuid import UUID, uuid4
from dataclasses import replace

import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from rest_framework.test import APIClient
from wsgiref.simple_server import make_server
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import create_object, initialize_object_types, register_actor_grant, execute_command, review_command
from plane.radar.models import CommandExecution
from plane.radar.commands.actor import Actor

call_command("migrate", verbosity=0)
users = {}
for name in ("author", "member", "admin", "guest", "outsider"):
    users[name], _ = User.objects.get_or_create(email=f"u1-phase01-{name}@plane.local",
        defaults={"username": f"u1-phase01-{name}", "display_name": name.title()})
workspace, _ = Workspace.objects.get_or_create(slug="u1-phase01-browser",
    defaults={"name": "U1 phase 01 isolated browser", "owner": users["admin"]})
for name, role in [("author", 15), ("member", 15), ("admin", 20), ("guest", 5)]:
    WorkspaceMember.objects.update_or_create(workspace=workspace, member=users[name], defaults={"role": role, "is_active": True})
actor = Actor(actor_type="human", actor_id=users["author"].pk, source="fixture.browser", reason="Provision Object", correlation_id=uuid4())
kind = next(t for t in initialize_object_types(actor=actor, workspace=workspace) if t.key == "objective")
obj = create_object(actor=actor, workspace=workspace, object_type=kind.pk, title="Implantar Governança de IA")
objects = {"human": str(obj.pk)}
for actor_type in ("agent", "system", "integration"):
    principal = Actor(actor_type=actor_type, actor_id=uuid4(), run_id=uuid4() if actor_type == "agent" else None,
        source="fixture.browser." + actor_type, reason="Create authored browser fixture", correlation_id=uuid4())
    register_actor_grant(actor=replace(actor, actor_id=users["admin"].pk), workspace=workspace,
        actor_type=actor_type, actor_id=principal.actor_id, delegator_id=users["author"].pk,
        commands=["CreateObject"], object_types=["objective"], fields=["*"], requires_approval=False)
    request = {"command_name": "CreateObject", "command_version": 1, "idempotency_key": str(uuid4()),
        "expected_versions": {}, "reason": principal.reason,
        "input": {"object_type_id": str(kind.pk), "title": "U1 " + actor_type + " authorship"},
        "assertion": {"kind": "asserted"}}
    result = execute_command(actor=principal, workspace=workspace, envelope=request)
    if result["status"] == "pending_approval":
        record = CommandExecution.objects.get(pk=result["command_id"])
        vote = review_command(actor=replace(actor, actor_id=users["admin"].pk), workspace=workspace,
            command_id=record.pk, intent_hash=record.intent_hash, approve=True, rationale="Review fixture creation")
        result = execute_command(actor=replace(principal, approval_id=vote.pk), workspace=workspace, envelope=request)
    objects[actor_type] = result["data"]["object"]["id"]
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "host.docker.internal"]
settings.SESSION_COOKIE_SECURE = False
application = get_wsgi_application()


def fixture(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.startswith("/fixture/login/"):
        name = path.rstrip("/").split("/")[-1]
        if name not in users:
            start_response("404 Not Found", [])
            return [b"Unknown fixture user"]
        client = APIClient()
        client.force_login(users[name])
        cookie = client.cookies[settings.SESSION_COOKIE_NAME]
        start_response("302 Found", [("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={cookie.value}; Path=/; HttpOnly; SameSite=Lax"),
            ("Location", f"/{workspace.slug}/radar/objects/{obj.pk}?mode={name}")])
        return [b""]
    if path == "/fixture/info/":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"object_id": str(obj.pk), "workspace_slug": workspace.slug, "objects": objects}).encode()]
    return application(environ, start_response)


print("U1_PHASE01_BROWSER_READY", flush=True)
make_server("0.0.0.0", 8942, fixture).serve_forever()
