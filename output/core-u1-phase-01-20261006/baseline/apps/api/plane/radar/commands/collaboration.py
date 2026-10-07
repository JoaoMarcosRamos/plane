from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from plane.db.models import WorkspaceMember
from plane.radar.collaboration import MAX_ATTACHMENT_SIZE, validate_filename
from plane.radar.models import Object, ObjectComment, ObjectAttachment, AttachmentPayload
from plane.radar.mutation import current_mutation
from .execution import CommandConflict, emit


def dispatch(workspace, name, data):
    context = current_mutation.get()
    if context is None or context.actor.actor_type != "human":
        raise PermissionDenied("MVP collaboration requires an authenticated human command.")
    actor_id = context.actor.actor_id
    obj = Object.objects.filter(workspace=workspace, pk=data["object_id"]).first()
    if obj is None:
        raise NotFound("Object not found in this workspace.")
    common = {"workspace": workspace, "object": obj, "created_by_id": actor_id, "updated_by_id": actor_id}
    if name == "AddComment":
        item = ObjectComment.objects.create(**common, body=data["body"])
    elif name == "AddAttachment":
        upload = context.upload
        if upload is None or upload.metadata != {key: data[key] for key in ("filename", "size", "sha256")}:
            raise ValidationError({"file": "Use the authenticated multipart upload endpoint."})
        if not 0 < len(upload.data) <= MAX_ATTACHMENT_SIZE:
            raise ValidationError({"file": "Upload a nonempty file no larger than 2 MiB."})
        item = ObjectAttachment.objects.create(**common, **upload.metadata)
        AttachmentPayload.objects.create(attachment=item, data=upload.data)
    else:
        model = ObjectComment if name.endswith("Comment") else ObjectAttachment
        item = model.objects.select_for_update().filter(workspace=workspace, object=obj, pk=data["item_id"]).first()
        if item is None:
            raise NotFound("Collaboration item not found on this Object.")
        deleting = name.startswith("Delete")
        admin = WorkspaceMember.objects.filter(
            workspace=workspace, member_id=actor_id, role=20, is_active=True
        ).exists()
        if item.created_by_id != actor_id and not (deleting and admin):
            raise PermissionDenied("Only the author may edit; authors and workspace admins may delete.")
        if item.revision != data["expected_revision"]:
            raise CommandConflict({"code": "revision_conflict", "item_id": str(item.pk)})
        if deleting:
            item.deleted_at = timezone.now()
        elif name == "EditComment":
            item.body = data["body"]
        else:
            item.filename = validate_filename(data["filename"])
        item.revision += 1
        item.updated_by_id = actor_id
        item.save()
    emit(name, {"object_id": obj.pk, "item_id": item.pk, "revision": item.revision})
    return {"item_id": str(item.pk), "object_id": str(obj.pk), "revision": item.revision}
