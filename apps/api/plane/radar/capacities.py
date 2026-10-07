"""Effective capacities of a human actor over one Object (Core U1 C20).

Advisory and recomputed on every read; each write is still revalidated by its command.
Lifecycle transitions and actions with complete probe inputs are exercised by the real
planner under a rolled-back savepoint, so guards are not duplicated here.
"""

from django.db import transaction
from django.db.models import Q
from django.utils.html import strip_tags
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from plane.db.models import WorkspaceMember
from plane.radar.active import active_relations, active_values
from plane.radar.commands import descriptors
from plane.radar.commands.access import require_human_membership, role_can_write
from plane.radar.commands.capabilities import CAPABILITIES, get_guard, resolve
from plane.radar.commands.effects import plan_command
from plane.radar.commands.handlers import (
    field_restriction,
    relation_restriction,
    relation_review,
    requires_human_review,
    update_restrictions,
)
from plane.radar.commands.primitives_semantic import effective_values, get_active_object, property_definitions
from plane.radar.commands.rules import effective_invariants
from plane.radar.mutation import json_value
from plane.radar.workspace_schema import lock_schema

PROBE_TEXT = "Availability probe"


def failure(exc: APIException) -> dict:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    code = detail.get("code") if isinstance(detail.get("code"), str) else None
    if code is None:
        code = (
            "not_permitted"
            if isinstance(exc, PermissionDenied)
            else "unavailable"
            if isinstance(exc, NotFound)
            else "requirements_not_met"
            if isinstance(exc, ValidationError)
            else "conflict"
        )
    return {"available": False, "reason": str(code), "detail": descriptors.error_detail(exc)}


def probe(actor, workspace, name, data) -> dict:
    """Plan a command as this actor without persisting anything; failures explain unavailability."""
    capability = CAPABILITIES[name]
    try:
        parsed = capability.input_type(data=json_value(data))
        parsed.is_valid(raise_exception=True)
        with transaction.atomic():
            plan_command(actor=actor, workspace=workspace, name=name, data=parsed.validated_data)
            review = requires_human_review(workspace, actor, None, name, parsed.validated_data)
            transaction.set_rollback(True)
    except APIException as exc:
        return failure(exc)
    return {"available": True, "reason": None, "detail": None, "requires_review": review}


def object_capacities(*, actor, workspace, object_id, relation_ids=None) -> dict:
    require_human_membership(actor, workspace, write=False)
    revision = lock_schema(workspace)
    obj = get_active_object(workspace, object_id)
    role = WorkspaceMember.objects.get(workspace=workspace, member_id=actor.actor_id, is_active=True).role
    can_write = role_can_write(role)
    definitions = property_definitions(obj)
    values = effective_values(obj)
    stored = set(active_values(workspace).filter(object=obj).values_list("definition__key", flat=True))
    errors = []
    try:
        lifecycle = descriptors.effective_lifecycle(obj.object_type, definitions)
        derived = {r["result"] for r in effective_invariants(obj.object_type, definitions) if r["kind"] == "product"}
    except ValidationError as exc:
        lifecycle, derived = None, set()
        errors.append({"section": "rules", "detail": descriptors.error_detail(exc)})
    presentation = descriptors.layout(obj.object_type, definitions)
    if presentation["diagnostic"]:
        errors.append({"section": "presentation", "detail": presentation["diagnostic"]})
    presentation["legacy_notes"] = presentation["content"]["role"] == "notes" and bool(strip_tags(obj.content).strip())
    blocked = "invalid_metadata" if any(error["section"] == "rules" for error in errors) else None
    readonly = None if can_write else "read_only_access"

    state, transitions = None, []
    if lifecycle:
        prop = lifecycle["property"]
        current = values.get(prop)
        terminal = definitions[prop].config.get("terminal", [])
        state = {"property": prop, "current": current, "initial": lifecycle["initial"], "terminal": current in terminal}
        for declared in lifecycle["transitions"]:
            if current not in declared["from"]:
                continue
            name = declared.get("capability", descriptors.DEFAULT_TRANSITION)
            guard = get_guard(declared["guard"]) if "guard" in declared else None
            entry = {
                "to": declared["to"],
                "capability": name,
                "guard": declared.get("guard"),
                "parameter": declared.get("parameter"),
                "stamp": declared.get("stamp"),
                "human_only": bool(guard and guard.human_only) or CAPABILITIES[name].human_only,
                "available": False,
                "reason": readonly,
                "detail": None,
                "requires_review": False,
            }
            if readonly is None and name == descriptors.DEFAULT_TRANSITION:
                entry.update(
                    probe(actor, workspace, name, {"object_id": obj.pk, "set_properties": {prop: declared["to"]}})
                )
            elif readonly is None and CAPABILITIES[name].object_action:
                entry.update(available=True, reason="requires_input")
            elif readonly is None:
                # Context-bound runtime operations (review dispositions, delegation) are not page actions.
                entry["reason"] = "runtime_context"
            transitions.append(entry)

    stamps = {
        t["stamp"]: t.get("capability", descriptors.DEFAULT_TRANSITION)
        for t in (lifecycle or {}).get("transitions", [])
        if "stamp" in t
    }
    restrictions = update_restrictions(workspace, obj)
    fields = {}
    for key, definition in definitions.items():
        options, governed_by = None, []
        reason = readonly or blocked
        if reason is None and key in derived:
            reason = "derived"
        elif reason is None and state and key == state["property"]:
            reason = "lifecycle_state"
            options = [state["current"]] + [
                t["to"]
                for t in transitions
                if t["capability"] == descriptors.DEFAULT_TRANSITION and not t["guard"] and t["available"]
            ]
            governed_by = sorted({t["capability"] for t in transitions})
        elif reason is None and key in stamps:
            reason, governed_by = "lifecycle_stamp", [stamps[key]]
        elif reason is None:
            reason = field_restriction(restrictions, key)
            governed_by = ["RecordMeasurement"] if reason == "measurement" else []
        removable = (
            reason is None
            and key in stored
            and not definition.is_required
            and "default" not in definition.config
            and restrictions["remove"] is None
        )
        fields[key] = {
            "editable": reason is None or reason == "lifecycle_state" and len(options) > 1,
            "removable": removable,
            "reason": reason,
            "options": options,
            "governed_by": governed_by,
        }

    envelope_reason = readonly or blocked or restrictions["envelope"]
    envelope = {key: {"editable": envelope_reason is None, "reason": envelope_reason} for key in ("title", "content")}

    relations = {}
    edges = (
        active_relations(workspace)
        .filter(Q(source=obj) | Q(target=obj))
        .select_related("relation_type", "source__object_type", "target__object_type")
    )
    if relation_ids is not None:
        edges = edges.filter(pk__in=relation_ids)
    else:
        edges = edges.order_by("pk")[:50]
    for edge in edges:
        reason = readonly
        if reason is None and edge.relation_type.cardinality == "1..1":
            reason = "mandatory_relation"
        if reason is None:
            reason = relation_restriction(workspace, edge, edge.source, edge.target)
        relations[str(edge.pk)] = {
            "removable": reason is None,
            "reason": reason,
            "requires_review": reason is None and relation_review(workspace, "UnlinkObjects", {"relation_id": edge.pk}),
        }

    actions = []
    for capability in CAPABILITIES.values():
        types = capability.action_types()
        if not types or "*" not in types and obj.object_type.key not in types:
            continue
        entry = {
            "capability": capability.name,
            "target_field": capability.object_action,
            "prefill": {capability.object_action: str(obj.pk)},
            "transition": None,
            "human_only": capability.human_only,
            "available": False,
            "reason": readonly or blocked,
            "detail": None,
            "requires_review": False,
        }
        actions.append(entry)
        if entry["reason"]:
            continue
        if capability.lifecycle_types:
            declared = descriptors.declared_target(obj, capability.name, required=False)
            if declared is None or state is None or state["current"] not in declared["from"]:
                entry["reason"] = "not_declared_from_state"
                continue
            entry["transition"] = {"to": declared["to"], "stamp": declared.get("stamp")}
        try:
            if capability.action_prefill:
                entry["prefill"].update(resolve(capability.action_prefill)(workspace, actor, obj))
        except APIException as exc:
            entry.update(failure(exc))
            continue
        fields_contract = capability.input_type().fields
        missing = [
            key
            for key, field in fields_contract.items()
            if field.required and key not in entry["prefill"] and not isinstance(field, serializers.CharField)
        ]
        if missing:
            # Required references come from the user; the command revalidates every guard.
            entry.update(available=True, reason="requires_input")
            continue
        data = {
            **{
                key: PROBE_TEXT
                for key, field in fields_contract.items()
                if field.required and key not in entry["prefill"]
            },
            **entry["prefill"],
        }
        entry.update(probe(actor, workspace, capability.name, data))

    return {
        "schema_revision": revision,
        "object": {"id": str(obj.pk), "version": obj.version, "object_type": obj.object_type.key},
        "can_write": can_write,
        "metadata_errors": errors,
        "presentation": presentation,
        "envelope": envelope,
        "state": state,
        "fields": fields,
        "transitions": transitions,
        "actions": actions,
        "relations": relations,
    }
