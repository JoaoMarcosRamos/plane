import hashlib
import io
import logging

from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.db.models import WorkspaceMember
from plane.radar.collaboration import AttachmentUnavailable, prepare_upload
from plane.radar.commands import execute_command
from plane.radar.commands.execution import authorize
from plane.radar.commands.access import role_can_write, is_workspace_admin
from plane.radar.active import active_objects
from plane.radar.models import ObjectComment, ObjectAttachment, AttachmentPayload, Provenance
from .views import RadarAPIView


def activity_records(workspace, object_id):
    pk = str(object_id)
    # Includes semantic changes and collaboration children, even after soft deletion.
    return Provenance.objects.filter(workspace=workspace).filter(
        Q(changes__contains=[{"id": pk}])
        | Q(changes__contains=[{"after": {"object_id": pk}}])
        | Q(changes__contains=[{"before": {"object_id": pk}}])
    )


def item_data(item, user_id, can_write, admin):
    result = {
        "id": str(item.pk),
        "revision": item.revision,
        "created_by": str(item.created_by_id) if item.created_by_id else None,
        "author": item.created_by.display_name if item.created_by else "Deleted user",
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "created_provenance_id": item.created_provenance_id,
        "last_provenance_id": item.last_provenance_id,
        "can_edit": can_write and item.created_by_id == user_id,
        "can_delete": can_write and (item.created_by_id == user_id or admin),
    }
    if isinstance(item, ObjectComment):
        result["body"] = item.body
    else:
        result.update(filename=item.filename, size=item.size, sha256=item.sha256)
    return result


class ObjectCollaborationView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        authorize(self.actor("Read Object collaboration"), workspace, "ReadCollaboration", read=True)
        obj = get_object_or_404(active_objects(workspace).select_for_update(), pk=object_id)
        role = WorkspaceMember.objects.get(workspace=workspace, member=request.user, is_active=True).role
        can_write, admin = role_can_write(role), is_workspace_admin(self.actor("Read Object collaboration"), workspace)
        records = activity_records(workspace, obj.pk)
        before = request.query_params.get("activity_before")
        if before:
            cursor_id = serializers.UUIDField().run_validation(before)
            cursor = get_object_or_404(records, pk=cursor_id)
            records = records.filter(
                Q(timestamp__lt=cursor.timestamp) | Q(timestamp=cursor.timestamp, id__lt=cursor.pk)
            )
        records = list(records.order_by("-timestamp", "-id")[:51])
        activity = [
            {
                "id": record.pk,
                "command_id": record.command_id,
                "command_name": record.command_name,
                "actor_type": record.actor_type,
                "actor_id": record.actor_id,
                "timestamp": record.timestamp,
                "reason": record.reason,
                "source": record.source,
                "outcome": record.outcome,
                "correlation_id": record.correlation_id,
            }
            for record in records[:50]
        ]
        return Response(
            {
                "object_id": str(obj.pk),
                "object_version": obj.version,
                "can_write": can_write,
                "comments": [
                    item_data(item, request.user.pk, can_write, admin)
                    for item in ObjectComment.objects.filter(workspace=workspace, object=obj).select_related(
                        "created_by"
                    )
                ],
                "attachments": [
                    item_data(item, request.user.pk, can_write, admin)
                    for item in ObjectAttachment.objects.filter(workspace=workspace, object=obj).select_related(
                        "created_by"
                    )
                ],
                "activity": activity,
                "activity_next": str(records[49].pk) if len(records) > 50 else None,
            }
        )


class ObjectAttachmentUploadView(RadarAPIView):
    def post(self, request, slug, object_id):
        workspace = self.workspace()
        actor = self.actor("Add Object attachment")
        authorize(actor, workspace, "AddAttachment")
        get_object_or_404(active_objects(workspace), pk=object_id)
        if set(request.data) != {"file"} or len(request.FILES.getlist("file")) != 1:
            raise ValidationError({"file": "Send exactly one multipart file, without additional fields."})
        upload = prepare_upload(request.FILES["file"])
        options = self.command_options(require_schema_revision=False)
        envelope = {
            "command_name": "AddAttachment",
            "command_version": 1,
            "workspace_id": str(workspace.pk),
            "reason": actor.reason,
            "assertion": {"kind": "asserted"},
            "input": {"object_id": str(object_id), **upload.metadata},
            **options,
        }
        try:
            result = execute_command(actor=actor, workspace=workspace, envelope=envelope, upload=upload)
        except DatabaseError as exc:
            logging.getLogger(__name__).exception("RADAR attachment transaction failed")
            raise AttachmentUnavailable() from exc
        return Response(result)


class ObjectAttachmentDownloadView(RadarAPIView):
    def get(self, request, slug, object_id, attachment_id):
        workspace = self.workspace()
        authorize(self.actor("Download Object attachment"), workspace, "ReadAttachment", read=True)
        get_object_or_404(active_objects(workspace), pk=object_id)
        item = get_object_or_404(ObjectAttachment, workspace=workspace, object_id=object_id, pk=attachment_id)
        payload = get_object_or_404(AttachmentPayload, attachment=item)
        data = bytes(payload.data)
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            # Corruption must not be presented as a successful download.
            raise ValidationError({"code": "attachment_integrity_failed"})
        response = FileResponse(
            io.BytesIO(data), as_attachment=True, filename=item.filename, content_type="application/octet-stream"
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
