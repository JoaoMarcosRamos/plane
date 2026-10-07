"""Actor summaries derived from provenance; bulk human resolution for list/detail adapters."""

from collections.abc import Sequence
from typing import Literal, TypedDict
from uuid import UUID
from plane.db.models import User
from plane.radar.commands.results import result_timestamp
from plane.radar.models import Object

AUTHOR_RELATIONS = ("object_type", "created_provenance", "last_provenance")


class ActorSummary(TypedDict):
    actor_type: Literal["human", "agent", "system", "integration", "unknown"]
    actor_id: str | None
    display_name: str | None
    user_status: Literal["available", "deleted", "unknown", "not_applicable"]
    source: str | None
    timestamp: str
    provenance_id: str | None


class ObjectAuthorship(TypedDict):
    created_actor: ActorSummary
    updated_actor: ActorSummary


def object_authorship(objects: Sequence[Object]) -> dict[UUID, ObjectAuthorship]:
    """Objects should preload AUTHOR_RELATIONS; names are resolved in one scoped batch."""
    actors = {}
    ids = set()
    for obj in objects:
        for label, pointer, legacy_id, timestamp in (
            ("created_actor", obj.created_provenance, obj.created_by_id, obj.created_at),
            ("updated_actor", obj.last_provenance, obj.updated_by_id, obj.updated_at),
        ):
            actor_id = pointer.actor_id if pointer else legacy_id
            actor_type = pointer.actor_type if pointer else "human" if legacy_id else "unknown"
            actors[obj.pk, label] = actor_id, actor_type, pointer, timestamp
            if actor_type == "human" and actor_id:
                ids.add(actor_id)
    users = User.objects.filter(pk__in=ids).in_bulk() if ids else {}
    result = {}
    for obj in objects:
        summaries = {}
        for label in ("created_actor", "updated_actor"):
            actor_id, actor_type, pointer, timestamp = actors[obj.pk, label]
            user = users.get(actor_id)
            summaries[label] = {
                "actor_type": actor_type,
                "actor_id": str(actor_id) if actor_id else None,
                "display_name": (user.display_name or user.full_name) if user else None,
                "user_status": ("available" if user else "deleted")
                if actor_type == "human"
                else "unknown"
                if actor_type == "unknown"
                else "not_applicable",
                "source": pointer.source if pointer else None,
                "timestamp": result_timestamp(pointer.timestamp if pointer else timestamp),
                "provenance_id": str(pointer.pk) if pointer else None,
            }
        result[obj.pk] = summaries
    return result
