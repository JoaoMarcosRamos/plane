from django.db import models
from django.db.models import Q

from .core import RadarBaseModel


class AgentConfiguration(RadarBaseModel):
    """Versioned product configuration for a provisioned user/agent binding."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    binding = models.OneToOneField("radar.RuntimeCredential", on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    identity = models.JSONField()
    role = models.JSONField()
    policies = models.JSONField()
    permissions = models.JSONField()

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_agent_configurations"
        constraints = [models.CheckConstraint(condition=Q(version__gte=1), name="radar_agent_config_version")]
