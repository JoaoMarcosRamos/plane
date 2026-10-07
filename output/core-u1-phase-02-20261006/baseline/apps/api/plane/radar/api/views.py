import json
from uuid import uuid4
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from plane.app.views.base import BaseAPIView
from plane.app.permissions.workspace import WorkspaceMemberPermission
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.commands import initialize_object_types, create_object, update_object
from plane.radar.models import Object
from plane.radar.commands.compatibility import PendingCommand
from .serializers import ObjectInputSerializer, ObjectSerializer, ObjectTypeSerializer


class RadarAPIView(BaseAPIView):
    permission_classes = [IsAuthenticated, WorkspaceMemberPermission]

    def workspace(self):
        return get_object_or_404(Workspace, slug=self.kwargs["slug"])

    def actor(self, reason):
        from rest_framework import serializers

        approval = self.request.headers.get("X-Radar-Approval-Id")
        correlation = self.request.headers.get("X-Radar-Correlation-Id")
        return Actor(
            actor_type="human",
            actor_id=self.request.user.pk,
            source="radar.session-api",
            reason=self.request.headers.get("X-Radar-Reason", reason),
            correlation_id=serializers.UUIDField().run_validation(correlation) if correlation else uuid4(),
            approval_id=serializers.UUIDField().run_validation(approval) if approval else None,
        )

    def command_options(self):
        raw = self.request.headers.get("X-Radar-Expected-Versions")
        if raw is None:
            raise ValidationError({"expected_versions": "Send X-Radar-Expected-Versions with the reviewed snapshot."})
        try:
            versions = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"expected_versions": "Expected a JSON version map."}) from exc
        if not isinstance(versions, dict):
            raise ValidationError({"expected_versions": "Expected a JSON version map."})
        key = self.request.headers.get("Idempotency-Key")
        if not key or len(key) > 128:
            raise ValidationError({"idempotency_key": "Send an Idempotency-Key of 1–128 characters."})
        return {"expected_versions": versions, "idempotency_key": key}

    @staticmethod
    def pending_response(result):
        if isinstance(result, PendingCommand):
            return Response(result.result, status=status.HTTP_202_ACCEPTED)
        return None


class ObjectTypesView(RadarAPIView):
    def get(self, request, slug):
        types = initialize_object_types(
            actor=self.actor("Initialize workspace object types"), workspace=self.workspace()
        )
        return Response(ObjectTypeSerializer(types, many=True).data)


class ObjectsView(RadarAPIView):
    def get(self, request, slug):
        objects = Object.objects.filter(workspace=self.workspace()).select_related("object_type")
        return Response(ObjectSerializer(objects, many=True).data)

    def post(self, request, slug):
        serializer = ObjectInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_object(
            actor=self.actor("Create object"),
            workspace=self.workspace(),
            **serializer.validated_data,
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        return Response(ObjectSerializer(result).data, status=status.HTTP_201_CREATED)


class ObjectDetailView(RadarAPIView):
    def get(self, request, slug, object_id):
        result = get_object_or_404(
            Object.objects.select_related("object_type"), workspace=self.workspace(), pk=object_id
        )
        return Response(ObjectSerializer(result).data)

    def patch(self, request, slug, object_id):
        serializer = ObjectInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "properties" in serializer.validated_data:
            raise ValidationError("Use the property endpoints or UpdateObject.set_properties.")
        result = update_object(
            actor=self.actor("Update object"),
            workspace=self.workspace(),
            object_id=object_id,
            changes=serializer.validated_data,
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        return Response(ObjectSerializer(result).data)
