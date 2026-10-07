from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4
import hashlib
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from plane.db.models import WorkspaceMember
from plane.radar.collaboration import MAX_ATTACHMENT_SIZE, AttachmentUnavailable, prepare_upload
from plane.radar.commands import create_object, execute_command, initialize_object_types
from plane.radar.models import Object, ObjectComment, ObjectAttachment, AttachmentPayload, Provenance, CommandExecution
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.fixture
def obj(context):
    kind = next(t for t in initialize_object_types(actor=context[5], workspace=context[3]) if t.key == "objective")
    return create_object(actor=context[5], workspace=context[3], object_type=kind.pk, title="Governança IA")


def envelope(context, obj, name="AddComment", payload=None, key=None):
    obj.refresh_from_db()
    return {
        "command_name": name,
        "command_version": 1,
        "workspace_id": str(context[3].pk),
        "reason": "Test",
        "assertion": {"kind": "asserted"},
        "idempotency_key": key or str(uuid4()),
        "expected_versions": {str(obj.pk): obj.version},
        "input": payload or {"object_id": str(obj.pk), "body": "Revisar licenciamento"},
    }


def command(context, obj, name="AddComment", payload=None, actor=None):
    return execute_command(
        actor=actor or context[5], workspace=context[3], envelope=envelope(context, obj, name, payload)
    )


def url(context, obj):
    return f"/api/workspaces/{context[3].slug}/radar/objects/{obj.pk}"


def upload(client, context, obj, data=b"evidence", key=None, filename="evidence.txt"):
    return client.post(
        url(context, obj) + "/attachments/",
        {"file": SimpleUploadedFile(filename, data)},
        format="multipart",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def test_comment_lifecycle_authorship_revision_activity_and_replay(context, client, obj):
    intent = envelope(context, obj)
    first = execute_command(actor=context[5], workspace=context[3], envelope=intent)
    assert execute_command(actor=context[5], workspace=context[3], envelope=intent) == first
    item = ObjectComment.objects.get(pk=first["data"]["item_id"])
    assert item.created_by_id == context[0].pk and item.body == "Revisar licenciamento"
    original_provenance = item.created_provenance_id
    payload = {"object_id": str(obj.pk), "item_id": str(item.pk), "expected_revision": 1, "body": "Contexto atualizado"}
    assert command(context, obj, "EditComment", payload)["data"]["revision"] == 2
    item.refresh_from_db()
    assert item.created_provenance_id == original_provenance != item.last_provenance_id
    stale = client.post(
        f"/api/workspaces/{context[3].slug}/radar/commands/",
        envelope(context, obj, "EditComment", payload),
        format="json",
    )
    assert stale.status_code == 409
    payload.pop("body")
    payload["expected_revision"] = 2
    command(context, obj, "DeleteComment", payload)
    snapshot = client.get(url(context, obj) + "/collaboration/").json()
    assert snapshot["comments"] == []
    assert {a["command_name"] for a in snapshot["activity"]} >= {
        "AddComment",
        "EditComment",
        "DeleteComment",
        "CreateObject",
    }
    audit = client.get(url(context, obj) + "/provenance/").json()
    assert {record["command_name"] for record in audit} >= {"AddComment", "EditComment", "DeleteComment"}
    assert ObjectComment.all_objects.get(pk=item.pk).deleted_at is not None
    assert Provenance.objects.get(pk=original_provenance).changes[0]["after"]["body"] == "Revisar licenciamento"
    obj.refresh_from_db()
    assert obj.version == 1  # Discussion never invalidates semantic approvals.


@pytest.mark.parametrize("name", ["EditComment", "DeleteComment", "RenameAttachment", "DeleteAttachment"])
def test_other_member_cannot_edit_or_delete(context, client, obj, name):
    if name.endswith("Comment"):
        pk = command(context, obj)["data"]["item_id"]
    else:
        pk = upload(client, context, obj).json()["data"]["item_id"]
    payload = {"object_id": str(obj.pk), "item_id": pk, "expected_revision": 1}
    if name == "EditComment":
        payload["body"] = "Not mine"
    if name == "RenameAttachment":
        payload["filename"] = "not-mine.txt"
    with pytest.raises(PermissionDenied):
        command(context, obj, name, payload, actor=replace(context[5], actor_id=context[1].pk))
    WorkspaceMember.objects.filter(workspace=context[3], member=context[1]).update(role=20)
    if name.startswith("Delete"):
        command(context, obj, name, payload, actor=replace(context[5], actor_id=context[1].pk))
        record = Provenance.objects.filter(command_name=name).get()
        assert record.actor_id == context[1].pk and record.changes[0]["before"]["created_by_id"] == str(context[0].pk)
    else:
        with pytest.raises(PermissionDenied):
            command(context, obj, name, payload, actor=replace(context[5], actor_id=context[1].pk))


def test_attachment_real_bytes_private_download_rename_delete_and_replay(context, client, obj):
    key = str(uuid4())
    response = upload(client, context, obj, key=key)
    assert response.status_code == 200
    assert upload(client, context, obj, key=key).json() == response.json()
    pk = response.json()["data"]["item_id"]
    item = ObjectAttachment.objects.get(pk=pk)
    assert item.created_by_id == context[0].pk and item.sha256 == hashlib.sha256(b"evidence").hexdigest()
    assert AttachmentPayload.objects.count() == 1
    persisted_input = CommandExecution.objects.get(pk=response.json()["command_id"]).envelope["input"]
    assert set(persisted_input) == {"object_id", "filename", "size", "sha256"}
    download = url(context, obj) + f"/attachments/{pk}/download/"
    result = client.get(download)
    assert b"".join(result.streaming_content) == b"evidence"
    assert result["Content-Type"] == "application/octet-stream" and result["Cache-Control"] == "private, no-store"
    assert "attachment;" in result["Content-Disposition"]
    payload = {"object_id": str(obj.pk), "item_id": pk, "expected_revision": 1, "filename": "renamed.txt"}
    command(context, obj, "RenameAttachment", payload)
    item.refresh_from_db()
    assert item.filename == "renamed.txt" and item.revision == 2
    payload.pop("filename")
    payload["expected_revision"] = 2
    command(context, obj, "DeleteAttachment", payload)
    assert client.get(download).status_code == 404
    assert client.get(url(context, obj) + "/collaboration/").json()["attachments"] == []
    assert AttachmentPayload.objects.count() == 1  # Audit/retention survives logical removal.


@pytest.mark.parametrize("state", ["anonymous", "outsider", "inactive_membership", "inactive_user", "guest"])
def test_read_write_and_download_membership(context, client, obj, state):
    pk = upload(client, context, obj).json()["data"]["item_id"]
    if state == "anonymous":
        client.force_authenticate(user=None)
    elif state == "outsider":
        client.force_authenticate(user=context[2])
    elif state == "inactive_membership":
        WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(is_active=False)
    elif state == "inactive_user":
        context[0].is_active = False
        context[0].save()
    else:
        WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(role=5)
    denied_status = 401 if state == "anonymous" else 403
    for endpoint in ["/collaboration/", f"/attachments/{pk}/download/"]:
        assert client.get(url(context, obj) + endpoint).status_code == (200 if state == "guest" else denied_status)
    assert upload(client, context, obj).status_code == denied_status
    assert (
        client.post(
            f"/api/workspaces/{context[3].slug}/radar/commands/", envelope(context, obj), format="json"
        ).status_code
        == denied_status
    )


def test_cross_workspace_and_cross_object_items_are_not_accessible(context, client, obj):
    pk = upload(client, context, obj).json()["data"]["item_id"]
    WorkspaceMember.objects.create(workspace=context[4], member=context[0], role=15)
    other_url = f"/api/workspaces/{context[4].slug}/radar/objects/{obj.pk}"
    assert client.get(other_url + "/collaboration/").status_code == 404
    assert client.get(other_url + f"/attachments/{pk}/download/").status_code == 404
    foreign = fixture_write(
        lambda: Object.objects.create(workspace=context[4], object_type=obj.object_type, title="foreign")
    )
    payload = {"object_id": str(foreign.pk), "item_id": pk, "expected_revision": 1}
    with pytest.raises(Exception) as exc:
        command(context, obj, "DeleteAttachment", payload)
    assert getattr(exc.value, "status_code", None) == 404
    sibling = create_object(actor=context[5], workspace=context[3], object_type=obj.object_type_id, title="Sibling")
    payload["object_id"] = str(sibling.pk)
    intent = envelope(context, sibling, "DeleteAttachment", payload)
    assert client.post(f"/api/workspaces/{context[3].slug}/radar/commands/", intent, format="json").status_code == 404
    assert client.get(url(context, sibling) + f"/attachments/{pk}/download/").status_code == 404


@pytest.mark.parametrize("data", [b"", b"x" * (MAX_ATTACHMENT_SIZE + 1)], ids=["empty", "oversized"])
def test_upload_size_rejected_without_any_persistence(context, client, obj, data):
    before = (ObjectAttachment.objects.count(), CommandExecution.objects.count(), Provenance.objects.count())
    assert upload(client, context, obj, data=data).status_code == 400
    assert before == (ObjectAttachment.objects.count(), CommandExecution.objects.count(), Provenance.objects.count())


def test_upload_read_and_database_failures_are_atomic(context, client, obj):
    file = io.BytesIO(b"x")
    file.name = "test.txt"
    with patch.object(file, "read", side_effect=OSError("Interrupted")), pytest.raises(AttachmentUnavailable):
        prepare_upload(file)
    before = (CommandExecution.objects.count(), Provenance.objects.count())
    with patch.object(AttachmentPayload, "save", side_effect=DatabaseError("Storage full")):
        response = upload(client, context, obj)
    assert response.status_code == 503
    assert ObjectAttachment.objects.count() == AttachmentPayload.objects.count() == 0
    assert before == (CommandExecution.objects.count(), Provenance.objects.count())
    assert upload(client, context, obj).status_code == 200


def test_upload_strict_contract_conflict_and_revocation(context, client, obj):
    endpoint = url(context, obj) + "/attachments/"
    assert client.post(endpoint, {}, format="multipart").status_code == 400
    assert (
        client.post(
            endpoint, {"file": SimpleUploadedFile("a.txt", b"x"), "actor_id": str(context[1].pk)}, format="multipart"
        ).status_code
        == 400
    )
    assert (
        client.post(
            endpoint,
            {"file": [SimpleUploadedFile("a.txt", b"x"), SimpleUploadedFile("b.txt", b"y")]},
            format="multipart",
        ).status_code
        == 400
    )
    raw = APIClient()
    raw.force_authenticate(user=context[0])
    assert raw.post(endpoint, {"file": SimpleUploadedFile("a.txt", b"x")}, format="multipart").status_code == 400
    assert upload(client, context, obj, key="one").status_code == 200
    assert upload(client, context, obj, key="one", data=b"different").status_code == 409
    assert (
        client.post(
            endpoint,
            {"file": SimpleUploadedFile("a.txt", b"x")},
            format="multipart",
            HTTP_IDEMPOTENCY_KEY="stale",
            HTTP_X_RADAR_EXPECTED_VERSIONS=json.dumps({str(obj.pk): 9}),
        ).status_code
        == 409
    )
    WorkspaceMember.objects.filter(workspace=context[3], member=context[0]).update(is_active=False)
    assert upload(client, context, obj, key="one").status_code == 403


def test_commands_reject_forged_author_empty_text_and_missing_upload(context, obj):
    for payload in [
        {"object_id": str(obj.pk), "body": "   "},
        {"object_id": str(obj.pk), "body": "x", "created_by": str(context[1].pk)},
    ]:
        with pytest.raises(ValidationError):
            command(context, obj, payload=payload)
    with pytest.raises(ValidationError):
        command(
            context,
            obj,
            "AddAttachment",
            {"object_id": str(obj.pk), "filename": "x.txt", "size": 1, "sha256": hashlib.sha256(b"x").hexdigest()},
        )
    with pytest.raises(PermissionDenied):
        command(context, obj, actor=replace(context[5], actor_type="system"))
    with pytest.raises(PermissionDenied):
        ObjectComment.objects.create(workspace=context[3], object=obj, body="bypass")


@pytest.mark.parametrize("filename", ["../a.txt", "a\\b.txt", "bad\n.txt", "..", " "])
def test_filename_validation(context, obj, filename):
    with pytest.raises(ValidationError):
        command(
            context,
            obj,
            "AddAttachment",
            {"object_id": str(obj.pk), "filename": filename, "size": 1, "sha256": hashlib.sha256(b"x").hexdigest()},
        )


def test_deleted_object_blocks_discussion_upload_download(context, client, obj):
    pk = upload(client, context, obj).json()["data"]["item_id"]
    fixture_write(lambda: Object.all_objects.filter(pk=obj.pk).update(deleted_at=timezone.now()))
    assert client.get(url(context, obj) + "/collaboration/").status_code == 404
    assert upload(client, context, obj).status_code == 404
    assert client.get(url(context, obj) + f"/attachments/{pk}/download/").status_code == 404


def test_activity_pagination_is_scoped_and_reads_do_not_mutate(context, client, obj):
    for i in range(51):
        command(context, obj, payload={"object_id": str(obj.pk), "body": f"comment {i}"})
    before = (Provenance.objects.count(), CommandExecution.objects.count())
    first = client.get(url(context, obj) + "/collaboration/").json()
    second = client.get(url(context, obj) + "/collaboration/", {"activity_before": first["activity_next"]}).json()
    assert len(first["activity"]) == 50 and second["activity_next"] is None
    assert not set(a["id"] for a in first["activity"]) & set(a["id"] for a in second["activity"])
    assert before == (Provenance.objects.count(), CommandExecution.objects.count())
    assert client.get(url(context, obj) + "/collaboration/", {"activity_before": str(uuid4())}).status_code == 404


def test_bulk_writes_and_payload_replacement_cannot_bypass_commands(context, client, obj):
    pk = upload(client, context, obj).json()["data"]["item_id"]
    comment_id = command(context, obj)["data"]["item_id"]
    with pytest.raises(PermissionDenied):
        ObjectComment.objects.filter(pk=comment_id).update(body="bypass")
    with pytest.raises(PermissionDenied):
        ObjectAttachment.objects.filter(pk=pk).update(filename="bypass")
    with pytest.raises(PermissionDenied):
        ObjectComment.objects.bulk_create([ObjectComment(workspace=context[3], object=obj, body="bypass")])
    with pytest.raises(PermissionDenied):
        AttachmentPayload.objects.filter(pk=pk).update(data=b"bypass")
    with pytest.raises(PermissionDenied):
        AttachmentPayload.objects.filter(pk=pk).delete()
    payload = AttachmentPayload.objects.get(pk=pk)
    with pytest.raises(PermissionDenied):
        payload.save()


def test_storage_integrity_failure_never_serves_corrupted_bytes(context, client, obj):
    from django.db import connection

    pk = upload(client, context, obj).json()["data"]["item_id"]
    # Simulate external storage corruption, deliberately outside product's guarded writers.
    with connection.cursor() as cursor:
        cursor.execute("UPDATE radar_attachment_payloads SET data = %s WHERE attachment_id = %s", [b"broken", pk])
    response = client.get(url(context, obj) + f"/attachments/{pk}/download/")
    assert response.status_code == 400 and response.json()["code"] == "attachment_integrity_failed"


@pytest.mark.django_db(transaction=True)
def test_concurrent_comment_edit_checks_child_revision(context, obj):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections
    from plane.radar.commands.execution import CommandConflict

    pk = command(context, obj)["data"]["item_id"]
    barrier = Barrier(2)
    intents = [
        envelope(
            context,
            obj,
            "EditComment",
            {
                "object_id": str(obj.pk),
                "item_id": pk,
                "expected_revision": 1,
                "body": text,
            },
        )
        for text in ["First", "Second"]
    ]

    def write(intent):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            execute_command(actor=context[5], workspace=context[3], envelope=intent)
            return "executed"
        except CommandConflict:
            return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write, intents)) == ["conflict", "executed"]
    assert ObjectComment.objects.get(pk=pk).revision == 2
    assert Provenance.objects.filter(command_name="EditComment").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_upload_intention_commits_one_payload(context, obj):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections, connections

    upload = prepare_upload(SimpleUploadedFile("proof.txt", b"proof"))
    intent = envelope(
        context, obj, "AddAttachment", {"object_id": str(obj.pk), **upload.metadata}, key="parallel-upload"
    )
    barrier = Barrier(2)

    def write(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return execute_command(actor=context[5], workspace=context[3], envelope=intent, upload=upload)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(write, [1, 2])
    assert first == second
    assert ObjectAttachment.objects.count() == AttachmentPayload.objects.count() == 1
    assert Provenance.objects.filter(command_name="AddAttachment").count() == 1
