from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response

from plane.radar.commands import execute_command, review_command, register_actor_grant, configure_person_identity
from plane.radar.commands.execution import authorize, command_envelope
from plane.radar.commands.inputs import StrictSerializer
from plane.radar.models import CommandExecution, Object
from .views import RadarAPIView


class CommandsView(RadarAPIView):
    def post(self, request, slug):
        # Only the authenticated session determines Actor; actor fields in JSON are rejected by the envelope.
        workspace = self.workspace()
        reason = (
            serializers.CharField().run_validation(request.data.get("reason")) if isinstance(request.data, dict) else ""
        )
        result = execute_command(actor=self.actor(reason), workspace=workspace, envelope=request.data)
        return Response(result, status=status.HTTP_202_ACCEPTED if result["status"] == "pending_approval" else 200)


class CommandDetailView(RadarAPIView):
    def get(self, request, slug, command_id):
        workspace = self.workspace()
        authorize(self.actor("Read command"), workspace, "ReadCommand")
        execution = get_object_or_404(CommandExecution, workspace=workspace, pk=command_id)
        return Response(
            {
                "command_id": str(execution.pk),
                "status": execution.status,
                "intent_hash": execution.intent_hash,
                "envelope": command_envelope(execution),
                "rules_contract": execution.envelope.get("rules_contract"),
                "schema_hash": execution.envelope["schema_hash"],
                "actor_context": execution.actor_context,
                "result": execution.result,
            }
        )


class ReviewInput(StrictSerializer):
    intent_hash = serializers.RegexField(r"^[a-f0-9]{64}$")
    approve = serializers.BooleanField()
    rationale = serializers.CharField()


class CommandReviewView(RadarAPIView):
    def post(self, request, slug, command_id):
        parsed = ReviewInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        approval = review_command(
            actor=self.actor("Review command execution"),
            workspace=self.workspace(),
            command_id=command_id,
            **parsed.validated_data,
        )
        return Response({"approval_id": str(approval.pk), "status": approval.status})


class GrantInput(StrictSerializer):
    actor_type = serializers.ChoiceField(choices=["agent", "system", "integration"])
    actor_id = serializers.UUIDField()
    delegator_id = serializers.UUIDField()
    commands = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    object_types = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    fields = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    requires_approval = serializers.BooleanField(default=True)
    is_active = serializers.BooleanField(default=True)


class ActorGrantsView(RadarAPIView):
    def post(self, request, slug):
        parsed = GrantInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        grant = register_actor_grant(
            actor=self.actor("Configure principal grant"), workspace=self.workspace(), **parsed.validated_data
        )
        return Response({"grant_id": str(grant.pk), "policy_version": grant.policy_version})


class IdentityInput(StrictSerializer):
    user_id = serializers.UUIDField()
    person_id = serializers.UUIDField()
    can_approve = serializers.BooleanField(default=False)
    is_active = serializers.BooleanField(default=True)


class PersonIdentitiesView(RadarAPIView):
    def post(self, request, slug):
        parsed = IdentityInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        identity = configure_person_identity(
            actor=self.actor("Verify Person identity"), workspace=self.workspace(), **parsed.validated_data
        )
        return Response({"identity_id": str(identity.pk), "can_approve": identity.can_approve})


class ObjectProvenanceView(RadarAPIView):
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        authorize(self.actor("Read object provenance"), workspace, "ReadProvenance", read=True)
        get_object_or_404(Object, workspace=workspace, pk=object_id)
        from .collaboration_views import activity_records

        records = activity_records(workspace, object_id)
        return Response(
            list(
                records.order_by("timestamp", "id").values(
                    "id",
                    "command_id",
                    "command_name",
                    "actor_type",
                    "actor_id",
                    "timestamp",
                    "reason",
                    "source",
                    "correlation_id",
                    "run_id",
                    "approval_id",
                    "confidence",
                    "context",
                    "changes",
                    "outcome",
                )
            )
        )
