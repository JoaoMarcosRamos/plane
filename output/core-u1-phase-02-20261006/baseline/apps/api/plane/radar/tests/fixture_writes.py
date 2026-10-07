"""Explicit test-only raw fixture writes, including deliberately invalid historical rows.

Only the supplied ORM call is patched. Requests/commands/assertions execute with
production guards. Historical migrations use historical Django models instead.
"""

from unittest.mock import patch
from django.db import models
from plane.radar.models.core import RadarBaseModel, RadarQuerySet


def fixture_write(operation):
    with (
        patch.object(RadarBaseModel, "save", models.Model.save),
        patch.object(RadarQuerySet, "update", models.QuerySet.update),
    ):
        return operation()
