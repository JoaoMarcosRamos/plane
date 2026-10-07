"""Deterministic management operations shared by the UI and the CoS adapter."""

from uuid import uuid4
from django.utils import timezone
from django.utils.html import escape
from rest_framework.exceptions import PermissionDenied, ValidationError
from plane.db.models import WorkspaceMember
from plane.radar.models import OperationalRecord, PersonIdentity, Relation, RuntimeCredential, RuntimeObjectIdentity
from plane.radar.ontology.schema import load_schema
from plane.radar.mutation import json_value
from . import primitives_semantic as semantic
from .context import command_actor, command_user_id
from .queries import validate_evidence, lookup_object, effective_values
from .results import object_result
from .handlers import link_objects, create_typed_object, patch_object_properties
from .execution import emit

OPERATIONS = {
    "capture_issue": "CaptureIssue",
    "delegate": "DelegateAction",
    "review": "ReviewObject",
    "record_measurement": "RecordMeasurement",
}


def references(workspace, name, data):
    refs = {
        data[k]
        for k in ("action_id", "target_id", "indicator_id", "owner_id", "evidence_id", "executor_id")
        if k in data
    }
    refs.update(data.get("executor_ids", []))
    if name == "DelegateAction":
        refs.update(
            Relation.objects.filter(
                workspace=workspace, source_id=data["action_id"], relation_type__key="assigned_to"
            ).values_list("target_id", flat=True)
        )
        refs.update(
            Relation.objects.filter(
                workspace=workspace,
                target_id=data["action_id"],
                relation_type__key="commits_to",
                source__object_type__key="commitment",
            ).values_list("source_id", flat=True)
        )
        refs.update(
            Relation.objects.filter(
                workspace=workspace, source_id=data["action_id"], relation_type__key="owned_by"
            ).values_list("target_id", flat=True)
        )
    return refs


def check_context(workspace, data, refs):
    context = data["context"]
    identities = RuntimeObjectIdentity.objects.filter(workspace=workspace, object_id__in=refs, context=context)
    if set(identities.values_list("object_id", flat=True)) != refs:
        raise PermissionDenied("Every reference must have an explicit identity in this context.")


def identify_runtime_object(workspace, obj, context):
    existing = RuntimeObjectIdentity.objects.filter(workspace=workspace, object=obj).first()
    if existing:
        if existing.context != context:
            raise PermissionDenied("Creation cannot change the management context.")
        return
    spec = load_schema()["object_types"].get(obj.object_type.key)
    if spec is None:
        raise ValidationError({"code": "unsupported_schema"})
    prefix = spec["prefix"]
    RuntimeObjectIdentity.objects.create(
        workspace=workspace,
        object=obj,
        context=context,
        external_id=f"{prefix}-{timezone.now():%Y%m%d}-{uuid4().hex[:6].upper()}",
        created_by_id=command_user_id(),
        updated_by_id=command_user_id(),
    )


def _record(workspace, obj, values):
    record, _ = OperationalRecord.objects.get_or_create(
        workspace=workspace, object=obj, defaults={"created_by_id": command_user_id()}
    )
    record.data = {**record.data, **json_value(values)}
    record.updated_by_id = command_user_id()
    record.save()
    semantic.touch_objects([obj], command_user_id())


def _document(workspace, context, title, source, text):
    doc = create_typed_object(workspace, "document", title, {"source_system": source}, content=f"<p>{escape(text)}</p>")
    identify_runtime_object(workspace, doc, context)
    return doc


def _capture(workspace, data):
    case = create_typed_object(workspace, "case", data["case_title"], {})
    issue = create_typed_object(
        workspace,
        "management_item",
        data["title"],
        {"kind": "issue", **({"priority": data["priority"]} if "priority" in data else {})},
    )
    for obj in (case, issue):
        identify_runtime_object(workspace, obj, data["context"])
    evidence = _document(workspace, data["context"], data["evidence_title"], data["source"], data["source"])
    link_objects(workspace, case, issue, "contains")
    link_objects(workspace, evidence, issue, "evidences")
    if "owner_id" in data:
        link_objects(workspace, issue, lookup_object(workspace, data["owner_id"], {"person"}), "owned_by")
    emit("IssueCaptured", {"case_id": case.pk, "issue_id": issue.pk, "evidence_id": evidence.pk})
    return object_result(issue)


def _delegate(workspace, data):
    action = lookup_object(workspace, data["action_id"], {"action"})
    if effective_values(action)["status"] not in {"todo", "in_progress", "waiting"}:
        raise ValidationError("Only an active Action can be delegated.")
    actor = command_actor()
    user_id = actor.actor_id if actor.actor_type == "human" else actor.on_behalf_of
    identity = PersonIdentity.objects.filter(workspace=workspace, user_id=user_id, is_active=True).first()
    credential = (
        RuntimeCredential.objects.filter(
            pk=actor.metadata.get("credential_id"),
            workspace=workspace,
            actor_id=actor.actor_id,
            context=data["context"],
            is_active=True,
        ).first()
        if actor.actor_type == "agent"
        else None
    )
    manager = (
        bool(credential and credential.is_manager)
        or actor.actor_type == "human"
        and (
            workspace.owner_id == user_id
            or WorkspaceMember.objects.filter(workspace=workspace, member_id=user_id, is_active=True, role=20).exists()
        )
    )
    if not manager and (
        identity is None
        or not Relation.objects.filter(
            workspace=workspace, source=action, target=identity.person, relation_type__key="owned_by"
        ).exists()
    ):
        raise PermissionDenied("Delegation requires the owner or a configured context manager.")
    executors = [
        lookup_object(workspace, pk, {"person"})
        for pk in dict.fromkeys(data.get("executor_ids") or [data["executor_id"]])
    ]
    for edge in Relation.objects.filter(
        workspace=workspace, target=action, relation_type__key="commits_to", source__object_type__key="commitment"
    ).select_related("source"):
        if effective_values(edge.source).get("status") == "confirmed":
            patch_object_properties(workspace, edge.source, {"status": "superseded"})
    for edge in Relation.objects.filter(workspace=workspace, source=action, relation_type__key="assigned_to"):
        semantic.remove_relation(actor=actor, workspace=workspace, relation_id=edge.pk)
    for person in executors:
        link_objects(workspace, action, person, "assigned_to")
    _record(
        workspace,
        action,
        {
            "assignment": {
                "executor_id": str(executors[0].pk),
                "executor_ids": [str(p.pk) for p in executors],
                "due_at": data["due_at"],
                "next_review_at": data.get("next_review_at"),
                "state": "proposed",
                "accepted_at": None,
                "acceptances": {},
                "proposed_by": actor.actor_id,
                "proposed_at": timezone.now(),
            }
        },
    )
    emit("ActionDelegated", {"action_id": action.pk, "executor_ids": [p.pk for p in executors], "state": "proposed"})
    return object_result(action)


def _review(workspace, data):
    obj = lookup_object(workspace, data["target_id"], set(load_schema()["object_types"]) - {"person"})
    evidence = lookup_object(workspace, data["evidence_id"], {"document"})
    validate_evidence(evidence)
    disposition = data.get("disposition")
    if disposition:
        transitions = {"management_item": {"resolved": "done"}, "risk": {"resolved": "closed", "accepted": "accepted"}}
        new_status = transitions.get(obj.object_type.key, {}).get(disposition)
        terminal = load_schema()["object_types"][obj.object_type.key]["status"].get("terminal", [])
        if new_status is None or effective_values(obj)["status"] in terminal:
            raise ValidationError("Disposition is not valid for this type/status.")
        patch_object_properties(workspace, obj, {"status": new_status})
    old = OperationalRecord.objects.filter(object=obj).first()
    review = {**data, "actor": command_actor().actor_id, "at": timezone.now()}
    _record(
        workspace,
        obj,
        {"review": review, "reviews": [*(old.data.get("reviews", []) if old else []), json_value(review)]},
    )
    emit("ObjectReviewed", {"object_id": obj.pk, "evidence_id": evidence.pk, "disposition": disposition})
    return object_result(obj)


def _measure(workspace, data):
    obj = lookup_object(workspace, data["indicator_id"], {"indicator"})
    values = effective_values(obj)
    if values["status"] != "active":
        raise ValidationError("Measurement requires an active Indicator.")
    if data["measured_at"] > timezone.now():
        raise ValidationError({"code": "measurement_in_future"})
    if values.get("measured_at"):
        from datetime import datetime

        if data["measured_at"] <= datetime.fromisoformat(values["measured_at"].replace("Z", "+00:00")):
            raise ValidationError({"code": "measurement_out_of_order"})
    if "evidence_id" in data:
        evidence = lookup_object(workspace, data["evidence_id"], {"document"})
        validate_evidence(evidence)
    else:
        evidence = _document(
            workspace, data["context"], data["evidence_title"], data["evidence_source"], data["evidence_text"]
        )
    link_objects(workspace, evidence, obj, "evidences")
    patch_object_properties(workspace, obj, {"current": data["value"], "measured_at": data["measured_at"].isoformat()})
    previous = OperationalRecord.objects.filter(object=obj).first()
    measurement = json_value(
        {
            "value": data["value"],
            "measured_at": data["measured_at"],
            "evidence_id": evidence.pk,
            "actor": command_actor().actor_id,
            "at": timezone.now(),
        }
    )
    _record(
        workspace,
        obj,
        {
            "measurement": measurement,
            "measurements": [*(previous.data.get("measurements", []) if previous else []), measurement],
        },
    )
    emit("MeasurementRecorded", {"indicator_id": obj.pk, "evidence_id": evidence.pk, "value": data["value"]})
    return object_result(obj)


def dispatch(workspace, name, data):
    check_context(workspace, data, references(workspace, name, data))
    return {
        "CaptureIssue": _capture,
        "DelegateAction": _delegate,
        "ReviewObject": _review,
        "RecordMeasurement": _measure,
    }[name](workspace, data)
