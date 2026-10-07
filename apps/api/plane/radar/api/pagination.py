"""Bounded keyset reads. Signed cursors bind tenant, filters and reviewed schema."""

from uuid import UUID
from django.core import signing
from rest_framework.exceptions import ValidationError


def page(queryset, params, *, scope):
    try:
        limit = int(params.get("limit", 50))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"limit": "Use an integer between 1 and 100."}) from exc
    if not 1 <= limit <= 100:
        raise ValidationError({"limit": "Use an integer between 1 and 100."})
    cursor = params.get("cursor")
    if cursor:
        try:
            decoded = signing.loads(cursor, salt="radar.query.page", max_age=3600)
            if decoded["scope"] != scope:
                raise ValueError("Cursor belongs to another query or revision.")
            queryset = queryset.filter(pk__gt=UUID(decoded["id"]))
        except (signing.BadSignature, ValueError, KeyError, TypeError) as exc:
            raise ValidationError({"cursor": "Refresh this query; its cursor is invalid or obsolete."}) from exc
    rows = list(queryset.order_by("pk")[: limit + 1])
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = signing.dumps({"scope": scope, "id": str(rows[-1].pk)}, salt="radar.query.page") if more else None
    return rows, next_cursor
