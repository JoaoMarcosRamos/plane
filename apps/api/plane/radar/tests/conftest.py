from uuid import uuid4
import json
import re
import pytest
from rest_framework.test import APIClient
from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands.actor import Actor


class SnapshotClient(APIClient):
    """Existing endpoint tests explicitly supply a fresh snapshot and an intention key."""

    def generic(self, method, path, data="", content_type="application/octet-stream", secure=False, **extra):
        if method in {"POST", "PUT", "PATCH", "DELETE"} and "/radar/" in path:
            from plane.radar.models import Object, Relation

            ids = set()
            match = re.search(r"/objects/([0-9a-f-]{36})/", path)
            if match:
                ids.add(match.group(1))
            relation = re.search(r"/relations/([0-9a-f-]{36})/", path)
            if relation:
                edge = Relation.all_objects.filter(pk=relation.group(1)).first()
                if edge:
                    ids.update([str(edge.source_id), str(edge.target_id)])
            try:
                payload = json.loads(data) if data else {}
            except (TypeError, ValueError):
                payload = {}
            if isinstance(payload, dict):
                ids.update(str(payload[key]) for key in ("source", "target") if key in payload)
            versions = {str(obj.pk): obj.version for obj in Object.objects.filter(pk__in=ids)}
            extra.setdefault("HTTP_X_RADAR_EXPECTED_VERSIONS", json.dumps(versions))
            extra.setdefault("HTTP_IDEMPOTENCY_KEY", str(uuid4()))
            from plane.radar.workspace_schema import schema_revision
            from plane.db.models import Workspace

            match_workspace = re.search(r"/workspaces/([^/]+)/", path)
            if match_workspace:
                workspace = Workspace.objects.filter(slug=match_workspace.group(1)).first()
                if workspace:
                    extra.setdefault("HTTP_X_RADAR_EXPECTED_SCHEMA_REVISION", str(schema_revision(workspace)))
        return super().generic(method, path, data, content_type, secure, **extra)


@pytest.fixture
def context():
    user = User.objects.create(email="radar-unit@plane.local", username="radar-unit")
    second = User.objects.create(email="radar-second@plane.local", username="radar-second")
    outsider = User.objects.create(email="radar-outsider-unit@plane.local", username="radar-outsider-unit")
    workspace = Workspace.objects.create(name="RADAR", slug="radar-unit", owner=user)
    other = Workspace.objects.create(name="Other", slug="radar-unit-other", owner=outsider)
    for person in [user, second]:
        WorkspaceMember.objects.create(workspace=workspace, member=person, role=15)
    actor = Actor(actor_type="human", actor_id=user.pk, reason="Test", source="pytest", correlation_id=uuid4())
    return user, second, outsider, workspace, other, actor


@pytest.fixture
def client(context):
    api = SnapshotClient()
    api.force_authenticate(user=context[0])
    return api
