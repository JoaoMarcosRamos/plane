"""Test-only HTTP facade on an isolated Compose DB. Never used by product settings."""
import sys
from uuid import uuid4
sys.path.insert(0, "/code")
import django
from django.conf import settings
django.setup()
from django.core.management import call_command
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import initialize_semantic_model, create_object, configure_person_identity, register_actor_grant
from plane.radar.commands.actor import Actor
from plane.radar.commands.runtime_control import bind_runtime_object, issue_runtime_credential
from plane.radar.models import ObjectType
from plane.radar.ontology.schema import load_schema

call_command("migrate", verbosity=0)
user, _ = User.objects.get_or_create(email="risk-review-browser@plane.local", defaults={"username": "risk-review-browser"})
workspace, _ = Workspace.objects.get_or_create(slug="risk-review-browser", defaults={"name": "Risk Review isolated browser", "owner": user})
WorkspaceMember.objects.get_or_create(workspace=workspace, member=user, defaults={"role": 20})
actor = Actor(actor_type="human", actor_id=user.pk, reason="Provision disposable browser fixture", source="pytest.browser", correlation_id=uuid4())
initialize_semantic_model(actor=actor, workspace=workspace)
objects = {}
for key, title, props in [("person", "Test Reviewer", {}), ("risk", "Licenciamento pode atrasar", {"description": "A licença pode atrasar Governança e Sandbox IA"}), ("objective", "Implantar Governança de IA", {"description": "Implantação depende da licença"}), ("project", "Sandbox IA", {"description": "Depende do licenciamento"})]:
    obj = create_object(actor=actor, workspace=workspace, object_type=ObjectType.objects.get(workspace=workspace, key=key).pk, title=title, properties=props)
    bind_runtime_object(actor=actor, workspace=workspace, object_id=obj.pk, external_id=f"{load_schema()['object_types'][key]['prefix']}-20261005-{uuid4().hex[:6].upper()}", context="company:browser")
    objects[key] = obj
configure_person_identity(actor=actor, workspace=workspace, user_id=user.pk, person_id=objects["person"].pk, can_approve=True)
agent = uuid4()
register_actor_grant(actor=actor, workspace=workspace, actor_type="agent", actor_id=agent, delegator_id=user.pk, commands=["LinkObjects", "CreateAction"], object_types=["*"], fields=["*"])
issue_runtime_credential(actor=actor, workspace=workspace, actor_id=agent, context="company:browser", external_author=f"plane:{user.pk}", reviewer_id=user.pk, person_id=objects["person"].pk, channel="plane")
settings.RADAR_AGENT_RUNTIME_URL = "http://host.docker.internal:8935/agent-runtime/v1"
settings.RADAR_AGENT_RUNTIME_TOKEN = "radar-local-integration-test-key-0001"
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "host.docker.internal"]
settings.MIDDLEWARE = [middleware for middleware in settings.MIDDLEWARE if "CSRF" not in middleware and "Csrf" not in middleware]
# Force-authentication belongs only to this disposable WSGI wrapper, never product code.
from django.core.wsgi import get_wsgi_application
from wsgiref.simple_server import make_server, WSGIRequestHandler
application = get_wsgi_application()
from django.core.handlers.wsgi import WSGIHandler
from django.core.handlers.wsgi import WSGIRequest
class FixtureRequest(WSGIRequest):
    def __init__(self, environ):
        super().__init__(environ)
        self._force_auth_user = user
        self._force_auth_token = None
application.request_class = FixtureRequest
print("ISOLATED_REVIEW_SERVER_READY", flush=True)
make_server("0.0.0.0", 8938, application).serve_forever()
