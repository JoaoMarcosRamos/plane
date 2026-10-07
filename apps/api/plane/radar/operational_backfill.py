"""Reviewed, audited and idempotent migration from the untyped legacy archive."""

import hashlib
import json
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError

from plane.radar.models import Object, OperationalRecord, OperationalEntry, PropertyDefinition, PropertyValue
from plane.radar.operational import validate_payload, instant, deadline_projection, timezone_for
from plane.radar.active import active_relations
from plane.radar.commands.control import require_workspace_admin
from plane.radar.commands.execution import run_internal
from plane.radar.workspace_schema import lock_schema


def data_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def legacy_items(record):
    data = record.data
    if not isinstance(data, dict) or set(data) - {"assignment", "review", "reviews", "measurement", "measurements"}:
        raise ValidationError("Legacy data has unsupported top-level fields; export and reconcile explicitly.")
    if "assignment" in data:
        raw = data["assignment"]
        if not isinstance(raw, dict):
            raise ValidationError("Assignment must be an object.")
        payload = {key: value for key, value in raw.items() if key != "executor_id"}
        payload["executor_ids"] = payload.get("executor_ids") or (
            [raw["executor_id"]] if raw.get("executor_id") else []
        )
        yield "delegation", 0, validate_payload("delegation", payload), raw
    for kind, many in (("review", "reviews"), ("measurement", "measurements")):
        rows = data.get(many, [data[kind]] if kind in data else [])
        if not isinstance(rows, list):
            raise ValidationError(f"{many} must be a list.")
        if rows and kind in data and data[kind] != rows[-1]:
            raise ValidationError(f"The current {kind} diverges from its history tail.")
        for index, raw in enumerate(rows):
            yield kind, index, validate_payload(kind, raw), raw


def report_record(workspace, record, timezone_name):
    obj = record.object
    result = {
        "record_id": str(record.pk),
        "object_id": str(obj.pk),
        "object_version": obj.version,
        "data_hash": data_hash(record.data),
        "entries": {},
        "divergences": [],
        "blockers": [],
    }
    result["already_imported"] = record.backfill_hash == result["data_hash"]
    try:
        items = list(legacy_items(record))
        refs = set()
        for kind, index, payload, raw in items:
            result["entries"][kind] = result["entries"].get(kind, 0) + 1
            refs.update(payload.get("executor_ids", []))
            refs.update(
                acceptance["evidence_id"]
                for acceptance in payload.get("acceptances", {}).values()
                if "evidence_id" in acceptance
            )
            if payload.get("evidence_id"):
                refs.add(payload["evidence_id"])
            if payload.get("target_id", str(obj.pk)) != str(obj.pk):
                raise ValidationError("Legacy review target is not this Object.")
        if Object.all_objects.filter(workspace=workspace, pk__in=refs).count() != len(refs):
            raise ValidationError("Legacy references are unavailable in this workspace.")
        executors = {pk for _, _, payload, _ in items for pk in payload.get("executor_ids", [])}
        if Object.all_objects.filter(workspace=workspace, object_type__key="person", pk__in=executors).count() != len(
            executors
        ):
            raise ValidationError("Legacy executors must be Persons.")
        evidence = {payload["evidence_id"] for _, _, payload, _ in items if payload.get("evidence_id")}
        evidence.update(
            acceptance["evidence_id"]
            for _, _, payload, _ in items
            for acceptance in payload.get("acceptances", {}).values()
            if acceptance.get("evidence_id")
        )
        if Object.all_objects.filter(workspace=workspace, object_type__key="document", pk__in=evidence).count() != len(
            evidence
        ):
            raise ValidationError("Legacy evidence must be Documents.")
        properties = {
            row.definition.key: row.value
            for row in PropertyValue.objects.filter(workspace=workspace, object=obj).select_related("definition")
        }
        result["deadlines"] = {key: properties.get(key) for key in ("due_at", "due_date")}
        delegation = next((payload for kind, _, payload, _ in items if kind == "delegation"), None)
        if delegation:
            if obj.object_type.key != "action":
                raise ValidationError("Legacy delegation must belong to an Action.")
            definition = PropertyDefinition.objects.filter(
                workspace=workspace, object_type=obj.object_type, key="due_at"
            ).first()
            if definition is None or definition.value_type != "datetime":
                raise ValidationError("Install a compatible due_at datetime definition before applying backfill.")
            if (
                not result["already_imported"]
                and properties.get("due_at") is not None
                and instant(properties["due_at"]) != instant(delegation["due_at"])
            ):
                raise ValidationError("Canonical due_at conflicts with the archive; no automatic overwrite.")
            projected = deadline_projection({**properties, "due_at": delegation["due_at"]}, timezone_name)
            if projected["conflict"]:
                result["divergences"].append("deadline_conflict")
            assigned = set(
                str(pk)
                for pk in active_relations(workspace)
                .filter(source=obj, relation_type__key="assigned_to")
                .values_list("target_id", flat=True)
            )
            result["assigned_executor_ids"] = sorted(assigned)
            if assigned != set(delegation["executor_ids"]):
                result["divergences"].append("executor_sets_differ_preserve_relations")
            if not obj.object_type.is_active or obj.deleted_at:
                result["divergences"].append("historical_object_no_operational_context")
        if record.backfill_hash and record.backfill_hash != result["data_hash"]:
            raise ValidationError("Archive changed after import; export and reconcile instead of repeating backfill.")
        if record.backfill_hash and (
            not record.last_provenance_id or record.last_provenance.command_name != "BackfillOperationalHistory"
        ):
            raise ValidationError(
                "An old writer touched the imported archive; reconcile before activating new writers."
            )
        result["already_imported"] = record.backfill_hash == result["data_hash"]
    except ValidationError as exc:
        from plane.radar.commands.descriptors import error_detail

        result["blockers"].append(error_detail(exc))
    return result


def inventory(workspace, timezone_name="UTC"):
    timezone_for(timezone_name)
    revision = lock_schema(workspace)
    rows = [
        report_record(workspace, record, timezone_name)
        for record in OperationalRecord.all_objects.filter(workspace=workspace)
        .select_related("object__object_type")
        .order_by("pk")
        .iterator()
    ]
    report = {
        "schema_revision": revision,
        "timezone": timezone_name,
        "records": rows,
        "counts": {
            "records": len(rows),
            "entries": sum(sum(row["entries"].values()) for row in rows),
            "blocking_records": sum(bool(row["blockers"]) for row in rows),
            "divergent_records": sum(bool(row["divergences"]) for row in rows),
        },
    }
    report["reviewed_hash"] = data_hash(report)
    return report


@transaction.atomic
def preview_backfill(*, actor, workspace, timezone_name="UTC"):
    require_workspace_admin(actor, workspace)
    return inventory(workspace, timezone_name)


@transaction.atomic
def backfill(*, actor, workspace, reviewed_hash, timezone_name="UTC"):
    def operation():
        require_workspace_admin(actor, workspace)
        plan = inventory(workspace, timezone_name)
        if plan["counts"]["blocking_records"]:
            raise ValidationError({"code": "backfill_conflict", "report": plan})
        if all(row["already_imported"] for row in plan["records"]):
            return {"created_entries": 0, "materialized_deadlines": 0, "reviewed_hash": reviewed_hash}
        if reviewed_hash != plan["reviewed_hash"]:
            raise ValidationError({"code": "backfill_conflict", "report": plan})
        created, deadlines = 0, 0
        from plane.radar.commands.primitives_semantic import touch_objects, validate_value

        for record in (
            OperationalRecord.all_objects.filter(workspace=workspace)
            .select_related("object__object_type")
            .order_by("pk")
        ):
            if record.backfill_hash:
                continue
            obj = record.object
            for kind, index, payload, raw in legacy_items(record):
                if kind == "delegation":
                    definition = PropertyDefinition.objects.get(
                        workspace=workspace, object_type=obj.object_type, key="due_at"
                    )
                    stored = PropertyValue.objects.filter(object=obj, definition=definition).first()
                    if stored is None:
                        value = validate_value(definition, raw["due_at"], workspace)
                        PropertyValue.objects.create(
                            workspace=workspace,
                            object=obj,
                            definition=definition,
                            value=value,
                            created_by_id=actor.actor_id,
                            updated_by_id=actor.actor_id,
                        )
                        touch_objects([obj], actor.actor_id)
                        deadlines += 1
                OperationalEntry.objects.create(
                    workspace=workspace,
                    object=obj,
                    kind=kind,
                    payload=payload,
                    origin="legacy",
                    origin_key=f"legacy:{record.pk}:{kind}:{index}",
                    source_record=record,
                    source_provenance_id=record.last_provenance_id,
                    source_data=raw,
                    occurred_at=instant(raw.get("at") or raw.get("proposed_at")),
                    object_version=None,
                    actor_type="unknown",
                    actor_id=UUID(raw["actor"])
                    if raw.get("actor")
                    else UUID(raw["proposed_by"])
                    if raw.get("proposed_by")
                    else None,
                    evidence_id=payload.get("evidence_id"),
                    created_by_id=actor.actor_id,
                    updated_by_id=actor.actor_id,
                )
                created += 1
            record.backfill_hash = data_hash(record.data)
            record.save(update_fields=["backfill_hash"])
        return {"created_entries": created, "materialized_deadlines": deadlines, "reviewed_hash": reviewed_hash}

    return run_internal(actor=actor, workspace=workspace, name="BackfillOperationalHistory", operation=operation)


def export_workspace(workspace):
    """Streaming compatibility/archive export; not a write or an automatic rollback."""
    for record in OperationalRecord.all_objects.filter(workspace=workspace).order_by("pk").iterator():
        yield {
            "type": "legacy_archive",
            "record_id": str(record.pk),
            "object_id": str(record.object_id),
            "data": record.data,
            "data_hash": data_hash(record.data),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "created_by_id": str(record.created_by_id) if record.created_by_id else None,
            "updated_by_id": str(record.updated_by_id) if record.updated_by_id else None,
        }
    for entry in (
        OperationalEntry.all_objects.filter(workspace=workspace)
        .select_related("created_provenance", "source_provenance")
        .order_by("created_at", "pk")
        .iterator()
    ):
        from plane.radar.operational import entry_result

        yield {
            "type": "operational_entry",
            "object_id": str(entry.object_id),
            **entry_result(entry),
            "source_data": entry.source_data,
        }
