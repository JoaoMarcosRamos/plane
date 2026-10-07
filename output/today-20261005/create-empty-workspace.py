import sys
sys.path.insert(0, "/code")
import django
django.setup()
from plane.db.models import User, Workspace, WorkspaceMember
user = User.objects.get(email="today-browser@plane.local")
workspace = Workspace.objects.create(slug="today-browser-empty", name="Empty Today fixture", owner=user)
WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
print("EMPTY_WORKSPACE_READY", flush=True)
