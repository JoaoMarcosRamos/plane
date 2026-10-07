from django.db import models
from django.db.models import Q
from .core import RadarBaseModel


class WorkspaceSchemaState(RadarBaseModel):
    workspace = models.OneToOneField("db.Workspace", on_delete=models.PROTECT, related_name="radar_schema")
    revision = models.PositiveBigIntegerField(default=1)
    package_version = models.CharField(max_length=64, blank=True, default="")
    package_hash = models.CharField(max_length=64, blank=True, default="")
    origin = models.CharField(max_length=16, choices=[("package", "package"), ("legacy", "legacy")])
    installed_base = models.JSONField(default=dict)
    divergences = models.JSONField(default=list)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_workspace_schema_states"
        constraints = [models.CheckConstraint(condition=Q(revision__gte=1), name="radar_schema_revision_positive")]


class SchemaUpgrade(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_schema_upgrades")
    from_version = models.CharField(max_length=64, blank=True, default="")
    to_version = models.CharField(max_length=64)
    package_hash = models.CharField(max_length=64)
    diff = models.JSONField(default=dict)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_schema_upgrades"
