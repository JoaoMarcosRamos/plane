"""The browser reaches the API from another origin; RADAR headers must survive the CORS preflight."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

pytestmark = [pytest.mark.unit]

RADAR_HEADERS = [
    "idempotency-key",
    "x-radar-expected-versions",
    "x-radar-expected-schema-revision",
    "x-radar-reason",
    "x-radar-approval-id",
    "x-radar-correlation-id",
]


@override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=["http://localhost:3000"])
@pytest.mark.parametrize("path", ["objects/", "agent-runtime/runs/", "risk-reviews/", "commands/"])
def test_preflight_allows_radar_session_headers(path):
    response = APIClient().options(
        f"/api/workspaces/radar/radar/{path}",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS=",".join(["content-type", "x-csrftoken", *RADAR_HEADERS]),
    )
    assert response.status_code == 200
    assert response["access-control-allow-origin"] == "http://localhost:3000"
    allowed = {item.strip().lower() for item in response["access-control-allow-headers"].split(",")}
    assert set(RADAR_HEADERS) <= allowed
    exposed = {item.strip().lower() for item in response["access-control-expose-headers"].split(",")}
    assert "x-radar-schema-revision" in exposed


@override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=["http://localhost:3000"])
def test_preflight_still_rejects_unlisted_origins():
    response = APIClient().options(
        "/api/workspaces/radar/radar/objects/",
        HTTP_ORIGIN="http://attacker.invalid",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="idempotency-key",
    )
    assert "access-control-allow-origin" not in response
