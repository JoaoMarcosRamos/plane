from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from plane.radar.today import attention_queue
from .views import RadarAPIView


class TodayView(RadarAPIView):
    def get(self, request, slug):
        timezone_name = request.query_params.get("timezone", "UTC")
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValidationError({"timezone": "Expected an IANA timezone."}) from exc
        return Response(attention_queue(self.workspace(), request.user, timezone_name))
