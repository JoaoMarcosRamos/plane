import json
from uuid import uuid4
from plane.radar.locks import observed_atomic
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from plane.app.views.base import BaseAPIView
from plane.app.permissions.workspace import WorkspaceMemberPermission
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from plane.db.models import Workspace
from plane.radar.commands.actor import Actor
from plane.radar.commands import create_object, update_object
from plane.radar.active import active_objects, active_types
from plane.radar.workspace_schema import lock_schema, schema_revision
from plane.radar.commands.compatibility import PendingCommand, legacy_confirmed_intent
from .serializers import ObjectInputSerializer, ObjectSerializer, ObjectTypeSerializer, ObjectSummarySerializer


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

    def command_options(self, *, require_schema_revision=True):
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
        revision = self.request.headers.get("X-Radar-Expected-Schema-Revision")
        if revision is None and (
            not require_schema_revision
            or legacy_confirmed_intent(actor=self.actor("Replay command"), workspace=self.workspace(), key=key)
        ):
            return {"expected_versions": versions, "idempotency_key": key}
        if revision is None or not revision.isdecimal():
            raise ValidationError(
                {"expected_schema_revision": "Send X-Radar-Expected-Schema-Revision from the reviewed catalog."}
            )
        return {"expected_versions": versions, "idempotency_key": key, "expected_schema_revision": int(revision)}

    @staticmethod
    def pending_response(result):
        if isinstance(result, PendingCommand):
            return Response(result.result, status=status.HTTP_202_ACCEPTED)
        return None


class ObjectTypesView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug):
        workspace = self.workspace()
        revision = lock_schema(workspace)
        return Response(
            ObjectTypeSerializer(active_types(workspace), many=True).data,
            headers={"X-Radar-Schema-Revision": str(revision)},
        )


class ObjectsView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug):
        workspace = self.workspace()
        revision = lock_schema(workspace)
        from .object_queries import object_query
        from .pagination import page
        from plane.radar.authorship import AUTHOR_RELATIONS

        objects, scope = object_query(self, workspace, revision)
        rows, cursor = page(
            objects.select_related(*AUTHOR_RELATIONS).defer("content"), request.query_params, scope=scope
        )
        return Response(
            ObjectSummarySerializer(rows, many=True).data,
            headers={"X-Radar-Schema-Revision": str(revision), "X-Radar-Next-Cursor": cursor or ""},
        )

    @observed_atomic
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
        return Response(
            ObjectSerializer(result).data,
            status=status.HTTP_201_CREATED,
            headers={"X-Radar-Schema-Revision": str(schema_revision(self.workspace()))},
        )


class ObjectDetailView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        revision = lock_schema(workspace)
        result = get_object_or_404(active_objects(workspace).select_related("object_type"), pk=object_id)
        return Response(ObjectSerializer(result).data, headers={"X-Radar-Schema-Revision": str(revision)})

    @observed_atomic
    def patch(self, request, slug, object_id):
        serializer = ObjectInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if {"properties", "parameters"} & set(serializer.validated_data):
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
        return Response(
            ObjectSerializer(result).data, headers={"X-Radar-Schema-Revision": str(schema_revision(self.workspace()))}
        )
