"""Deterministic management operations shared by the UI and the CoS adapter."""

from .context import command_now
from django.utils.html import escape
from rest_framework.exceptions import PermissionDenied, ValidationError
from .access import is_workspace_admin
from plane.radar.models import PersonIdentity, Relation, RuntimeCredential
from plane.radar.operational import append_entry, require_reconciled
from plane.radar.runtime_identity import bind_identity, runtime_identities
from plane.radar.mutation import json_value
from . import descriptors
from . import primitives_semantic as semantic
from .context import command_actor, command_user_id
from .queries import validate_evidence, lookup_object, effective_values
from .results import object_result
from .handlers import link_objects, create_typed_object, patch_object_properties
from .execution import emit

from .capabilities import RuntimeOperations

OPERATIONS = RuntimeOperations()


def references(workspace, name, data):
    from .capabilities import get_capability

    return get_capability(name).references(workspace, data)


def delegation_references(workspace, name, data):
    refs = set(
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
    identities = runtime_identities(workspace, context).filter(object_id__in=refs)
    if set(identities.values_list("object_id", flat=True)) != refs:
        raise PermissionDenied("Every reference must have an explicit identity in this context.")


def identify_runtime_object(workspace, obj, context):
    return bind_identity(workspace, obj, context, user_id=command_user_id(), at=command_now())


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
    require_reconciled(action)
    from plane.radar.active import active_definitions

    if (
        not active_definitions(workspace)
        .filter(object_type=action.object_type, key="due_at", value_type="datetime")
        .exists()
    ):
        raise ValidationError(
            "Delegation requires an active due_at datetime definition; reconcile local metadata first."
        )
    if descriptors.is_terminal(action):
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
        and is_workspace_admin(actor, workspace)
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
        # The commitment lifecycle declares which states delegation supersedes.
        transition = descriptors.declared_target(edge.source, "DelegateAction", required=False)
        state = descriptors.state_property(edge.source)
        if transition and effective_values(edge.source).get(state) in transition["from"]:
            patch_object_properties(workspace, edge.source, {state: transition["to"]})
    for edge in Relation.objects.filter(workspace=workspace, source=action, relation_type__key="assigned_to"):
        semantic.remove_relation(actor=actor, workspace=workspace, relation_id=edge.pk)
    for person in executors:
        link_objects(workspace, action, person, "assigned_to")
    patch_object_properties(workspace, action, {"due_at": data["due_at"].isoformat()})
    append_entry(
        action,
        "delegation",
        {
            "executor_ids": [str(p.pk) for p in executors],
            "due_at": data["due_at"],
            "next_review_at": data.get("next_review_at"),
            "state": "proposed",
            "accepted_at": None,
            "acceptances": {},
            "proposed_by": actor.actor_id,
            "proposed_at": command_now(),
        },
    )
    emit("ActionDelegated", {"action_id": action.pk, "executor_ids": [p.pk for p in executors], "state": "proposed"})
    return object_result(action)


def _review(workspace, data):
    obj = lookup_object(workspace, data["target_id"])
    require_reconciled(obj)
    if obj.object_type.key == "person":
        raise ValidationError("ReviewObject does not review a Person.")
    evidence = lookup_object(workspace, data["evidence_id"], {"document"})
    validate_evidence(evidence)
    disposition = data.get("disposition")
    if disposition:
        # Disposition mappings are ReviewObject transitions declared by the type lifecycle.
        transition = descriptors.declared_target(obj, "ReviewObject", disposition, required=False)
        if transition is None:
            raise ValidationError("Disposition is not valid for this type/status.")
        patch_object_properties(workspace, obj, {descriptors.state_property(obj): transition["to"]})
    review = {**data, "actor": command_actor().actor_id, "at": command_now()}
    append_entry(obj, "review", review)
    emit("ObjectReviewed", {"object_id": obj.pk, "evidence_id": evidence.pk, "disposition": disposition})
    return object_result(obj)


def _measure(workspace, data):
    obj = lookup_object(workspace, data["indicator_id"], {"indicator"})
    require_reconciled(obj)
    values = effective_values(obj)
    if values["status"] != "active":
        raise ValidationError("Measurement requires an active Indicator.")
    if data["measured_at"] > command_now():
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
    measurement = json_value(
        {
            "value": data["value"],
            "measured_at": data["measured_at"],
            "evidence_id": evidence.pk,
            "actor": command_actor().actor_id,
            "at": command_now(),
        }
    )
    append_entry(obj, "measurement", measurement)
    emit("MeasurementRecorded", {"indicator_id": obj.pk, "evidence_id": evidence.pk, "value": data["value"]})
    return object_result(obj)


def dispatch(workspace, name, data):
    from .capabilities import get_capability

    return get_capability(name).execute(workspace, data)
