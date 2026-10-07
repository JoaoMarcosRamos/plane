from uuid import uuid4
from django.db import models
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Q


class RadarQuerySet(models.QuerySet):
    def update(self, **kwargs):
        from plane.radar.mutation import current_mutation

        context = current_mutation.get()
        pointers = {"created_provenance_id", "last_provenance_id"}
        if (
            context is None
            or context.provenance_id is None
            or not kwargs
            or set(kwargs) - pointers
            or any(value != context.provenance_id for value in kwargs.values())
        ):
            raise PermissionDenied("RADAR bulk writes require individual commands.")
        allowed = [pk for label, pk in context.changes if label == self.model._meta.label]
        if self.exclude(workspace_id=context.workspace_id).exists() or self.exclude(pk__in=allowed).exists():
            raise PermissionDenied("Provenance updates must belong to this command's changes.")
        return super().update(**kwargs)

    def bulk_create(self, *args, **kwargs):
        raise PermissionDenied("Use individual RADAR commands.")

    def bulk_update(self, *args, **kwargs):
        raise PermissionDenied("Use individual RADAR commands.")

    def delete(self):
        raise NotImplementedError("RADAR deletion requires a command.")


class ActiveManager(models.Manager.from_queryset(RadarQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class RadarBaseModel(models.Model):
    """Explicit audit: no Plane save override, thread-local actor or async cascade."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "db.User", null=True, on_delete=models.SET_NULL, related_name="radar_%(class)s_created"
    )
    updated_by = models.ForeignKey(
        "db.User", null=True, on_delete=models.SET_NULL, related_name="radar_%(class)s_updated"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_provenance = models.ForeignKey(
        "radar.Provenance", null=True, on_delete=models.PROTECT, related_name="+", editable=False
    )
    last_provenance = models.ForeignKey(
        "radar.Provenance", null=True, on_delete=models.PROTECT, related_name="+", editable=False
    )

    objects = ActiveManager()
    all_objects = RadarQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def delete(self, *args, **kwargs):
        raise NotImplementedError("RADAR deletion requires a command.")

    def save(self, *args, **kwargs):
        from plane.radar.mutation import current_mutation, json_value

        context = current_mutation.get()
        if context is None or self.workspace_id != context.workspace_id:
            raise PermissionDenied("RADAR writes require a command in the same workspace.")
        before = None
        if not self._state.adding:
            before = self.__class__.all_objects.filter(pk=self.pk).values().first()
            if before is not None:
                if before["workspace_id"] != self.workspace_id:
                    raise PermissionDenied("RADAR workspace is immutable.")
                if before["created_by_id"] != self.created_by_id:
                    raise PermissionDenied("RADAR creator is immutable.")
                for field in ("created_provenance_id", "last_provenance_id"):
                    if before[field] != getattr(self, field):
                        raise PermissionDenied("Only the command flush may change provenance pointers.")
                before = json_value(before)
                for key in ("created_provenance_id", "last_provenance_id"):
                    before.pop(key, None)
        elif self.created_provenance_id is not None or self.last_provenance_id is not None:
            raise PermissionDenied("Provenance is assigned by the command flush.")
        for field in self._meta.concrete_fields:
            related = field.related_model if field.is_relation else None
            if (
                related is not None
                and related._meta.app_label == "radar"
                and any(item.name == "workspace" for item in related._meta.fields)
            ):
                pk = getattr(self, field.attname)
                if pk is not None and not related._base_manager.filter(pk=pk, workspace_id=self.workspace_id).exists():
                    raise ValidationError({field.name: "Select a reference in this workspace."})
        self.validate_domain_links()
        super().save(*args, **kwargs)
        context.record(self, before)

    def validate_domain_links(self):
        """Subclass structural checks; business effects remain in command handlers."""


class ObjectType(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_object_types")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=64, blank=True, default="")
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    rules = models.JSONField(default=dict)

    def validate_domain_links(self):
        from plane.radar.commands.rules import validate_type_rules

        validate_type_rules(self.rules, self.key)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_object_types"
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"], condition=Q(deleted_at__isnull=True), name="radar_type_workspace_key_live"
            )
        ]


class Object(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_objects")
    object_type = models.ForeignKey(ObjectType, on_delete=models.PROTECT, related_name="objects_of_type")
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_objects"
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["workspace", "object_type"], name="radar_object_ws_type_idx"),
            models.Index(
                fields=["workspace", "id"], condition=Q(deleted_at__isnull=True), name="radar_object_ws_page_idx"
            ),
            models.Index(
                fields=["workspace", "object_type", "id"],
                condition=Q(deleted_at__isnull=True),
                name="radar_object_type_page_idx",
            ),
        ]
        constraints = [models.CheckConstraint(condition=Q(version__gte=1), name="radar_object_version_positive")]
