"""Small, atomic PostgreSQL attachments for the MVP, with authenticated downloads."""

import hashlib
from dataclasses import dataclass

from rest_framework.exceptions import APIException, ValidationError

MAX_ATTACHMENT_SIZE = 2 * 1024 * 1024
COLLABORATION_COMMANDS = {
    "AddComment",
    "EditComment",
    "DeleteComment",
    "AddAttachment",
    "RenameAttachment",
    "DeleteAttachment",
}


def validate_filename(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise ValidationError({"filename": "Use a filename of 1–255 characters."})
    if value in {".", ".."} or any(char in value for char in "/\\") or any(ord(char) < 32 for char in value):
        raise ValidationError({"filename": "Use a filename without paths or control characters."})
    return value.strip()


@dataclass(frozen=True)
class AttachmentUpload:
    filename: str
    data: bytes

    @property
    def metadata(self):
        return {"filename": self.filename, "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}


class AttachmentUnavailable(APIException):
    status_code = 503
    default_detail = "Upload failed. Reload collaboration before retrying the same intention."
    default_code = "attachment_upload_failed"


def prepare_upload(file):
    filename = validate_filename(file.name)
    # Do not trust the client's Content-Length, MIME type, or multipart size metadata.
    try:
        data = file.read(MAX_ATTACHMENT_SIZE + 1)
    except OSError as exc:
        raise AttachmentUnavailable() from exc
    if not data or len(data) > MAX_ATTACHMENT_SIZE:
        raise ValidationError({"file": "Upload a nonempty file no larger than 2 MiB."})
    return AttachmentUpload(filename, data)
