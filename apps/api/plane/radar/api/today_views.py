from django.db import transaction
from plane.radar.workspace_schema import lock_schema
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.radar.today import attention_queue
from .views import RadarAPIView


class TodayView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug):
        timezone_name = request.query_params.get("timezone", "UTC")
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValidationError({"timezone": "Expected an IANA timezone."}) from exc
        workspace = self.workspace()
        revision = lock_schema(workspace)
        return Response({**attention_queue(workspace, request.user, timezone_name), "schema_revision": revision})
