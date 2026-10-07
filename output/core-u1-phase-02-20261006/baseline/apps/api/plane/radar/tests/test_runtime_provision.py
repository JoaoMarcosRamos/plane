from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command
from plane.radar.commands import configure_person_identity
from plane.radar.models import PersonIdentity, RuntimeCredential
from .test_runtime_contract import runtime  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def test_provision_keeps_existing_decision_authority(request):
    state = request.getfixturevalue("runtime")
    ctx = state[0]
    configure_person_identity(
        actor=ctx[5], workspace=ctx[3], user_id=ctx[0].pk, person_id=state[4].pk, can_approve=True
    )
    output = StringIO()
    call_command(
        "radar_runtime_provision",
        workspace=ctx[3].slug,
        admin_id=ctx[0].pk,
        context="company:test",
        agent_id=uuid4(),
        reviewer_id=ctx[0].pk,
        person_id=state[4].pk,
        telegram_user_id=42,
        stdout=output,
    )
    assert PersonIdentity.objects.get(workspace=ctx[3], user=ctx[0]).can_approve
    assert RuntimeCredential.objects.count() == 2
    assert len(output.getvalue().strip()) >= 48
