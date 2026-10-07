import hashlib
import json
from pathlib import Path
from plane.radar.models import Object, ObjectComment, ObjectAttachment, AttachmentPayload, Provenance

obj = Object.objects.get(workspace__slug="collaboration-browser")
comment = ObjectComment.objects.get(object=obj)
attachment = ObjectAttachment.all_objects.get(object=obj)
payload = AttachmentPayload.objects.get(attachment=attachment)
record = Provenance.objects.get(pk=attachment.last_provenance_id)
report = {
    "object_version": obj.version, "comment_revision": comment.revision, "comment_body": comment.body,
    "comment_creator_preserved": comment.created_provenance_id != comment.last_provenance_id,
    "attachment_deleted": attachment.deleted_at is not None, "attachment_revision": attachment.revision,
    "attachment_hash_matches": hashlib.sha256(bytes(payload.data)).hexdigest() == attachment.sha256,
    "attachment_creator_preserved": attachment.created_by_id != attachment.updated_by_id,
    "delete_actor_matches_admin": str(record.actor_id) == str(attachment.updated_by_id),
    "payload_retained": True,
    "commands": list(Provenance.objects.filter(workspace=obj.workspace, command_name__in=["AddComment", "EditComment", "AddAttachment", "RenameAttachment", "DeleteAttachment"]).values_list("command_name", flat=True)),
}
assert report["object_version"] == 1 and report["comment_revision"] == 2 and report["attachment_revision"] == 3
assert all(report[key] for key in ["comment_creator_preserved", "attachment_deleted", "attachment_hash_matches", "attachment_creator_preserved", "delete_actor_matches_admin", "payload_retained"])
print(json.dumps(report, indent=2))
