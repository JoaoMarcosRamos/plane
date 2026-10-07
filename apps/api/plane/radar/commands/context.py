"""Public transaction context for deterministic domain effects."""

from uuid import UUID
from rest_framework.exceptions import PermissionDenied
from plane.radar.mutation import MutationContext, current_mutation
from .actor import Actor


def command_context() -> MutationContext:
    context = current_mutation.get()
    if context is None:
        raise PermissionDenied("Mutation requires the shared command layer and an explicit Actor.")
    return context


def command_actor() -> Actor:
    return command_context().actor


def command_user_id() -> UUID | None:
    actor = command_actor()
    return actor.actor_id if actor.actor_type == "human" else None


def command_now():
    """Identify generated clock values so plans never erase caller-supplied dates."""
    from django.utils import timezone
    from plane.radar.mutation import json_value

    now = timezone.now()
    command_context().server_times.add(json_value(now))
    return now
