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
    """Immutable-in-product legacy archive; new operations write OperationalEntry."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    object = models.OneToOneField("radar.Object", on_delete=models.PROTECT)
    data = models.JSONField(default=dict)
    backfill_hash = models.CharField(max_length=64, blank=True, default="")

    def validate_domain_links(self):
        from plane.radar.commands.context import command_context
        from rest_framework.exceptions import PermissionDenied

        if command_context().command_name != "BackfillOperationalHistory":
            raise PermissionDenied("Legacy operational archives have no current product writer.")
        original = OperationalRecord.all_objects.filter(pk=self.pk).values("data").first()
        if original and original["data"] != self.data:
            raise PermissionDenied("Preserve the original operational archive; reconcile facts through commands.")

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_operational_records"


class OperationalEntry(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT)
    object = models.ForeignKey("radar.Object", on_delete=models.PROTECT, related_name="operational_entries")
    kind = models.CharField(max_length=16, choices=[(key, key) for key in ("delegation", "review", "measurement")])
    schema_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField()
    object_version = models.PositiveIntegerField(null=True)
    actor_type = models.CharField(max_length=16, choices=[*ACTOR_TYPES, ("unknown", "unknown")])
    actor_id = models.UUIDField(null=True)
    occurred_at = models.DateTimeField(null=True)
    origin = models.CharField(max_length=16, choices=[("command", "command"), ("legacy", "legacy")])
    origin_key = models.CharField(max_length=160, null=True)
    evidence = models.ForeignKey(
        "radar.Object", null=True, on_delete=models.PROTECT, related_name="operational_evidence"
    )
    source_record = models.ForeignKey(OperationalRecord, null=True, on_delete=models.PROTECT)
    source_provenance = models.ForeignKey(
        Provenance, null=True, on_delete=models.PROTECT, related_name="operational_sources"
    )
    source_data = models.JSONField(null=True)

    def save(self, *args, **kwargs):
        from rest_framework.exceptions import PermissionDenied

        if not self._state.adding:
            raise PermissionDenied("Operational history is immutable.")
        super().save(*args, **kwargs)

    def validate_domain_links(self):
        from plane.radar.operational import validate_payload
        from plane.radar.commands.context import command_actor
        from rest_framework.exceptions import ValidationError
        from .core import Object

        if self.schema_version != 1:
            raise ValidationError("Unsupported operational record schema.")
        parsed = validate_payload(self.kind, self.payload)
        refs = [*parsed.get("executor_ids", [])]
        refs.extend(
            acceptance["evidence_id"]
            for acceptance in parsed.get("acceptances", {}).values()
            if "evidence_id" in acceptance
        )
        if parsed.get("evidence_id") != (str(self.evidence_id) if self.evidence_id else None):
            raise ValidationError("Evidence must match the typed operational payload.")
        if (
            self.evidence_id
            and not Object.all_objects.filter(pk=self.evidence_id, object_type__key="document").exists()
        ):
            raise ValidationError("Operational evidence must reference a Document.")
        if parsed.get("target_id", str(self.object_id)) != str(self.object_id):
            raise ValidationError("The reviewed target must match this Object.")
        if Object.all_objects.filter(workspace_id=self.workspace_id, pk__in=refs).count() != len(set(refs)):
            raise ValidationError("Operational references must belong to this workspace.")
        actor = command_actor()
        if not Object.all_objects.filter(
            workspace_id=self.workspace_id, object_type__key="person", pk__in=parsed.get("executor_ids", [])
        ).count() == len(set(parsed.get("executor_ids", []))):
            raise ValidationError("Delegation executors must be Persons.")
        if self.origin == "command":
            if (
                (self.actor_type, self.actor_id) != (actor.actor_type, actor.actor_id)
                or self.source_record_id
                or self.origin_key
                or self.source_data is not None
            ):
                raise ValidationError("Operational author must be the authenticated command actor.")
            if self.object_version != Object.all_objects.get(pk=self.object_id).version or self.occurred_at is None:
                raise ValidationError("Record the resulting Object revision and command time.")
        elif (
            self.origin != "legacy"
            or actor.actor_type != "human"
            or self.actor_type != "unknown"
            or not self.source_record_id
            or not self.origin_key
            or self.source_record.object_id != self.object_id
            or self.object_version is not None
        ):
            raise ValidationError("Legacy import requires explicit archive origin and unknown author type.")
        elif self.origin == "legacy":
            from plane.radar.commands.context import command_context
            from plane.radar.commands.access import require_workspace_admin

            if command_context().command_name != "BackfillOperationalHistory":
                raise ValidationError("Legacy entries require the administrative backfill command.")
            require_workspace_admin(actor, self.workspace)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_operational_entries"
        indexes = [
            models.Index(fields=["workspace", "object", "kind", "-created_at", "-id"], name="radar_op_history_page"),
            models.Index(fields=["workspace", "object", "-created_at", "-id"], name="radar_op_history_all"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "origin_key"], name="radar_op_origin_unique"),
            models.CheckConstraint(condition=Q(kind__in=["delegation", "review", "measurement"]), name="radar_op_kind"),
            models.CheckConstraint(condition=Q(schema_version=1), name="radar_op_schema"),
            models.CheckConstraint(
                condition=Q(object_version__isnull=True) | Q(object_version__gte=1), name="radar_op_object_version"
            ),
            models.CheckConstraint(condition=Q(origin__in=["command", "legacy"]), name="radar_op_origin"),
            models.CheckConstraint(
                condition=Q(actor_type__in=[v for v, _ in ACTOR_TYPES] + ["unknown"]), name="radar_op_actor"
            ),
        ]


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
