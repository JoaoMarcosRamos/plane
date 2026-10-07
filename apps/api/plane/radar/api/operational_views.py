from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response

from plane.radar.models import Object
from plane.radar.commands.queries import lookup_object
from plane.radar.commands.access import require_human_membership
from plane.radar.operational import operation_projection, history_page
from plane.radar.workspace_schema import lock_schema
from .views import RadarAPIView


class ObjectOperationsView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        require_human_membership(self.actor("Read operational projection"), workspace, write=False)
        revision = lock_schema(workspace)
        obj = lookup_object(workspace, object_id, active_person=False)
        return Response(
            {
                "object_id": str(obj.pk),
                "object_version": obj.version,
                "schema_revision": revision,
                **operation_projection(obj, timezone_name=request.query_params.get("timezone", "UTC")),
            }
        )


class ObjectOperationalHistoryView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        require_human_membership(self.actor("Read historical operational records"), workspace, write=False)
        revision = lock_schema(workspace)
        # Explicit historical API, including resources retired from operation.
        obj = get_object_or_404(Object.all_objects, workspace=workspace, pk=object_id)
        limit = serializers.IntegerField(min_value=1, max_value=100).run_validation(
            request.query_params.get("limit", 20)
        )
        return Response(
            {
                "object_id": str(obj.pk),
                "object_version": obj.version,
                "schema_revision": revision,
                **history_page(
                    workspace,
                    obj,
                    kind=request.query_params.get("kind"),
                    limit=limit,
                    cursor=request.query_params.get("cursor"),
                ),
            }
        )
