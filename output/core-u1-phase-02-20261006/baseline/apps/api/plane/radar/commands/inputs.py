"""Transport-independent input contracts shared by session API and trusted adapters."""

from collections.abc import Mapping
import math
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    @staticmethod
    def _check_type(field, value):
        if value is None:
            return
        if isinstance(field, serializers.CharField) and not isinstance(value, str):
            raise serializers.ValidationError("Use a string.")
        if isinstance(field, serializers.BooleanField) and type(value) is not bool:
            raise serializers.ValidationError("Use a boolean.")
        if isinstance(field, serializers.IntegerField) and type(value) is not int:
            raise serializers.ValidationError("Use an integer.")
        if isinstance(field, serializers.ListField) and isinstance(value, list):
            for item in value:
                StrictSerializer._check_type(field.child, item)
        if isinstance(field, serializers.DateTimeField):
            try:
                parsed = parse_datetime(value) if isinstance(value, str) else value
                if parsed is None or timezone.is_naive(parsed):
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise serializers.ValidationError("Use an ISO datetime with timezone.")

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Expected a JSON object.")
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown or read-only field." for key in unknown})
        for key, value in data.items():
            try:
                self._check_type(self.fields[key], value)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({key: exc.detail})
        return super().to_internal_value(data)


class AssertionInput(StrictSerializer):
    kind = serializers.ChoiceField(choices=["asserted", "observed", "inferred"])
    evidence_ids = serializers.ListField(child=serializers.UUIDField(), default=list)
    confidence = serializers.JSONField(required=False)

    def validate(self, data):
        if "confidence" in data and (
            type(data["confidence"]) not in (int, float)
            or not math.isfinite(data["confidence"])
            or not 0 <= data["confidence"] <= 1
        ):
            raise serializers.ValidationError({"confidence": "Use a finite number between 0 and 1."})
        if data["kind"] == "inferred" and "confidence" not in data:
            raise serializers.ValidationError({"confidence": "Required for inference."})
        return data


class CommandInput(StrictSerializer):
    command_name = serializers.CharField(max_length=64)
    command_version = serializers.IntegerField(min_value=1, max_value=1)
    workspace_id = serializers.UUIDField(required=False)
    idempotency_key = serializers.CharField(max_length=128)
    expected_versions = serializers.DictField()
    reason = serializers.CharField()
    input = serializers.JSONField()
    approval_id = serializers.UUIDField(required=False)
    proposal_id = serializers.UUIDField(required=False)
    assertion = AssertionInput()

    def validate(self, data):
        if type(data.get("command_version")) is not int:
            raise serializers.ValidationError({"command_version": "Use an integer version."})
        return data


class CreateObjectInput(StrictSerializer):
    object_type_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    properties = serializers.DictField(required=False, default=dict)


class ObjectChangesInput(StrictSerializer):
    title = serializers.CharField(max_length=255, required=False)
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class UpdateObjectInput(StrictSerializer):
    object_id = serializers.UUIDField()
    changes = ObjectChangesInput(required=False, default=dict)
    set_properties = serializers.DictField(default=dict)
    remove_properties = serializers.ListField(child=serializers.CharField(), default=list)

    def validate(self, data):
        if not (data["changes"] or data["set_properties"] or data["remove_properties"]):
            raise serializers.ValidationError("Provide at least one change.")
        if set(data["set_properties"]) & set(data["remove_properties"]):
            raise serializers.ValidationError("Cannot set and remove the same property.")
        return data


class InitializeObjectPropertiesInput(StrictSerializer):
    object_id = serializers.UUIDField()


class LinkObjectsInput(StrictSerializer):
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()
    relation_type_id = serializers.UUIDField()


class UnlinkObjectsInput(StrictSerializer):
    relation_id = serializers.UUIDField()


class CreateActionInput(StrictSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    next_step = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.CharField(required=False)
    due_date = serializers.CharField(required=False)
    origin_decision_id = serializers.UUIDField(required=False)
    owner_person_id = serializers.UUIDField(required=False)
    executor_person_ids = serializers.ListField(child=serializers.UUIDField(), default=list)
    mitigates_risk_ids = serializers.ListField(child=serializers.UUIDField(), default=list)


class CompleteActionInput(StrictSerializer):
    action_id = serializers.UUIDField()
    outcome = serializers.CharField()
    evidence_id = serializers.UUIDField()


class RegisterRiskInput(StrictSerializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    likelihood = serializers.JSONField(required=False)
    impact = serializers.JSONField(required=False)
    response_strategy = serializers.CharField(required=False)
    review_date = serializers.CharField(required=False)
    threatens_object_ids = serializers.ListField(child=serializers.UUIDField(), default=list)
    owner_person_id = serializers.UUIDField(required=False)


class CreateDecisionInput(StrictSerializer):
    title = serializers.CharField(max_length=255)
    context = serializers.CharField()
    decision = serializers.CharField()
    rationale = serializers.CharField()
    consequences = serializers.ListField(child=serializers.CharField(), default=list)
    project_id = serializers.UUIDField(required=False)
    evidence_ids = serializers.ListField(child=serializers.UUIDField(), default=list)
    consultation_person_ids = serializers.ListField(child=serializers.UUIDField(), default=list)
    notification_person_ids = serializers.ListField(child=serializers.UUIDField(), default=list)


class ApproveDecisionInput(StrictSerializer):
    decision_id = serializers.UUIDField()
    rationale = serializers.CharField()
    approver_person_id = serializers.UUIDField()


class EvidenceDocumentInput(StrictSerializer):
    existing_id = serializers.UUIDField(required=False)
    title = serializers.CharField(max_length=255, required=False)
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    document_type = serializers.CharField(required=False)
    summary = serializers.CharField(required=False, allow_blank=True)
    uri = serializers.CharField(required=False)
    source_system = serializers.CharField(required=False)

    def validate(self, data):
        if "existing_id" in data:
            if len(data) != 1:
                raise serializers.ValidationError("Use either an existing document or a new document.")
        elif not data.get("title") or not data.get("source_system"):
            raise serializers.ValidationError("New documents require title and source_system.")
        return data


class AddEvidenceInput(StrictSerializer):
    target_id = serializers.UUIDField()
    document = EvidenceDocumentInput()
    relation_key = serializers.ChoiceField(choices=["verifies", "informed_by", "evidences"])
    observed_at = serializers.DateTimeField(required=False)
    content_hash = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)


class OperationalInput(StrictSerializer):
    context = serializers.RegexField(r"^(company|manager):[A-Za-z0-9_.-]+$")


class CaptureIssueInput(OperationalInput):
    title = serializers.CharField(max_length=255)
    case_title = serializers.CharField(max_length=255)
    evidence_title = serializers.CharField(max_length=255)
    source = serializers.CharField(max_length=1200)
    priority = serializers.CharField(required=False)
    owner_id = serializers.UUIDField(required=False)


class DelegateActionInput(OperationalInput):
    action_id = serializers.UUIDField()
    executor_id = serializers.UUIDField(required=False)
    executor_ids = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=False)
    due_at = serializers.DateTimeField()
    next_review_at = serializers.DateTimeField(required=False)

    def validate(self, data):
        if ("executor_id" in data) == ("executor_ids" in data):
            raise serializers.ValidationError("Select one executor or a list of executors.")
        if data.get("next_review_at") and data["next_review_at"] > data["due_at"]:
            raise serializers.ValidationError("Review must not follow the due date.")
        return data


class ReviewObjectInput(OperationalInput):
    target_id = serializers.UUIDField()
    assessment = serializers.CharField(max_length=1200)
    evidence_id = serializers.UUIDField()
    next_review_at = serializers.DateTimeField(required=False)
    disposition = serializers.ChoiceField(choices=["resolved", "accepted"], required=False)


class RecordMeasurementInput(OperationalInput):
    indicator_id = serializers.UUIDField()
    value = serializers.JSONField()
    measured_at = serializers.DateTimeField()
    evidence_id = serializers.UUIDField(required=False)
    evidence_title = serializers.CharField(max_length=255, required=False)
    evidence_source = serializers.CharField(max_length=1200, required=False)
    evidence_text = serializers.CharField(max_length=1200, required=False)

    def validate(self, data):
        if type(data["value"]) not in (int, float) or not math.isfinite(data["value"]):
            raise serializers.ValidationError("Use a finite measurement value.")
        inline = {"evidence_title", "evidence_source", "evidence_text"}.intersection(data)
        if "evidence_id" in data and inline:
            raise serializers.ValidationError({"code": "evidence_source_conflict"})
        if "evidence_id" not in data and len(inline) != 3:
            raise serializers.ValidationError({"code": "evidence_required"})
        return data


class AddCommentInput(StrictSerializer):
    object_id = serializers.UUIDField()
    body = serializers.CharField(max_length=10000)


class CollaborationItemInput(StrictSerializer):
    object_id = serializers.UUIDField()
    item_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)


class EditCommentInput(CollaborationItemInput):
    body = serializers.CharField(max_length=10000)


class AddAttachmentInput(StrictSerializer):
    object_id = serializers.UUIDField()
    filename = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1, max_value=2 * 1024 * 1024)
    sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")

    def validate_filename(self, value):
        from plane.radar.collaboration import validate_filename

        return validate_filename(value)


class RenameAttachmentInput(CollaborationItemInput):
    filename = serializers.CharField(max_length=255)

    def validate_filename(self, value):
        from plane.radar.collaboration import validate_filename

        return validate_filename(value)


INPUTS = {
    "InitializeObjectProperties": InitializeObjectPropertiesInput,
    "AddComment": AddCommentInput,
    "EditComment": EditCommentInput,
    "DeleteComment": CollaborationItemInput,
    "AddAttachment": AddAttachmentInput,
    "RenameAttachment": RenameAttachmentInput,
    "DeleteAttachment": CollaborationItemInput,
    "CreateObject": CreateObjectInput,
    "UpdateObject": UpdateObjectInput,
    "LinkObjects": LinkObjectsInput,
    "UnlinkObjects": UnlinkObjectsInput,
    "CreateAction": CreateActionInput,
    "CompleteAction": CompleteActionInput,
    "RegisterRisk": RegisterRiskInput,
    "CreateDecision": CreateDecisionInput,
    "ApproveDecision": ApproveDecisionInput,
    "AddEvidence": AddEvidenceInput,
    "CaptureIssue": CaptureIssueInput,
    "DelegateAction": DelegateActionInput,
    "ReviewObject": ReviewObjectInput,
    "RecordMeasurement": RecordMeasurementInput,
}
