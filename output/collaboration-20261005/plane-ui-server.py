"""Disposable browser fixture. Product APIs, session auth and database remain real."""
import json
import sys
sys.path.insert(0, "/code")
from uuid import uuid4

import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from rest_framework.test import APIClient
from wsgiref.simple_server import make_server
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import create_object, initialize_object_types
from plane.radar.commands.actor import Actor

call_command("migrate", verbosity=0)
users = {}
for name in ("author", "member", "admin", "guest", "outsider"):
    users[name], _ = User.objects.get_or_create(email=f"collaboration-{name}@plane.local",
        defaults={"username": f"collaboration-{name}", "display_name": name.title()})
workspace, _ = Workspace.objects.get_or_create(slug="collaboration-browser",
    defaults={"name": "Isolated collaboration", "owner": users["admin"]})
for name, role in [("author", 15), ("member", 15), ("admin", 20), ("guest", 5)]:
    WorkspaceMember.objects.update_or_create(workspace=workspace, member=users[name], defaults={"role": role, "is_active": True})
actor = Actor(actor_type="human", actor_id=users["author"].pk, source="fixture.browser", reason="Provision Object", correlation_id=uuid4())
kind = next(t for t in initialize_object_types(actor=actor, workspace=workspace) if t.key == "objective")
obj = create_object(actor=actor, workspace=workspace, object_type=kind.pk, title="Implantar Governança de IA")
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
        return [json.dumps({"object_id": str(obj.pk), "workspace_slug": workspace.slug}).encode()]
    return application(environ, start_response)


print("COLLABORATION_BROWSER_READY", flush=True)
make_server("0.0.0.0", 8941, fixture).serve_forever()
