from uuid import uuid4

from django.db import models
from django.db.models import Q
from .core import RadarBaseModel

ACTOR_TYPES = [(value, value) for value in ("human", "agent", "system", "integration")]


class Provenance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    command_id = models.UUIDField(db_index=True)
    command_name = models.CharField(max_length=64)
    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPES)
    actor_id = models.UUIDField()
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    source = models.CharField(max_length=255)
    correlation_id = models.UUIDField(db_index=True)
    run_id = models.UUIDField(null=True)
    approval_id = models.UUIDField(null=True)
    confidence = models.FloatField(null=True)
    context = models.JSONField(default=dict)
    changes = models.JSONField(default=list)
    outcome = models.CharField(max_length=32)

    class Meta:
        db_table = "radar_provenance"
        constraints = [
            models.CheckConstraint(condition=Q(actor_type__in=[v for v, _ in ACTOR_TYPES]), name="radar_prov_actor"),
            models.CheckConstraint(
                condition=Q(confidence__isnull=True) | Q(confidence__gte=0, confidence__lte=1),
                name="radar_prov_confidence",
            ),
        ]
        indexes = [models.Index(fields=["workspace", "timestamp"], name="radar_prov_ws_time")]


class ActorGrant(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPES)
    actor_id = models.UUIDField()
    delegator = models.ForeignKey("db.User", on_delete=models.PROTECT)
    commands = models.JSONField(default=list)
    object_types = models.JSONField(default=list)
    fields = models.JSONField(default=list)
    requires_approval = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    policy_version = models.PositiveIntegerField(default=1)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_actor_grants"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "actor_type", "actor_id"], name="radar_grant_actor")
        ]


class PersonIdentity(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    user = models.ForeignKey("db.User", on_delete=models.PROTECT)
    person = models.ForeignKey("radar.Object", on_delete=models.PROTECT)
    can_approve = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_person_identities"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="radar_identity_user"),
            models.UniqueConstraint(fields=["workspace", "person"], name="radar_identity_person"),
        ]


class CommandExecution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    actor_type = models.CharField(max_length=16, choices=ACTOR_TYPES)
    actor_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=128)
    intent_hash = models.CharField(max_length=64)
    command_name = models.CharField(max_length=64)
    envelope = models.JSONField()
    actor_context = models.JSONField()
    status = models.CharField(max_length=32, default="pending")
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "radar_command_executions"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "actor_type", "actor_id", "idempotency_key"], name="radar_command_key"
            )
        ]


class CommandApproval(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    execution = models.OneToOneField(CommandExecution, on_delete=models.PROTECT)
    intent_hash = models.CharField(max_length=64)
    policy_version = models.PositiveIntegerField(default=1)
    approver_id = models.UUIDField(null=True)
    rationale = models.TextField(default="")
    status = models.CharField(max_length=16, default="pending")
    expires_at = models.DateTimeField()

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_command_approvals"


class DecisionApproval(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    decision = models.ForeignKey("radar.Object", on_delete=models.PROTECT)
    approver_id = models.UUIDField()
    approver_person = models.ForeignKey("radar.Object", on_delete=models.PROTECT, related_name="decision_votes")
    rationale = models.TextField()
    reviewed_version = models.PositiveIntegerField()
    resulting_version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    evidence_versions = models.JSONField()
    is_stale = models.BooleanField(default=False)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_decision_approvals"


class ActionCompletion(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    action = models.OneToOneField("radar.Object", on_delete=models.PROTECT)
    evidence = models.ForeignKey("radar.Object", on_delete=models.PROTECT, related_name="action_completions")
    outcome = models.TextField()
    snapshot = models.JSONField()
    completed_at = models.DateTimeField()

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_action_completions"


class DomainEvent(models.Model):
    """Durable outbox; consumers acknowledge publication, not command success."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    execution_id = models.UUIDField(db_index=True)
    provenance = models.ForeignKey(Provenance, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=64)
    event_version = models.PositiveIntegerField(default=1)
    occurred_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()
    published_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "radar_command_outbox"
        indexes = [models.Index(fields=["published_at", "occurred_at"], name="radar_outbox_pending")]


class EvidenceRecord(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    document = models.ForeignKey("radar.Object", on_delete=models.PROTECT)
    target = models.ForeignKey("radar.Object", on_delete=models.PROTECT, related_name="evidence_records")
    relation = models.ForeignKey("radar.Relation", on_delete=models.PROTECT)
    observed_at = models.DateTimeField(null=True)
    content_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_evidence_records"


class RuntimeObjectIdentity(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    object = models.OneToOneField("radar.Object", on_delete=models.PROTECT)
    context = models.CharField(max_length=128)
    external_id = models.CharField(max_length=64)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_runtime_object_identities"
        constraints = [models.UniqueConstraint(fields=["workspace", "external_id"], name="radar_external_id")]


class OperationalRecord(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    object = models.OneToOneField("radar.Object", on_delete=models.PROTECT)
    data = models.JSONField(default=dict)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_operational_records"


class RuntimeCredential(RadarBaseModel):
    """Host credential bound to one agent, human delegator and management context."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    channel = models.CharField(
        max_length=16, choices=[("telegram", "telegram"), ("plane", "plane")], default="telegram"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    actor_id = models.UUIDField()
    context = models.CharField(max_length=128)
    external_author = models.CharField(max_length=64)
    reviewer = models.ForeignKey("db.User", on_delete=models.PROTECT)
    person = models.ForeignKey("radar.Object", on_delete=models.PROTECT)
    is_manager = models.BooleanField(default=False)
    object_ids = models.JSONField(null=True)
    is_active = models.BooleanField(default=True)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_runtime_credentials"


class AgentRuntimeRun(models.Model):
    """Stored product intention; CoS owns execution state, Plane owns authority."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    user = models.ForeignKey("db.User", on_delete=models.PROTECT)
    binding = models.ForeignKey(RuntimeCredential, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128)
    input_hash = models.CharField(max_length=64)
    request_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "radar_agent_runtime_runs"
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user", "idempotency_key"], name="radar_agent_run_key")
        ]
