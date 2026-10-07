"""Collaboration belongs to a RADAR Object, independently of Plane Issues."""

from django.db import models
from rest_framework.exceptions import PermissionDenied

from plane.radar.mutation import current_mutation
from .core import RadarBaseModel, RadarQuerySet


class CollaborationQuerySet(RadarQuerySet):
    def update(self, **kwargs):
        context = current_mutation.get()
        if context is None or set(kwargs) - {"created_provenance_id", "last_provenance_id"}:
            raise PermissionDenied("Collaboration changes require commands, including bulk writes.")
        if self.exclude(workspace_id=context.workspace_id).exists():
            raise PermissionDenied("A command cannot mutate another workspace.")
        return super().update(**kwargs)

    def bulk_create(self, *args, **kwargs):
        raise PermissionDenied("Use individual collaboration commands.")

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied("Use individual collaboration commands.")


class CollaborationManager(models.Manager.from_queryset(CollaborationQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class CollaborationBase(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    object = models.ForeignKey("radar.Object", on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=1)
    objects = CollaborationManager()
    all_objects = CollaborationQuerySet.as_manager()

    class Meta(RadarBaseModel.Meta):
        abstract = True

    def save(self, *args, **kwargs):
        context = current_mutation.get()
        if context is None or context.workspace_id != self.workspace_id:
            raise PermissionDenied("Collaboration writes require a RADAR command.")
        if self.object.workspace_id != self.workspace_id:
            raise PermissionDenied("Object belongs to another workspace.")
        super().save(*args, **kwargs)


class ObjectComment(CollaborationBase):
    body = models.TextField()

    class Meta(CollaborationBase.Meta):
        db_table = "radar_object_comments"
        ordering = ["created_at", "id"]


class ObjectAttachment(CollaborationBase):
    filename = models.CharField(max_length=255)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)

    class Meta(CollaborationBase.Meta):
        db_table = "radar_object_attachments"
        ordering = ["created_at", "id"]


class PayloadQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied("Attachment bytes are immutable.")

    def delete(self):
        raise PermissionDenied("Attachment bytes are retained for audit.")

    def bulk_create(self, *args, **kwargs):
        raise PermissionDenied("Attachment writes require a command.")

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied("Attachment bytes are immutable.")


class AttachmentPayload(models.Model):
    """Bounded private bytes; never serialized into command envelopes/provenance."""

    attachment = models.OneToOneField(ObjectAttachment, primary_key=True, on_delete=models.PROTECT)
    data = models.BinaryField(editable=False)
    objects = PayloadQuerySet.as_manager()

    class Meta:
        db_table = "radar_attachment_payloads"

    def save(self, *args, **kwargs):
        context = current_mutation.get()
        if context is None or context.workspace_id != self.attachment.workspace_id or not self._state.adding:
            raise PermissionDenied("Attachment bytes are immutable and require a RADAR command.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Attachment retention is independent of soft deletion.")
