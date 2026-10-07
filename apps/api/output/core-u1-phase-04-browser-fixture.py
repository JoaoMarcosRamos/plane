"""Disposable phase 4 browser fixture. Product APIs, session auth, commands and PostgreSQL stay real."""

import json
import sys
from uuid import uuid4

sys.path.insert(0, "/code")
import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from rest_framework.test import APIClient
from wsgiref.simple_server import make_server
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import configure_person_identity, create_object, execute_command, initialize_semantic_model
from plane.radar.commands.actor import Actor
from plane.radar.commands.schema import preview_upgrade, upgrade_schema
from plane.radar.models import Object, ObjectType, RelationType
from plane.radar.ontology.package import package_definitions
from plane.radar.workspace_schema import schema_revision

call_command("migrate", verbosity=0)
users = {}
for name in ("author", "reviewer", "admin", "guest"):
    users[name], _ = User.objects.get_or_create(
        email=f"u1-phase04-{name}@plane.local",
        defaults={"username": f"u1-phase04-{name}", "display_name": name.title()},
    )
workspace, created = Workspace.objects.get_or_create(
    slug="u1-phase04-browser", defaults={"name": "U1 phase 04 browser", "owner": users["admin"]}
)
for name, role in [("author", 15), ("reviewer", 15), ("admin", 20), ("guest", 5)]:
    WorkspaceMember.objects.update_or_create(
        workspace=workspace, member=users[name], defaults={"role": role, "is_active": True}
    )


def actor(name, reason="Provision browser fixture"):
    return Actor(actor_type="human", actor_id=users[name].pk, source="fixture.browser", reason=reason, correlation_id=uuid4())


objects = {}
if created or not ObjectType.objects.filter(workspace=workspace, key="ticket").exists():
    initialize_semantic_model(actor=actor("admin"), workspace=workspace)
    # A workspace type unknown to Python, added by the audited administrative upgrade path.
    candidate = package_definitions()
    candidate["types:ticket"] = {
        "name": "Ticket",
        "description": "",
        "icon": "",
        "is_active": True,
        "rules": {
            "invariants": [],
            "creation": {"capability": "CreateObject"},
            "lifecycle": {
                "property": "status",
                "initial": "open",
                "transitions": [
                    {"from": ["open"], "to": "working"},
                    {"from": ["working"], "to": "closed", "stamp": "closed_at"},
                ],
            },
            "presentation": {
                "narrative": "summary",
                "sections": [{"key": "triage", "label": "Triage", "properties": ["status", "severity", "closed_at"]}],
            },
        },
    }
    for key, value_type, config, required in (
        ("status", "enum", {"choices": ["open", "working", "closed"], "terminal": ["closed"], "default": "open"}, False),
        ("summary", "string", {}, True),
        ("severity", "enum", {"choices": ["low", "high"], "default": "low"}, False),
        ("closed_at", "datetime", {}, False),
    ):
        candidate[f"properties:ticket.{key}"] = {
            "name": key,
            "value_type": value_type,
            "config": config,
            "is_required": required,
            "is_active": True,
        }
    plan = preview_upgrade(
        actor=actor("admin"), workspace=workspace, expected_revision=schema_revision(workspace), definitions=candidate
    )
    upgrade_schema(
        actor=actor("admin"),
        workspace=workspace,
        expected_revision=plan["schema_revision"],
        reviewed_hash=plan["candidate_hash"],
        definitions=candidate,
        version="3.2.0+ticket",
    )


def kind(key):
    return ObjectType.objects.get(workspace=workspace, key=key)


def find_or_create(key, title, **kwargs):
    existing = Object.objects.filter(workspace=workspace, object_type__key=key, title=title).first()
    return existing or create_object(
        actor=actor("author"), workspace=workspace, object_type=kind(key).pk, title=title, **kwargs
    )


risk = find_or_create("risk", "Licensing delay", properties={"description": "Vendor may delay licenses"})
action = find_or_create("action", "Negotiate licenses", properties={"description": "Agree enterprise terms"})
evidence = find_or_create("document", "License assessment", content="<p>Reviewed options and prices</p>")
decision = find_or_create(
    "decision",
    "Adopt enterprise licenses",
    properties={"context": "Sandbox governance", "decision": "Use enterprise licenses", "rationale": "Central control"},
)
approver = find_or_create("person", "Reviewer person")
if not decision.outgoing_relations.filter(relation_type__key="informed_by").exists():
    informed = RelationType.objects.get(workspace=workspace, key="informed_by")
    execute_command(
        actor=actor("author"),
        workspace=workspace,
        envelope={
            "command_name": "LinkObjects",
            "command_version": 1,
            "idempotency_key": str(uuid4()),
            "expected_versions": {str(decision.pk): decision.version, str(evidence.pk): evidence.version},
            "reason": "Provision browser fixture",
            "input": {"source_id": str(decision.pk), "target_id": str(evidence.pk), "relation_type_id": str(informed.pk)},
            "assertion": {"kind": "asserted", "evidence_ids": []},
        },
    )
configure_person_identity(
    actor=actor("admin"), workspace=workspace, user_id=users["reviewer"].pk, person_id=approver.pk, can_approve=True
)
objects = {
    "risk": str(risk.pk),
    "action": str(action.pk),
    "evidence": str(evidence.pk),
    "decision": str(decision.pk),
    "person": str(approver.pk),
}
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
        target = dict(item.split("=", 1) for item in environ.get("QUERY_STRING", "").split("&") if "=" in item)
        location = f"/{workspace.slug}/radar/{target.get('to', 'create')}?mode={name}"
        start_response(
            "302 Found",
            [
                ("Set-Cookie", f"{settings.SESSION_COOKIE_NAME}={cookie.value}; Path=/; HttpOnly; SameSite=Lax"),
                ("Location", location),
            ],
        )
        return [b""]
    if path == "/fixture/info/":
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"workspace_slug": workspace.slug, "objects": objects}).encode()]
    return application(environ, start_response)


print("U1_PHASE04_BROWSER_READY", flush=True)
make_server("0.0.0.0", 8944, fixture).serve_forever()
