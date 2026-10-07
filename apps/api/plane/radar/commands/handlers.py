"""Domain handlers. Only execute_command enters these functions with a write context."""

import hashlib
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from .context import command_now
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from plane.radar.models import (
    ActionCompletion,
    DecisionApproval,
    EvidenceRecord,
    ObjectType,
    PersonIdentity,
    PropertyDefinition,
    Provenance,
    Relation,
    RelationType,
)
from plane.radar.mutation import json_value
from .execution import CommandConflict, emit
from . import descriptors
from . import primitives_objects as objects
from . import primitives_semantic as semantic
from .rules import effective_invariants
from .context import command_context, command_actor, command_user_id
from .queries import (
    lookup_object,
    effective_values,
    decision_evidence_ids,
    current_decision_approval,
    validate_evidence,
)
from .results import object_result, relation_result, property_snapshot_result


def _kind(workspace, key):
    try:
        return RelationType.objects.get(workspace=workspace, key=key, is_active=True)
    except RelationType.DoesNotExist as exc:
        raise ValidationError({"code": "unsupported_schema", "relation": key}) from exc


def _snapshot(obj):
    return json_value(
        {
            "id": obj.pk,
            "version": obj.version,
            "title": obj.title,
            "content": obj.content,
            "object_type": obj.object_type.key,
            "properties": effective_values(obj),
        }
    )


def references(workspace, name, data):
    from .capabilities import get_capability

    return get_capability(name).references(workspace, data)


def creation_capability(workspace, data):
    """Composed authority of CreateObject: the creation capability declared by the type."""
    name = descriptors.creation_capability_name(objects.get_object_type(workspace, data["object_type_id"]))
    return None if name == descriptors.DEFAULT_CREATION else name


def creation_references(workspace, name, data):
    selected = objects.get_object_type(workspace, data["object_type_id"])
    capability, parameters = creation_parameters(selected, data.get("parameters", {}))
    return capability.references(workspace, parameters) if capability.creation.parameters else set()


def unlink_references(workspace, name, data):
    relation = Relation.all_objects.filter(pk=data["relation_id"], workspace=workspace).first()
    if relation is None:
        raise NotFound("Relation not found in this workspace.")
    return {relation.source_id, relation.target_id}


def approval_references(workspace, name, data):
    return decision_evidence_ids(workspace, data["decision_id"])


def transition_guard(workspace, data):
    """Registered guard of the transition an UpdateObject requests, if any."""
    from .capabilities import get_guard

    if not data.get("set_properties"):
        return None, None
    obj = semantic.get_active_object(workspace, data["object_id"])
    name = descriptors.guarded_target(obj, data["set_properties"], "UpdateObject")
    return obj, get_guard(name) if name else None


def update_references(workspace, name, data):
    from .capabilities import resolve

    obj, guard = transition_guard(workspace, data)
    if guard is None or guard.references is None:
        return set()
    return resolve(guard.references)(workspace, obj)


def creation_parameters(selected, parameters):
    """Validate composed-effect parameters against the type's declared creation capability."""
    from .capabilities import get_capability

    capability = get_capability(descriptors.creation_capability_name(selected))
    profile = capability.creation
    if profile.parameters is None:
        if parameters:
            raise ValidationError({"parameters": "This type's creation capability takes no parameters."})
        return capability, {}
    serializer = profile.parameter_type(data=parameters)
    serializer.is_valid(raise_exception=True)
    return capability, serializer.validated_data


def human_only_policy(workspace, name, data):
    from .capabilities import get_capability

    if get_capability(name).human_only:
        return True
    if name != "UpdateObject":
        return False
    _, guard = transition_guard(workspace, data)
    return bool(guard and guard.human_only)


def requires_human_review(workspace, actor, grant, name, data):
    from .capabilities import get_capability, resolve

    capability = get_capability(name)
    if capability.is_human_only(workspace, data) and actor.actor_type != "human":
        raise PermissionDenied("This command is human-only.")
    if grant:
        return actor.actor_type == "agent" or grant.requires_approval
    return bool(capability.review_policy and resolve(capability.review_policy)(workspace, name, data))


def relation_review(workspace, name, data):
    if name == "UnlinkObjects":
        relation = Relation.all_objects.get(pk=data["relation_id"], workspace=workspace)
        if relation.deleted_at:
            return False
        kind = relation.relation_type.key
        return kind in {"owned_by", "requires_consultation", "requires_notification"}
    if name == "LinkObjects":
        kind = RelationType.objects.filter(pk=data["relation_type_id"], workspace=workspace).first()
        if kind and kind.key == "owned_by":
            if Relation.objects.filter(
                workspace=workspace, source_id=data["source_id"], target_id=data["target_id"], relation_type=kind
            ).exists():
                return False
            return Relation.all_objects.filter(
                workspace=workspace, source_id=data["source_id"], relation_type=kind
            ).exists()
    return False


@contextmanager
def _special(name):
    context = command_context()
    old = context.special
    context.special = name
    try:
        yield
    finally:
        context.special = old


def _stale(workspace, obj):
    if obj.object_type.key != "decision":
        return
    for approval in DecisionApproval.objects.filter(workspace=workspace, decision=obj, is_stale=False):
        approval.is_stale = True
        approval.save(update_fields=["is_stale", "updated_at"])
        emit("DecisionApprovalInvalidated", {"decision_id": obj.pk, "decision_approval_id": approval.pk})


def patch_object_properties(workspace, obj, values, remove=()):
    return semantic.patch_properties(actor=command_actor(), workspace=workspace, obj=obj, values=values, remove=remove)


def create_typed_object(
    workspace, key, title, properties, content=None, type_id=None, creation=descriptors.DEFAULT_CREATION
):
    """Every creation path: the type's declared capability and lifecycle initial state govern it."""
    selected = (
        objects.get_object_type(workspace, type_id)
        if type_id
        else ObjectType.objects.filter(workspace=workspace, key=key, is_active=True).first()
    )
    if selected is None:
        raise ValidationError({"code": "unsupported_schema", "object_type": key})
    if descriptors.creation_capability_name(selected) != creation:
        raise PermissionDenied("This Object type is created only by its declared creation capability.")
    definitions = {
        d.key: d for d in PropertyDefinition.objects.filter(workspace=workspace, object_type=selected, is_active=True)
    }
    derived = {r["result"] for r in effective_invariants(selected, definitions) if r["kind"] == "product"}
    if set(properties).intersection(derived):
        raise ValidationError({"properties": "Derived properties are not initial inputs."})
    initial = descriptors.initial_state(selected, definitions)
    if initial:
        state, value = initial
        from .capabilities import get_capability

        accepted = get_capability(creation).creation.initial_states
        if properties.get(state, value) != value or accepted and value not in accepted:
            raise ValidationError({state: "Use the initial status, then a guarded update."})
        properties = {**properties, state: value}
    obj = objects.create_object(
        actor=command_actor(),
        workspace=workspace,
        object_type=selected.pk,
        title=title,
        content=content,
        initial_values=properties,
    )
    if command_actor().metadata.get("context"):
        from .operations import identify_runtime_object

        identify_runtime_object(workspace, obj, command_actor().metadata["context"])
    patch_object_properties(workspace, obj, {})
    emit(
        "ObjectCreated",
        {
            "object_id": obj.pk,
            "object_type_id": selected.pk,
            "version": 1,
            "property_keys": list(effective_values(obj)),
        },
    )
    return obj


def link_objects(workspace, source, target, key=None, kind_id=None):
    kind = (
        _kind(workspace, key)
        if key
        else RelationType.objects.filter(pk=kind_id, workspace=workspace, is_active=True).first()
    )
    if kind is None:
        raise ValidationError({"relation_type": "Unknown active RelationType in this workspace."})
    if kind.key == "made_by" and command_context().special != "ApproveDecision":
        raise PermissionDenied("made_by is recorded only by ApproveDecision.")
    if kind.key == "supersedes":
        raise ValidationError("Decision replacement requires a dedicated workflow.")
    if (
        kind.key == "creates"
        and source.object_type.key == "decision"
        and effective_values(source).get("status") != "decided"
    ):
        raise ValidationError("Only a decided Decision can originate an Action.")
    existing = Relation.objects.filter(workspace=workspace, relation_type=kind, source=source, target=target).first()
    result = semantic.create_relation(
        actor=command_actor(), workspace=workspace, source_id=source.pk, target_id=target.pk, relation_type_id=kind.pk
    )
    if existing is None:
        emit(
            "ObjectLinked",
            {"relation_id": result.pk, "relation_type_id": kind.pk, "source_id": source.pk, "target_id": target.pk},
        )
        if command_context().special != "ApproveDecision":
            _stale(workspace, source)
            if source.pk != target.pk:
                _stale(workspace, target)
    return result


def create_declared(workspace, selected, capability, *, title, properties, parameters, content=None):
    """Shared creation/effects path of CreateObject and the semantic creation facades."""
    from .capabilities import resolve

    profile = capability.creation
    for key in profile.required_properties:
        value = properties.get(key)
        if not (value.strip() if isinstance(value, str) else value):
            raise ValidationError({key: "This field is required."})
    obj = create_typed_object(
        workspace, selected.key, title, properties, content, selected.pk, creation=capability.name
    )
    return resolve(profile.effects)(workspace, obj, parameters) if profile.effects else object_result(obj)


def _create_object(workspace, data):
    selected = objects.get_object_type(workspace, data["object_type_id"])
    capability, parameters = creation_parameters(selected, data.get("parameters", {}))
    return create_declared(
        workspace,
        selected,
        capability,
        title=data["title"],
        properties=dict(data["properties"]),
        parameters=parameters,
        content=data.get("content"),
    )


def _create_facade(workspace, name, data):
    """Semantic commands keep their inputs and reuse the type's declared creation path."""
    from plane.radar.active import active_types
    from .capabilities import get_capability

    capability = get_capability(name)
    selected = [kind for kind in active_types(workspace) if descriptors.creation_capability_name(kind) == name]
    if len(selected) != 1:
        raise ValidationError({"code": "unsupported_schema", "creation": name})
    profile = capability.creation
    properties = {key: data[key] for key in profile.property_fields if key in data}
    extra = data.get("properties", {})
    if set(extra) & (set(properties) | set(profile.parameter_type().fields)):
        raise ValidationError({"properties": "Declared inputs cannot be repeated as properties."})
    parameters = {key: data[key] for key in profile.parameter_type().fields if key in data}
    return create_declared(
        workspace,
        selected[0],
        capability,
        title=data["title"],
        properties={**properties, **extra},
        parameters=parameters,
    )


RESTRICTION_MESSAGES = {
    "measurement": "Use RecordMeasurement with evidence to update observations.",
    "decision_taken": "A taken choice is immutable; create a new Decision.",
    "evidence_in_use": "Evidence used in an approval/completion is immutable; create a new revision.",
}
RELATION_MESSAGES = {
    "approval_history": "Decision approval history cannot be removed.",
    "completion_evidence": "Completion evidence cannot be removed.",
    "decision_evidence": "Evidence of a taken Decision cannot be removed.",
}


def update_restrictions(workspace, obj) -> dict:
    """Specialized edit guards kept in code, shared by UpdateObject and effective capacities.

    `envelope` covers title/content, `fields` maps property keys ("*" for all) and `remove`
    covers any property removal. Values are reason codes from RESTRICTION_MESSAGES.
    """
    key, status = obj.object_type.key, effective_values(obj).get("status")
    if key == "indicator":
        return {"envelope": None, "fields": dict.fromkeys(("current", "measured_at"), "measurement"), "remove": None}
    if key == "decision" and status == "decided":
        fields = dict.fromkeys(("context", "decision", "rationale", "consequences"), "decision_taken")
        return {"envelope": "decision_taken", "fields": fields, "remove": "decision_taken"}
    if key == "document" and (
        ActionCompletion.objects.filter(evidence=obj).exists()
        or any(str(obj.pk) in vote.evidence_versions for vote in DecisionApproval.objects.filter(workspace=workspace))
    ):
        return {"envelope": "evidence_in_use", "fields": {"*": "evidence_in_use"}, "remove": "evidence_in_use"}
    return {"envelope": None, "fields": {}, "remove": None}


def field_restriction(restrictions, key):
    return restrictions["fields"].get(key) or restrictions["fields"].get("*")


def relation_restriction(workspace, relation, source, target) -> str | None:
    """Protected edges: specialized history that UnlinkObjects never removes."""
    key = relation.relation_type.key
    if key == "made_by" and DecisionApproval.objects.filter(decision=source, approver_person=target).exists():
        return "approval_history"
    if key == "verifies" and ActionCompletion.objects.filter(action=target, evidence=source).exists():
        return "completion_evidence"
    if key == "informed_by" and effective_values(source).get("status") == "decided":
        return "decision_evidence"
    return None


def _update(workspace, data):
    obj = lookup_object(workspace, data["object_id"], active_person=False)
    values, remove, changes = data["set_properties"], data["remove_properties"], data["changes"]
    restrictions = update_restrictions(workspace, obj)
    reasons = [field_restriction(restrictions, key) for key in (*values, *remove)]
    reasons += [restrictions["envelope"] if changes else None, restrictions["remove"] if remove else None]
    reason = next((item for item in reasons if item), None)
    if reason:
        raise ValidationError(RESTRICTION_MESSAGES[reason])
    guard = token = None
    transition = descriptors.requested_transition(obj, values, "UpdateObject")
    if transition and "guard" in transition:
        from .capabilities import get_guard, resolve

        guard = get_guard(transition["guard"])
        token = resolve(guard.check)(workspace, obj, data)
        descriptors.authorize_transition(obj, transition)
    values = descriptors.governed_patch(obj, values, remove)
    changed = False
    for field, value in changes.items():
        value = objects.validate_title(value) if field == "title" else objects.validate_content(value)
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed = True
    if changed:
        obj.updated_by_id = command_user_id()
        obj.save(update_fields=[*changes, "updated_by", "updated_at"])
        semantic.touch_objects([obj], command_user_id())
    changed = patch_object_properties(workspace, obj, values, remove) or changed
    extra = {}
    if changed:
        if guard is None:
            _stale(workspace, obj)
        emit(
            "ObjectUpdated",
            {
                "object_id": obj.pk,
                "changed_fields": list(changes),
                "property_keys_set": list(values),
                "property_keys_removed": remove,
            },
        )
        if guard and guard.after:
            from .capabilities import resolve

            extra = resolve(guard.after)(workspace, obj, token, transition)
    return {**object_result(obj), **extra}


def decision_approval_guard(workspace, obj, data):
    """Registered guard: a current, independent approval authorizes taking the Decision."""
    state = descriptors.state_property(obj)
    if (
        command_actor().actor_type != "human"
        or data["changes"]
        or set(data["set_properties"]) != {state}
        or data["remove_properties"]
    ):
        raise PermissionDenied("Decision taking is human-only and cannot edit the approved choice.")
    taken = current_decision_approval(workspace, obj)
    if taken is None:
        raise CommandConflict({"code": "approval_stale"})
    identity = PersonIdentity.objects.filter(
        workspace=workspace, user_id=command_actor().actor_id, can_approve=True, is_active=True
    ).first()
    authority = PersonIdentity.objects.filter(
        workspace=workspace,
        user_id=taken.approver_id,
        person=taken.approver_person,
        can_approve=True,
        is_active=True,
    ).first()
    if identity is None or authority is None:
        raise PermissionDenied("A current context_approver is required.")
    lookup_object(workspace, identity.person_id, {"person"})
    lookup_object(workspace, authority.person_id, {"person"})
    from dataclasses import replace
    from .execution import require_human_membership

    require_human_membership(replace(command_actor(), actor_id=taken.approver_id), workspace)
    if authority.updated_at.isoformat() != taken.snapshot["authority_updated_at"]:
        raise CommandConflict({"code": "approval_stale"})
    for pk, version in taken.evidence_versions.items():
        evidence = lookup_object(workspace, UUID(pk), {"document"})
        validate_evidence(evidence)
        if evidence.version != version:
            raise CommandConflict({"code": "approval_stale"})
    return taken


def decision_approval_references(workspace, obj):
    approval = current_decision_approval(workspace, obj)
    if approval is None:
        return set()
    return {*(UUID(pk) for pk in approval.evidence_versions), approval.approver_person_id}


def decision_taken(workspace, obj, taken, transition):
    decided_at = effective_values(obj).get(transition["stamp"]) if "stamp" in transition else command_now()
    emit("DecisionTaken", {"decision_id": obj.pk, "decision_approval_id": taken.pk, "decided_at": decided_at})
    return {"decision_approval_id": str(taken.pk)}


def _create_action(workspace, data):
    return _create_facade(workspace, "CreateAction", data)


def action_effects(workspace, obj, data):
    if data.get("origin_decision_id"):
        decision = lookup_object(workspace, data["origin_decision_id"], {"decision"})
        if effective_values(decision).get("status") != "decided":
            raise ValidationError("Action origin requires a decided Decision.")
        link_objects(workspace, decision, obj, "creates")
    if data.get("owner_person_id"):
        link_objects(workspace, obj, lookup_object(workspace, data["owner_person_id"], {"person"}), "owned_by")
    for pk in set(data["executor_person_ids"]):
        link_objects(workspace, obj, lookup_object(workspace, pk, {"person"}), "assigned_to")
    for pk in set(data["mitigates_risk_ids"]):
        link_objects(workspace, obj, lookup_object(workspace, pk, {"risk"}), "mitigates")
    emit(
        "ActionCreated",
        {
            "action_id": obj.pk,
            "initial_status": effective_values(obj).get(descriptors.state_property(obj)),
            "origin_decision_id": data.get("origin_decision_id"),
        },
    )
    result = object_result(obj)
    if not data.get("owner_person_id"):
        result["findings"] = [{"code": "RADAR-M001", "object_id": str(obj.pk), "severity": "finding"}]
    return result


def _register_risk(workspace, data):
    return _create_facade(workspace, "RegisterRisk", data)


def risk_effects(workspace, obj, data):
    if data.get("owner_person_id"):
        link_objects(workspace, obj, lookup_object(workspace, data["owner_person_id"], {"person"}), "owned_by")
    for pk in set(data["threatens_object_ids"]):
        link_objects(workspace, obj, lookup_object(workspace, pk, {"objective", "project"}), "threatens")
    emit(
        "RiskRegistered",
        {
            "risk_id": obj.pk,
            "initial_status": effective_values(obj).get(descriptors.state_property(obj)),
            **{key: effective_values(obj)[key] for key in ("likelihood", "impact", "score")},
        },
    )
    return object_result(obj)


def _create_decision(workspace, data):
    return _create_facade(workspace, "CreateDecision", data)


def decision_effects(workspace, obj, data):
    if data.get("project_id"):
        link_objects(workspace, lookup_object(workspace, data["project_id"], {"project"}), obj, "contains")
    for pk in set(data["evidence_ids"]):
        evidence = lookup_object(workspace, pk, {"document"})
        validate_evidence(evidence)
        link_objects(workspace, obj, evidence, "informed_by")
    for field, key in [
        ("consultation_person_ids", "requires_consultation"),
        ("notification_person_ids", "requires_notification"),
    ]:
        for pk in set(data[field]):
            link_objects(workspace, obj, lookup_object(workspace, pk, {"person"}), key)
    emit(
        "DecisionCreated",
        {"decision_id": obj.pk, "initial_status": effective_values(obj).get(descriptors.state_property(obj))},
    )
    return object_result(obj)


def _approve_decision(workspace, data):
    if command_actor().actor_type != "human":
        raise PermissionDenied("Decision approval is human-only.")
    obj = lookup_object(workspace, data["decision_id"], {"decision"})
    person = lookup_object(workspace, data["approver_person_id"], {"person"})
    identity = PersonIdentity.objects.filter(
        workspace=workspace, user_id=command_actor().actor_id, person=person, can_approve=True, is_active=True
    ).first()
    if identity is None:
        raise PermissionDenied("No verified Person mapping and context_approver authority.")
    values = effective_values(obj)
    if values.get("status") not in {"proposed", "decided"} or any(
        not values.get(key, "").strip() for key in ("context", "decision", "rationale")
    ):
        raise ValidationError("Review a complete proposed/decided Decision.")
    author_ids = {obj.created_by_id}
    editorial = Provenance.objects.filter(
        workspace=workspace,
        command_name="UpdateObject",
        changes__contains=[{"model": "radar.Object", "id": str(obj.pk)}],
    )
    for record in editorial.order_by("-timestamp"):
        reviewed_input = record.context.get("input", {})
        if reviewed_input.get("changes") or set(reviewed_input.get("set_properties", {})) & {
            "context",
            "decision",
            "rationale",
            "consequences",
        }:
            if record.actor_type == "human":
                author_ids.add(record.actor_id)
            break
    if command_actor().actor_id in author_ids:
        raise PermissionDenied("An independent human must approve the reviewed proposal.")
    evidence_ids = decision_evidence_ids(workspace, obj.pk)
    if not evidence_ids:
        raise ValidationError("Decision approval requires evidence.")
    evidence_versions, snapshots = {}, {}
    for pk in evidence_ids:
        evidence = lookup_object(workspace, pk, {"document"})
        validate_evidence(evidence)
        evidence_versions[str(pk)], snapshots[str(pk)] = evidence.version, _snapshot(evidence)
    existing = current_decision_approval(workspace, obj)
    if (
        existing
        and existing.approver_id == command_actor().actor_id
        and existing.evidence_versions == evidence_versions
    ):
        return {**object_result(obj), "decision_approval_id": str(existing.pk)}
    snapshot, reviewed = _snapshot(obj), obj.version
    with _special("ApproveDecision"):
        link_objects(workspace, obj, person, "made_by")
    semantic.touch_objects([obj], command_user_id())
    obj.refresh_from_db()
    vote = DecisionApproval.objects.create(
        workspace=workspace,
        decision=obj,
        approver_id=command_actor().actor_id,
        approver_person=person,
        rationale=data["rationale"],
        reviewed_version=reviewed,
        resulting_version=obj.version,
        snapshot={"decision": snapshot, "evidence": snapshots, "authority_updated_at": identity.updated_at.isoformat()},
        evidence_versions=evidence_versions,
        created_by_id=command_user_id(),
        updated_by_id=command_user_id(),
    )
    emit(
        "DecisionApproved",
        {
            "decision_id": obj.pk,
            "decision_approval_id": vote.pk,
            "reviewed_version": reviewed,
            "resulting_version": obj.version,
            "approver_actor_id": command_actor().actor_id,
            "approver_person_id": person.pk,
            "evidence_ids": list(evidence_ids),
        },
    )
    return {**object_result(obj), "decision_approval_id": str(vote.pk)}


def approver_prefill(workspace, actor, obj):
    """The actor's own verified approver identity; approval is never offered on behalf of others."""
    identity = PersonIdentity.objects.filter(
        workspace=workspace, user_id=actor.actor_id, can_approve=True, is_active=True
    ).first()
    if identity is None:
        raise PermissionDenied("No verified Person mapping and context_approver authority.")
    return {"approver_person_id": str(identity.person_id)}


def _complete_action(workspace, data):
    obj = lookup_object(workspace, data["action_id"], {"action"})
    evidence = lookup_object(workspace, data["evidence_id"], {"document"})
    validate_evidence(evidence)
    state = descriptors.state_property(obj)
    status = effective_values(obj).get(state)
    transition = descriptors.declared_target(obj, "CompleteAction", required=False)
    if transition is None or status not in transition["from"] or ActionCompletion.objects.filter(action=obj).exists():
        raise ValidationError("This Action cannot be completed again or reopened.")
    snapshot = {"action": _snapshot(obj), "evidence": _snapshot(evidence)}
    patch_object_properties(workspace, obj, {state: transition["to"]})
    stamp = effective_values(obj).get(transition.get("stamp")) if "stamp" in transition else None
    now = datetime.fromisoformat(stamp) if stamp else command_now()
    link_objects(workspace, evidence, obj, "verifies")
    completion = ActionCompletion.objects.create(
        workspace=workspace,
        action=obj,
        evidence=evidence,
        outcome=data["outcome"],
        snapshot=snapshot,
        completed_at=now,
        created_by_id=command_user_id(),
        updated_by_id=command_user_id(),
    )
    emit(
        "ActionCompleted",
        {
            "action_id": obj.pk,
            "completion_id": completion.pk,
            "evidence_id": evidence.pk,
            "completed_at": now,
            "before_status": status,
            "after_status": transition["to"],
        },
    )
    return {**object_result(obj), "completion_id": str(completion.pk)}


def _unlink(workspace, data):
    relation = (
        Relation.all_objects.filter(workspace=workspace, pk=data["relation_id"]).select_related("relation_type").first()
    )
    if relation is None:
        raise NotFound("Relation not found in this workspace.")
    if relation.deleted_at:
        return {"relation_id": str(relation.pk)}
    source, target = lookup_object(workspace, relation.source_id), lookup_object(workspace, relation.target_id)
    reason = relation_restriction(workspace, relation, source, target)
    if reason:
        raise PermissionDenied(RELATION_MESSAGES[reason])
    semantic.remove_relation(actor=command_actor(), workspace=workspace, relation_id=relation.pk)
    _stale(workspace, source)
    if source.pk != target.pk:
        _stale(workspace, target)
    emit(
        "ObjectUnlinked",
        {
            "relation_id": relation.pk,
            "relation_type_id": relation.relation_type_id,
            "source_id": source.pk,
            "target_id": target.pk,
            "removed_at": command_now(),
        },
    )
    return {"relation_id": str(relation.pk)}


def _add_evidence(workspace, data):
    target = lookup_object(workspace, data["target_id"])
    document = data["document"]
    created = "existing_id" not in document
    if created:
        props = {
            key: value for key, value in document.items() if key in {"document_type", "summary", "uri", "source_system"}
        }
        obj = create_typed_object(workspace, "document", document["title"], props, document.get("content"))
    else:
        obj = lookup_object(workspace, document["existing_id"], {"document"})
    validate_evidence(obj)
    observed_at = data.get("observed_at")
    if observed_at and observed_at > command_now():
        raise ValidationError({"observed_at": "Observation cannot be in the future."})
    claimed_hash = data.get("content_hash", "")
    if claimed_hash and obj.content and claimed_hash != hashlib.sha256(obj.content.encode()).hexdigest():
        raise ValidationError({"content_hash": "Hash must match sanitized persisted content."})
    if data["relation_key"] == "informed_by":
        source, dest = target, obj
    else:
        source, dest = obj, target
    relation = link_objects(workspace, source, dest, data["relation_key"])
    record = EvidenceRecord.objects.filter(
        workspace=workspace,
        document=obj,
        target=target,
        relation=relation,
        observed_at=observed_at,
        content_hash=claimed_hash,
    ).first()
    if record is None:
        record = EvidenceRecord.objects.create(
            workspace=workspace,
            document=obj,
            target=target,
            relation=relation,
            observed_at=observed_at,
            content_hash=claimed_hash,
            created_by_id=command_user_id(),
            updated_by_id=command_user_id(),
        )
        emit(
            "EvidenceAdded",
            {
                "target_id": target.pk,
                "document_id": obj.pk,
                "relation_id": relation.pk,
                "relation_key": data["relation_key"],
                "created_document": created,
                "observed_at": observed_at,
                "content_hash": claimed_hash,
            },
        )
    return {
        **object_result(target),
        "document_id": str(obj.pk),
        "relation_id": str(relation.pk),
        "evidence_record_id": str(record.pk),
    }


def _initialize_properties(workspace, data):
    obj = semantic.initialize_object_properties(actor=command_actor(), workspace=workspace, object_id=data["object_id"])
    if command_context().changes:
        emit("InitializeObjectProperties", {"object_id": obj.pk})
    return property_snapshot_result(obj)


def _link(workspace, data):
    source, target = lookup_object(workspace, data["source_id"]), lookup_object(workspace, data["target_id"])
    relation = link_objects(workspace, source, target, kind_id=data["relation_type_id"])
    return {"relation": relation_result(relation)}


def dispatch(workspace, name, data):
    from .capabilities import get_capability

    command_context()
    return get_capability(name).execute(workspace, data)
