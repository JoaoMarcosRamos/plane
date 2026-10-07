from django.db import models

from .core import RadarBaseModel


class RiskReview(models.Model):
    """Immutable validated copy of a completed CoS result, owned by Plane."""

    run = models.OneToOneField("radar.AgentRuntimeRun", primary_key=True, on_delete=models.PROTECT)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "radar_risk_reviews"


class RiskReviewProposal(RadarBaseModel):
    """A separately approved command; editing preserves the original intention."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    review = models.ForeignKey(RiskReview, on_delete=models.PROTECT, related_name="proposals")
    ordinal = models.PositiveSmallIntegerField()
    component = models.CharField(max_length=16, choices=[("relation", "relation"), ("action", "action")])
    revision = models.PositiveIntegerField(default=1)
    reviewed_context = models.JSONField(default=dict)
    execution = models.OneToOneField("radar.CommandExecution", on_delete=models.PROTECT)
    previous = models.OneToOneField("self", null=True, on_delete=models.PROTECT, related_name="replacement")

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_risk_review_proposals"
        constraints = [
            models.UniqueConstraint(
                fields=["review", "ordinal", "component", "revision"], name="radar_risk_proposal_revision"
            )
        ]
