"""Typed operational history and the common canonical deadline/assignment projection."""

import base64
import json
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from plane.radar.active import active_relations
from plane.radar.commands.inputs import StrictSerializer, FiniteNumberField
from plane.radar.mutation import json_value

KINDS = ("delegation", "review", "measurement")


class DelegationPayload(StrictSerializer):
    executor_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=100)
    due_at = serializers.DateTimeField()
    next_review_at = serializers.DateTimeField(required=False, allow_null=True)
    state = serializers.ChoiceField(choices=["proposed", "accepted", "partially_accepted", "rejected"])
    proposed_by = serializers.UUIDField(required=False, allow_null=True)
    proposed_at = serializers.DateTimeField(required=False, allow_null=True)
    accepted_at = serializers.DateTimeField(required=False, allow_null=True)
    acceptances = serializers.DictField(required=False, default=dict)

    def validate(self, data):
        if len(set(data["executor_ids"])) != len(data["executor_ids"]):
            raise ValidationError("Executors must be unique.")
        if data.get("next_review_at") and data["next_review_at"] > data["due_at"]:
            raise ValidationError("Review must not follow the deadline.")
        if data["state"] == "accepted" and not data.get("accepted_at"):
            raise ValidationError("Accepted terms require their original acceptance time.")
        if data.get("accepted_at") and data.get("proposed_at") and data["accepted_at"] < data["proposed_at"]:
            raise ValidationError("Acceptance cannot precede proposal.")
        if len(data["acceptances"]) > 100:
            raise ValidationError("Use at most 100 typed acceptances.")
        for person, acceptance in data["acceptances"].items():
            if serializers.UUIDField().run_validation(person) not in data["executor_ids"]:
                raise ValidationError("Acceptance must belong to a declared executor.")
            parsed = AcceptancePayload(data=acceptance)
            parsed.is_valid(raise_exception=True)
        return data


class AcceptancePayload(StrictSerializer):
    accepted_at = serializers.DateTimeField()
    evidence_id = serializers.UUIDField(required=False)
    state = serializers.ChoiceField(choices=["accepted", "rejected"], required=False)


class ReviewPayload(StrictSerializer):
    target_id = serializers.UUIDField(required=False)
    context = serializers.RegexField(r"^(company|manager):[A-Za-z0-9_.-]+$", required=False, max_length=128)
    assessment = serializers.CharField(max_length=1200)
    evidence_id = serializers.UUIDField()
    next_review_at = serializers.DateTimeField(required=False, allow_null=True)
    disposition = serializers.ChoiceField(choices=["resolved", "accepted"], required=False)
    actor = serializers.UUIDField(required=False, allow_null=True)
    at = serializers.DateTimeField(required=False, allow_null=True)


class MeasurementPayload(StrictSerializer):
    value = FiniteNumberField()
    measured_at = serializers.DateTimeField()
    evidence_id = serializers.UUIDField()
    actor = serializers.UUIDField(required=False, allow_null=True)
    at = serializers.DateTimeField(required=False, allow_null=True)


PAYLOADS = {"delegation": DelegationPayload, "review": ReviewPayload, "measurement": MeasurementPayload}


def validate_payload(kind, payload):
    if kind not in PAYLOADS:
        raise ValidationError("Use a registered operational record kind.")
    parsed = PAYLOADS[kind](data=payload)
    parsed.is_valid(raise_exception=True)
    return json_value(parsed.validated_data)


def timezone_for(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValidationError({"timezone": "Expected an IANA timezone."}) from exc


def instant(value):
    if value is None:
        return None
    field = serializers.DateTimeField()
    StrictSerializer._check_type(field, value)
    parsed = field.run_validation(value)
    return parsed


def deadline_projection(properties, timezone_name="UTC", *, now=None):
    zone, now = timezone_for(timezone_name), now or timezone.now()
    legacy, precise = properties.get("due_date"), properties.get("due_at")
    planned = date.fromisoformat(legacy) if legacy else None
    at = instant(precise)
    local_date = at.astimezone(zone).date() if at else None
    conflict = bool(planned and local_date and planned != local_date)
    source = "conflict" if conflict else "due_at" if at else "due_date" if planned else None
    return {
        "source": source,
        "timezone": timezone_name,
        "conflict": conflict,
        "due_date": legacy,
        "due_at": precise,
        "effective_at": None if conflict else precise,
        "effective_date": None
        if conflict
        else (local_date or planned).isoformat()
        if (local_date or planned)
        else None,
        "overdue": bool(at and at < now or planned and planned < now.astimezone(zone).date()),
    }


def require_reconciled(obj):
    if legacy_pending(obj):
        raise ValidationError({"code": "operational_backfill_required"})


def legacy_pending(obj):
    from plane.radar.models import OperationalRecord

    # Current readers never fetch the potentially huge archive JSON. Legacy writes
    # are blocked in this application; an old writer changes its provenance pointer.
    marker = (
        OperationalRecord.objects.filter(workspace=obj.workspace, object=obj)
        .values_list("backfill_hash", "last_provenance__command_name")
        .first()
    )
    return bool(marker and (not marker[0] or marker[1] != "BackfillOperationalHistory"))


def append_entry(obj, kind, payload):
    from plane.radar.models import OperationalEntry
    from plane.radar.commands.context import command_actor, command_now, command_user_id
    from plane.radar.commands.primitives_semantic import touch_objects

    require_reconciled(obj)
    payload = validate_payload(kind, json_value(payload))
    actor = command_actor()
    touch_objects([obj], command_user_id())
    obj.refresh_from_db(fields=["version"])
    return OperationalEntry.objects.create(
        workspace=obj.workspace,
        object=obj,
        kind=kind,
        payload=payload,
        object_version=obj.version,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        occurred_at=command_now(),
        origin="command",
        evidence_id=payload.get("evidence_id"),
        created_by_id=command_user_id(),
        updated_by_id=command_user_id(),
    )


def current_entries(obj):
    from plane.radar.models import OperationalEntry

    return {
        kind: OperationalEntry.objects.filter(workspace=obj.workspace, object=obj, kind=kind)
        .only("id", "payload", "origin", "created_provenance_id")
        .order_by("-created_at", "-id")
        .first()
        for kind in KINDS
    }


def operation_projection(obj, properties=None, *, timezone_name="UTC", now=None):
    from plane.radar.commands.queries import effective_values

    properties = effective_values(obj) if properties is None else properties
    deadline = deadline_projection(properties, timezone_name, now=now) if obj.object_type.key == "action" else None
    entries = current_entries(obj)
    pending = legacy_pending(obj)
    executors = list(
        active_relations(obj.workspace)
        .filter(source=obj, relation_type__key="assigned_to")
        .order_by("created_at", "id")
        .values_list("target_id", flat=True)
    )
    result = {
        "schema_version": 1,
        "migration_required": pending,
        "deadline": deadline,
        "executors": [str(pk) for pk in executors],
        "origins": {},
        "operation_data": {},
    }
    for kind, entry in entries.items():
        if entry is None:
            continue
        payload = entry.payload.copy()
        if kind == "measurement":
            if not {"current", "measured_at"}.issubset(properties):
                continue
            payload.update(value=properties["current"], measured_at=properties["measured_at"])
        result["origins"][kind] = {
            "entry_id": str(entry.pk),
            "origin": entry.origin,
            "provenance_id": str(entry.created_provenance_id) if entry.created_provenance_id else None,
        }
        if kind == "delegation":
            changed = set(payload["executor_ids"]) != set(result["executors"]) or instant(payload["due_at"]) != instant(
                properties.get("due_at")
            )
            payload.update(executor_ids=result["executors"], due_at=properties.get("due_at"), terms_changed=changed)
            if changed:
                payload.update(state="changed", accepted_at=None, acceptances={}, next_review_at=None)
            result["operation_data"]["assignment"] = payload
        else:
            result["operation_data"][kind] = payload
    return result


def history_page(workspace, obj, *, kind=None, limit=20, cursor=None):
    from plane.radar.models import OperationalEntry

    if kind is not None and kind not in KINDS or type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("Use a registered kind and a page size of 1–100.")
    rows = (
        OperationalEntry.objects.filter(workspace=workspace, object=obj)
        .select_related("created_provenance")
        .only(
            "id",
            "kind",
            "schema_version",
            "object_version",
            "occurred_at",
            "created_at",
            "actor_type",
            "actor_id",
            "origin",
            "source_record_id",
            "source_provenance_id",
            "created_provenance_id",
            "payload",
            "created_provenance__id",
            "created_provenance__command_id",
        )
    )
    if kind:
        rows = rows.filter(kind=kind)
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if set(token) != {"object", "kind", "at", "id"} or token["object"] != str(obj.pk) or token["kind"] != kind:
                raise ValueError()
            at, pk = instant(token["at"]), UUID(token["id"])
            rows = rows.filter(Q(created_at__lt=at) | Q(created_at=at, pk__lt=pk))
        except (ValueError, TypeError, KeyError, UnicodeError, ValidationError) as exc:
            raise ValidationError({"cursor": "Invalid history cursor for this Object/kind."}) from exc
    selected = list(rows.order_by("-created_at", "-id")[: limit + 1])
    next_cursor = None
    if len(selected) > limit:
        last = selected[limit - 1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {"object": str(obj.pk), "kind": kind, "at": last.created_at.isoformat(), "id": str(last.pk)}
            ).encode()
        ).decode()
    return {"items": [entry_result(row) for row in selected[:limit]], "next_cursor": next_cursor}


def entry_result(row):
    provenance = row.created_provenance
    return {
        "id": str(row.pk),
        "kind": row.kind,
        "schema_version": row.schema_version,
        "object_version": row.object_version,
        "occurred_at": json_value(row.occurred_at),
        "recorded_at": json_value(row.created_at),
        "actor_type": row.actor_type,
        "actor_id": json_value(row.actor_id),
        "origin": row.origin,
        "source_record_id": json_value(row.source_record_id),
        "source_provenance_id": json_value(row.source_provenance_id),
        "provenance_id": json_value(row.created_provenance_id),
        "command_id": json_value(provenance.command_id) if provenance else None,
        "payload": row.payload,
    }
