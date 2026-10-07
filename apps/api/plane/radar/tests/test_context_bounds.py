"""Authorized fields must be selected before the runtime property budget."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from plane.radar.agent_runtime import load_context
from plane.radar.models import Object, PropertyDefinition, PropertyValue
from .test_core import create
from .fixture_writes import fixture_write

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


@pytest.mark.parametrize("hidden_count,visible_count", [(42, 1), (0, 20), (0, 21)])
def test_context_property_budget_counts_only_authorized_fields(context, hidden_count, visible_count):
    obj = create(context)
    allowed = []
    for index in range(hidden_count + visible_count):
        key = f"field_{index}"
        definition = fixture_write(
            lambda: PropertyDefinition.objects.create(
                workspace=obj.workspace, object_type=obj.object_type, key=key, name=key, value_type="string"
            )
        )
        fixture_write(
            lambda: PropertyValue.objects.create(
                id=UUID(int=index + 1), workspace=obj.workspace, object=obj, definition=definition, value=key
            )
        )
        if index >= hidden_count:
            allowed.append(key)
    snapshot = load_context(Object.objects.filter(pk=obj.pk), SimpleNamespace(fields=allowed), [obj.pk])
    properties = snapshot["objects"][0]["properties"]
    assert properties == {key: key for key in allowed[:20]}
    assert snapshot["truncated"] is (visible_count > 20)
