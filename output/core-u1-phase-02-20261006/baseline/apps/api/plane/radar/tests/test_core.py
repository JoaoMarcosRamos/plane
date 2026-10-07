from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from plane.db.models import User, Workspace, WorkspaceMember
from plane.radar.commands import initialize_object_types, create_object, update_object
from plane.radar.models import Object, ObjectType
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def objective(context):
    *_, workspace, other, actor = context
    return next(item for item in initialize_object_types(actor=actor, workspace=workspace) if item.key == "objective")


def create(context, **kwargs):
    user, second, outsider, workspace, other, actor = context
    return create_object(
        actor=actor,
        workspace=workspace,
        object_type=objective(context).pk,
        title="Implantar Governança de IA",
        **kwargs,
    )


def test_system_types_idempotent_and_scoped(context):
    user, second, outsider, workspace, other, actor = context
    first = initialize_object_types(actor=actor, workspace=workspace)
    again = initialize_object_types(actor=actor, workspace=workspace)
    assert {item.key for item in first} == {
        "objective",
        "project",
        "decision",
        "action",
        "risk",
        "person",
        "document",
        "case",
        "management_item",
        "indicator",
        "commitment",
    }
    assert {item.pk for item in first} == {item.pk for item in again}
    assert all(item.is_system and item.is_active and item.workspace_id == workspace.pk for item in first)
    assert all(item.created_by_id == user.pk and item.updated_by_id == user.pk for item in first)
    assert not ObjectType.objects.filter(workspace=other).exists()


def test_type_uniqueness_and_deleted_behavior(context):
    selected = objective(context)
    with pytest.raises(IntegrityError), transaction.atomic():
        fixture_write(
            lambda: ObjectType.objects.create(workspace=selected.workspace, key="objective", name="Duplicate")
        )
    fixture_write(lambda: ObjectType.all_objects.filter(pk=selected.pk).update(deleted_at=timezone.now()))
    assert not ObjectType.objects.filter(pk=selected.pk).exists()
    replacement = objective(context)
    assert replacement.pk != selected.pk
    assert ObjectType.all_objects.filter(workspace=selected.workspace, key="objective").count() == 2


def test_type_key_can_exist_in_different_workspace(context):
    selected = objective(context)
    other = context[4]
    fixture_write(lambda: ObjectType.objects.create(workspace=other, key=selected.key, name="Other Objective"))
    assert ObjectType.objects.filter(key="objective").count() == 2


def test_create_and_update_explicit_actor_preserves_creator(context):
    user, second, outsider, workspace, other, actor = context
    result = create(context, content="<p>Context</p>")
    assert result.version == 1
    assert result.created_by_id == user.pk == result.updated_by_id
    assert result.workspace_id == workspace.pk and result.object_type.key == "objective"
    # No request or thread-local user exists here; a second explicit actor updates.
    updated = update_object(
        actor=replace(actor, actor_id=second.pk),
        workspace=workspace,
        object_id=result.pk,
        changes={"title": "Implantar Governança de IA na C3"},
    )
    updated.refresh_from_db()
    assert updated.title == "Implantar Governança de IA na C3"
    assert updated.version == 2 and updated.created_by_id == user.pk and updated.updated_by_id == second.pk
    assert updated.content == "<p>Context</p>"
    with pytest.raises(PermissionDenied):
        updated.save()  # Raw ORM writes cannot erase the author or bypass provenance.
    updated.refresh_from_db()
    assert updated.created_by_id == user.pk


def test_stale_instance_updates_increment_database_version(context):
    result = create(context)
    workspace, actor = context[3], context[5]
    for title in ["First", "Second"]:
        update_object(actor=actor, workspace=workspace, object_id=result.pk, changes={"title": title})
    result.refresh_from_db()
    assert result.version == 3 and result.title == "Second"


@pytest.mark.parametrize("field", ["created_by", "updated_by", "workspace", "version", "deleted_at"])
def test_command_rejects_immutable_fields(context, field):
    result = create(context)
    with pytest.raises(ValidationError):
        update_object(actor=context[5], workspace=context[3], object_id=result.pk, changes={field: str(uuid4())})
    result.refresh_from_db()
    assert result.version == 1


def test_cross_workspace_object_and_type_denied(context):
    user, second, outsider, workspace, other, actor = context
    result = create(context)
    WorkspaceMember.objects.create(workspace=other, member=user, role=15)
    foreign_type = next(
        item for item in initialize_object_types(actor=actor, workspace=other) if item.key == "objective"
    )
    with pytest.raises(ValidationError):
        create_object(actor=actor, workspace=workspace, object_type=foreign_type.pk, title="Cross tenant")
    with pytest.raises(ValidationError):
        update_object(actor=actor, workspace=workspace, object_id=result.pk, changes={"object_type": foreign_type.pk})
    with pytest.raises(NotFound):
        update_object(actor=actor, workspace=other, object_id=result.pk, changes={"title": "Cross tenant"})
    assert Object.objects.count() == 1


@pytest.mark.parametrize(
    "state", ["nonmember", "inactive_membership", "guest", "inactive_user", "agent", "system", "integration"]
)
def test_permission_enforced_inside_commands(context, state):
    user, second, outsider, workspace, other, actor = context
    type_id = objective(context).pk
    if state == "nonmember":
        actor = replace(actor, actor_id=outsider.pk)
    elif state == "inactive_membership":
        WorkspaceMember.objects.filter(workspace=workspace, member=user).update(is_active=False)
    elif state == "guest":
        WorkspaceMember.objects.filter(workspace=workspace, member=user).update(role=5)
    elif state == "inactive_user":
        User.objects.filter(pk=user.pk).update(is_active=False)
    else:
        actor = replace(actor, actor_type=state)
    with pytest.raises(PermissionDenied):
        create_object(actor=actor, workspace=workspace, object_type=type_id, title="Denied")
    assert Object.objects.count() == 0


def test_inactive_and_deleted_types_rejected(context):
    selected = objective(context)
    for changes in [{"is_active": False}, {"is_active": True, "deleted_at": timezone.now()}]:
        fixture_write(lambda: ObjectType.all_objects.filter(pk=selected.pk).update(**changes))
        with pytest.raises(ValidationError):
            create_object(actor=context[5], workspace=context[3], object_type=selected.pk, title="Denied")


def test_create_rolls_back_lazy_initialization_on_failure(context):
    with pytest.raises(ValidationError):
        create_object(actor=context[5], workspace=context[3], object_type=uuid4(), title="Invalid type")
    assert ObjectType.objects.count() == Object.objects.count() == 0


def test_update_is_atomic_on_storage_failure(context):
    result = create(context)
    with patch.object(Object, "save", side_effect=IntegrityError("write failed")), pytest.raises(IntegrityError):
        update_object(actor=context[5], workspace=context[3], object_id=result.pk, changes={"title": "Lost"})
    result.refresh_from_db()
    assert result.version == 1 and result.title == "Implantar Governança de IA"


@pytest.mark.parametrize("title", ["", "   ", "x" * 256, None])
def test_command_validates_title(context, title):
    with pytest.raises(ValidationError):
        create_object(actor=context[5], workspace=context[3], object_type=objective(context).pk, title=title)


def test_html_is_sanitized(context):
    result = create(context, content='<p>Safe</p><script>alert(1)</script><img src="x" onerror="alert(2)">')
    assert "<script" not in result.content and "onerror" not in result.content
    assert "<p>Safe</p>" in result.content


def test_delete_blocked_and_deleted_objects_hidden(context):
    result = create(context)
    for operation in [result.delete, Object.objects.all().delete, Object.all_objects.all().delete]:
        with pytest.raises(NotImplementedError):
            operation()
    fixture_write(lambda: Object.all_objects.filter(pk=result.pk).update(deleted_at=timezone.now()))
    assert not Object.objects.filter(pk=result.pk).exists()
    with pytest.raises(NotFound):
        update_object(actor=context[5], workspace=context[3], object_id=result.pk, changes={"title": "Deleted"})


def url(context, suffix="objects/"):
    return f"/api/workspaces/{context[3].slug}/radar/{suffix}"


def test_api_member_create_update_list_retrieve(client, context):
    types = client.get(url(context, "object-types/"))
    assert types.status_code == 200
    selected = next(item for item in types.data if item["key"] == "objective")
    response = client.post(
        url(context), {"title": "Implantar Governança de IA", "object_type": selected["id"]}, format="json"
    )
    assert response.status_code == 201
    detail_url = url(context, f"objects/{response.data['id']}/")
    assert response.data["version"] == 1 and str(response.data["created_by"]) == str(context[0].pk)
    update = client.patch(detail_url, {"title": "Implantar Governança de IA na C3"}, format="json")
    assert update.status_code == 200 and update.data["version"] == 2
    assert update.data["created_by"] == response.data["created_by"] == update.data["updated_by"]
    assert client.get(detail_url).data["title"] == "Implantar Governança de IA na C3"
    assert len(client.get(url(context)).data) == 1


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("get", "object-types/"),
        ("get", "objects/"),
        ("post", "objects/"),
        ("get", "objects/{id}/"),
        ("patch", "objects/{id}/"),
    ],
)
@pytest.mark.parametrize("access", ["anonymous", "nonmember"])
def test_api_unauthorized(client, context, method, suffix, access):
    result = create(context)
    client.force_authenticate(user=None if access == "anonymous" else context[2])
    response = getattr(client, method)(url(context, suffix.replace("{id}", str(result.pk))))
    assert response.status_code in [401, 403]


def test_api_guest_can_read_but_not_write(client, context):
    WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(role=5)
    assert client.get(url(context, "object-types/")).status_code == 200
    assert client.get(url(context)).status_code == 200
    selected = objective(context)
    assert (
        client.post(url(context), {"object_type": str(selected.pk), "title": "Denied"}, format="json").status_code
        == 403
    )


def test_api_cross_workspace_and_read_only_payload(client, context):
    result = create(context)
    WorkspaceMember.objects.create(workspace=context[4], member=context[0], role=15)
    foreign_url = f"/api/workspaces/{context[4].slug}/radar/objects/{result.pk}/"
    assert client.get(foreign_url).status_code == 404
    assert client.patch(foreign_url, {"title": "Denied"}, format="json").status_code == 404
    assert client.get(f"/api/workspaces/{context[4].slug}/radar/objects/").data == []
    assert (
        client.patch(
            url(context, f"objects/{result.pk}/"), {"created_by": str(context[1].pk)}, format="json"
        ).status_code
        == 400
    )


def test_api_session_authentication(context):
    # Exercise the same cookie session backend used by the browser, not force_authenticate.
    api = APIClient()
    api.force_login(context[0])
    assert api.get(url(context)).status_code == 200


@pytest.mark.django_db(transaction=True)
def test_concurrent_updates_serialize_versions(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections

    result = create(context)
    barrier = Barrier(2)

    def write(title):
        close_old_connections()
        try:
            workspace = Workspace.objects.get(pk=context[3].pk)
            barrier.wait(timeout=10)
            return update_object(
                actor=context[5], workspace=workspace, object_id=result.pk, changes={"title": title}
            ).version
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(executor.map(write, ["Concurrent A", "Concurrent B"]))
    result.refresh_from_db()
    assert sorted(versions) == [2, 3]
    assert result.version == 3 and result.created_by_id == context[0].pk


@pytest.mark.django_db(transaction=True)
def test_concurrent_initialization_is_idempotent(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections

    barrier = Barrier(2)

    def initialize(_):
        close_old_connections()
        try:
            workspace = Workspace.objects.get(pk=context[3].pk)
            barrier.wait(timeout=10)
            return {item.pk for item in initialize_object_types(actor=context[5], workspace=workspace)}
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(initialize, [1, 2])
    assert first == second and len(first) == 11
    assert ObjectType.objects.filter(workspace=context[3]).count() == 11
