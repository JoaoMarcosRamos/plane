"""Domain handlers. Only execute_command enters these functions with a write context."""

import hashlib
from contextlib import contextmanager
from uuid import UUID

from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from plane.radar.models import (
    ActionCompletion,
    ActorGrant,
    DecisionApproval,
    EvidenceRecord,
    Object,
    ObjectType,
    PersonIdentity,
    PropertyDefinition,
    Provenance,
    Relation,
    RelationType,
)
from plane.radar.mutation import current_mutation, json_value
from plane.radar.ontology.schema import load_schema
from .execution import CommandConflict, emit
from . import primitives_objects as objects
from . import primitives_semantic as semantic
from .rules import ORDINARY_TRANSITIONS, effective_invariants


def _context():
    context = current_mutation.get()
    if context is None:
        raise PermissionDenied("Mutation requires the shared command layer and an explicit Actor.")
    return context


def _actor():
    return _context().actor


def _user_id():
    return _actor().actor_id if _actor().actor_type == "human" else None


def _lookup(workspace, pk, types=None, *, active_person=True):
    obj = semantic._object(workspace, pk)
    if types is not None and obj.object_type.key not in types:
        raise ValidationError("Object type does not satisfy this command.")
    if active_person and obj.object_type.key == "person" and _values(obj).get("status") != "active":
        raise ValidationError("Select an active Person.")
    return obj


def _kind(workspace, key):
    try:
        return RelationType.objects.get(workspace=workspace, key=key, is_active=True)
    except RelationType.DoesNotExist as exc:
        raise ValidationError({"code": "unsupported_schema", "relation": key}) from exc


def _values(obj):
    return semantic.effective_values(obj)


def _snapshot(obj):
    return json_value(
        {
            "id": obj.pk,
            "version": obj.version,
            "title": obj.title,
            "content": obj.content,
            "object_type": obj.object_type.key,
            "properties": _values(obj),
        }
    )


def _fundaments(workspace, decision_id):
    return set(
        Relation.objects.filter(
            workspace=workspace,
            source_id=decision_id,
            relation_type__key="informed_by",
            relation_type__is_active=True,
            target__object_type__key="document",
            target__deleted_at__isnull=True,
        ).values_list("target_id", flat=True)
    )


def _approval(workspace, obj):
    return (
        DecisionApproval.objects.filter(
            workspace=workspace, decision=obj, is_stale=False, resulting_version=obj.version
        )
        .order_by("-created_at")
        .first()
    )


def references(workspace, name, data):
    from plane.radar.collaboration import COLLABORATION_COMMANDS

    if name in COLLABORATION_COMMANDS:
        return {data["object_id"]}
    if name in {"CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement"}:
        from .operations import references as operation_references

        return operation_references(workspace, name, data)
    if name == "CreateObject":
        specialized, payload = _special_input(workspace, data)
        if specialized:
            return references(workspace, specialized, payload)
    refs = set()
    single = {
        "UpdateObject": ["object_id"],
        "LinkObjects": ["source_id", "target_id"],
        "CreateAction": ["origin_decision_id", "owner_person_id"],
        "CompleteAction": ["action_id", "evidence_id"],
        "RegisterRisk": ["owner_person_id"],
        "CreateDecision": ["project_id"],
        "ApproveDecision": ["decision_id", "approver_person_id"],
        "AddEvidence": ["target_id"],
    }
    for key in single.get(name, []):
        if key in data:
            refs.add(data[key])
    for key in (
        "executor_person_ids",
        "mitigates_risk_ids",
        "threatens_object_ids",
        "evidence_ids",
        "consultation_person_ids",
        "notification_person_ids",
    ):
        refs.update(data.get(key, []))
    if name == "UnlinkObjects":
        relation = Relation.all_objects.filter(pk=data["relation_id"], workspace=workspace).first()
        if relation is None:
            raise NotFound("Relation not found in this workspace.")
        refs.update([relation.source_id, relation.target_id])
    if name == "AddEvidence" and "existing_id" in data["document"]:
        refs.add(data["document"]["existing_id"])
    if name == "ApproveDecision":
        refs.update(_fundaments(workspace, data["decision_id"]))
    if name == "UpdateObject" and data.get("set_properties", {}).get("status") == "decided":
        obj = _lookup(workspace, data["object_id"])
        approval = _approval(workspace, obj)
        if approval:
            refs.update(UUID(pk) for pk in approval.evidence_versions)
            refs.add(approval.approver_person_id)
    return refs


def _special_input(workspace, data):
    selected = objects._type(workspace, data["object_type_id"])
    props = dict(data["properties"])
    key = selected.key
    specialized = {"action": "CreateAction", "risk": "RegisterRisk", "decision": "CreateDecision"}.get(key)
    if specialized is None:
        return None, data
    if "status" in props:
        if props.pop("status") != load_schema()["object_types"][key]["status"]["default"]:
            raise ValidationError({"status": "Specialized objects must start in their initial state."})
    from .inputs import INPUTS

    payload = {"title": data["title"], **props}
    serializer = INPUTS[specialized](data=payload)
    serializer.is_valid(raise_exception=True)
    return specialized, serializer.validated_data


def check_grant(workspace, grant: ActorGrant | None, name, data, refs):
    if _is_human_only(workspace, name, data) and grant is not None:
        raise PermissionDenied("Decision approval and decision taking are human-only.")
    if grant is None:
        return
    if name in {"CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement"}:
        from .operations import check_context

        check_context(workspace, data, refs)
        created = {
            "CaptureIssue": {"case", "management_item", "document"},
            "RecordMeasurement": {"document"} if "evidence_id" not in data else set(),
        }.get(name, set())
        types = (
            set(Object.objects.filter(workspace=workspace, pk__in=refs).values_list("object_type__key", flat=True))
            | created
        )
        if "*" not in grant.object_types and not types.issubset(grant.object_types):
            raise PermissionDenied("Grant does not cover every operation Object type.")
        if "*" not in grant.fields or "LinkObjects" not in grant.commands:
            raise PermissionDenied("Operational commands require composed relation and field authority.")
        return
    types = set(Object.objects.filter(workspace=workspace, pk__in=refs).values_list("object_type__key", flat=True))
    created_type = {
        "CreateAction": "action",
        "RegisterRisk": "risk",
        "CreateDecision": "decision",
        "AddEvidence": "document",
    }.get(name)
    extra_commands = set()
    if name == "CreateObject":
        types.add(objects._type(workspace, data["object_type_id"]).key)
        specialized, _ = _special_input(workspace, data)
        if specialized:
            extra_commands.add(specialized)
    elif created_type:
        types.add(created_type)
    if (
        name in {"CompleteAction", "AddEvidence"}
        or refs
        and name in {"CreateObject", "CreateAction", "RegisterRisk", "CreateDecision"}
    ):
        extra_commands.add("LinkObjects")
    if not extra_commands.issubset(set(grant.commands)):
        raise PermissionDenied("Grant does not cover every composed command effect.")
    if "*" not in grant.object_types and not types.issubset(set(grant.object_types)):
        raise PermissionDenied("Grant does not cover every Object type.")
    if name == "UpdateObject":
        fields = set(data["changes"]) | set(data["set_properties"]) | set(data["remove_properties"])
        obj = semantic._object(workspace, data["object_id"])
        fields.update(semantic.property_effect_fields(obj, data["set_properties"], data["remove_properties"]))
        if "*" not in grant.fields and not fields.issubset(set(grant.fields)):
            raise PermissionDenied("Grant does not cover every modified field.")
    elif name.startswith("Create") or name in {"RegisterRisk", "CompleteAction", "AddEvidence"}:
        if "*" not in grant.fields:
            # Creation includes defaults and derived values, not just the explicit payload.
            keys = {
                definition.key
                for definition in PropertyDefinition.objects.filter(
                    workspace=workspace, object_type__key__in=types, is_active=True
                )
            }
            keys.update({"title", "content"})
            if not keys.issubset(set(grant.fields)):
                raise PermissionDenied("Grant does not cover initial/default/derived fields.")


def _is_human_only(workspace, name, data):
    return (
        name == "ApproveDecision"
        or name == "UpdateObject"
        and data.get("set_properties", {}).get("status") == "decided"
        and semantic._object(workspace, data["object_id"]).object_type.key == "decision"
    )


def requires_human_review(workspace, actor, grant, name, data):
    if _is_human_only(workspace, name, data) and actor.actor_type != "human":
        raise PermissionDenied("This command is human-only.")
    if grant:
        return actor.actor_type == "agent" or grant.requires_approval
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
    context = _context()
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


def _ensure_evidence(obj):
    values = _values(obj)
    if (
        obj.object_type.key != "document"
        or values.get("status") == "archived"
        or not (strip_tags(obj.content).strip() or values.get("uri"))
    ):
        raise ValidationError({"evidence": "Use a live Document with content or a source URI."})


def _patch_properties(workspace, obj, values, remove=()):
    return semantic.patch_properties(actor=_actor(), workspace=workspace, obj=obj, values=values, remove=remove)


def _new(workspace, key, title, properties, content=None, type_id=None):
    selected = (
        objects._type(workspace, type_id)
        if type_id
        else ObjectType.objects.filter(workspace=workspace, key=key, is_active=True).first()
    )
    if selected is None:
        raise ValidationError({"code": "unsupported_schema", "object_type": key})
    definitions = {
        d.key: d for d in PropertyDefinition.objects.filter(workspace=workspace, object_type=selected, is_active=True)
    }
    derived = {r["result"] for r in effective_invariants(selected, definitions) if r["kind"] == "product"}
    if set(properties).intersection(derived):
        raise ValidationError({"properties": "Derived properties are not initial inputs."})
    obj = objects.create_object(
        actor=_actor(),
        workspace=workspace,
        object_type=selected.pk,
        title=title,
        content=content,
        initial_values=properties,
    )
    if _actor().metadata.get("context"):
        from .operations import _identify

        _identify(workspace, obj, _actor().metadata["context"])
    _patch_properties(workspace, obj, {})
    emit(
        "ObjectCreated",
        {"object_id": obj.pk, "object_type_id": selected.pk, "version": 1, "property_keys": list(_values(obj))},
    )
    return obj


def _link(workspace, source, target, key=None, kind_id=None):
    kind = (
        _kind(workspace, key)
        if key
        else RelationType.objects.filter(pk=kind_id, workspace=workspace, is_active=True).first()
    )
    if kind is None:
        raise ValidationError({"relation_type": "Unknown active RelationType in this workspace."})
    if kind.key == "made_by" and _context().special != "ApproveDecision":
        raise PermissionDenied("made_by is recorded only by ApproveDecision.")
    if kind.key == "supersedes":
        raise ValidationError("Decision replacement requires a dedicated workflow.")
    if kind.key == "creates" and source.object_type.key == "decision" and _values(source).get("status") != "decided":
        raise ValidationError("Only a decided Decision can originate an Action.")
    existing = Relation.objects.filter(workspace=workspace, relation_type=kind, source=source, target=target).first()
    result = semantic.create_relation(
        actor=_actor(), workspace=workspace, source_id=source.pk, target_id=target.pk, relation_type_id=kind.pk
    )
    if existing is None:
        emit(
            "ObjectLinked",
            {"relation_id": result.pk, "relation_type_id": kind.pk, "source_id": source.pk, "target_id": target.pk},
        )
        if _context().special != "ApproveDecision":
            _stale(workspace, source)
            if source.pk != target.pk:
                _stale(workspace, target)
    return result


def _object_data(obj):
    from plane.radar.api.serializers import ObjectSerializer

    obj.refresh_from_db()
    return {"object": ObjectSerializer(obj).data}


def _create_object(workspace, data):
    specialized, payload = _special_input(workspace, data)
    if specialized:
        return dispatch(workspace, specialized, payload, content=data.get("content"))
    selected = objects._type(workspace, data["object_type_id"])
    spec = load_schema()["object_types"].get(selected.key)
    if "status" in data["properties"] and spec and data["properties"]["status"] != spec["status"]["default"]:
        raise ValidationError({"status": "Use the initial status, then a guarded update."})
    return _object_data(
        _new(workspace, selected.key, data["title"], data["properties"], data.get("content"), selected.pk)
    )


def _update(workspace, data):
    obj = _lookup(workspace, data["object_id"], active_person=False)
    values, remove, changes = data["set_properties"], data["remove_properties"], data["changes"]
    effective = _values(obj)
    key, status = obj.object_type.key, effective.get("status")
    if key == "indicator" and (set(values) | set(remove)) & {"current", "measured_at"}:
        raise ValidationError("Use RecordMeasurement with evidence to update observations.")
    if key == "action" and ("completed_at" in values or "completed_at" in remove or values.get("status") == "done"):
        raise ValidationError("Use CompleteAction with an outcome and evidence.")
    if key == "decision" and ("decided_at" in values or "decided_at" in remove):
        raise ValidationError("decided_at is recorded by the guarded decision transition.")
    if (
        key == "decision"
        and status == "decided"
        and (changes or set(values) & {"context", "decision", "rationale", "consequences"} or remove)
    ):
        raise ValidationError("A taken choice is immutable; create a new Decision.")
    if (
        key == "document"
        and (
            ActionCompletion.objects.filter(evidence=obj).exists()
            or any(
                str(obj.pk) in vote.evidence_versions for vote in DecisionApproval.objects.filter(workspace=workspace)
            )
        )
        and (changes or values or remove)
    ):
        raise ValidationError("Evidence used in an approval/completion is immutable; create a new revision.")
    taken = None
    if "status" in values and values["status"] != status:
        if key == "decision" and status == "proposed" and values["status"] == "decided":
            if _actor().actor_type != "human" or changes or set(values) != {"status"} or remove:
                raise PermissionDenied("Decision taking is human-only and cannot edit the approved choice.")
            taken = _approval(workspace, obj)
            if taken is None:
                raise CommandConflict({"code": "approval_stale"})
            identity = PersonIdentity.objects.filter(
                workspace=workspace, user_id=_actor().actor_id, can_approve=True, is_active=True
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
            _lookup(workspace, identity.person_id, {"person"})
            _lookup(workspace, authority.person_id, {"person"})
            from dataclasses import replace
            from .execution import _human_member

            _human_member(replace(_actor(), actor_id=taken.approver_id), workspace)
            if authority.updated_at.isoformat() != taken.snapshot["authority_updated_at"]:
                raise CommandConflict({"code": "approval_stale"})
            for pk, version in taken.evidence_versions.items():
                evidence = _lookup(workspace, UUID(pk), {"document"})
                _ensure_evidence(evidence)
                if evidence.version != version:
                    raise CommandConflict({"code": "approval_stale"})
            values = {**values, "decided_at": timezone.now().isoformat()}
        elif (status, values["status"]) not in ORDINARY_TRANSITIONS.get(key, set()):
            raise ValidationError({"status": "This transition requires a dedicated workflow."})
    changed = False
    for field, value in changes.items():
        value = objects._title(value) if field == "title" else objects._content(value)
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed = True
    if changed:
        obj.updated_by_id = _user_id()
        obj.save(update_fields=[*changes, "updated_by", "updated_at"])
        semantic._touch([obj], _user_id())
    changed = _patch_properties(workspace, obj, values, remove) or changed
    if changed:
        if taken is None:
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
        if taken:
            emit(
                "DecisionTaken",
                {"decision_id": obj.pk, "decision_approval_id": taken.pk, "decided_at": values["decided_at"]},
            )
    result = _object_data(obj)
    if taken:
        result["decision_approval_id"] = str(taken.pk)
    return result


def _create_action(workspace, data, content=None):
    props = {key: value for key, value in data.items() if key in {"description", "next_step", "priority", "due_date"}}
    if data.get("origin_decision_id"):
        decision = _lookup(workspace, data["origin_decision_id"], {"decision"})
        if _values(decision).get("status") != "decided":
            raise ValidationError("Action origin requires a decided Decision.")
    obj = _new(workspace, "action", data["title"], props, content)
    if data.get("origin_decision_id"):
        _link(workspace, decision, obj, "creates")
    if data.get("owner_person_id"):
        _link(workspace, obj, _lookup(workspace, data["owner_person_id"], {"person"}), "owned_by")
    for pk in set(data["executor_person_ids"]):
        _link(workspace, obj, _lookup(workspace, pk, {"person"}), "assigned_to")
    for pk in set(data["mitigates_risk_ids"]):
        _link(workspace, obj, _lookup(workspace, pk, {"risk"}), "mitigates")
    emit(
        "ActionCreated",
        {"action_id": obj.pk, "initial_status": "todo", "origin_decision_id": data.get("origin_decision_id")},
    )
    result = _object_data(obj)
    if not data.get("owner_person_id"):
        result["findings"] = [{"code": "RADAR-M001", "object_id": str(obj.pk), "severity": "finding"}]
    return result


def _register_risk(workspace, data, content=None):
    props = {
        key: value
        for key, value in data.items()
        if key in {"description", "likelihood", "impact", "response_strategy", "review_date"}
    }
    obj = _new(workspace, "risk", data["title"], props, content)
    if data.get("owner_person_id"):
        _link(workspace, obj, _lookup(workspace, data["owner_person_id"], {"person"}), "owned_by")
    for pk in set(data["threatens_object_ids"]):
        _link(workspace, obj, _lookup(workspace, pk, {"objective", "project"}), "threatens")
    emit(
        "RiskRegistered",
        {
            "risk_id": obj.pk,
            "initial_status": "identified",
            **{key: _values(obj)[key] for key in ("likelihood", "impact", "score")},
        },
    )
    return _object_data(obj)


def _create_decision(workspace, data, content=None):
    props = {key: value for key, value in data.items() if key in {"context", "decision", "rationale", "consequences"}}
    obj = _new(workspace, "decision", data["title"], props, content)
    if data.get("project_id"):
        _link(workspace, _lookup(workspace, data["project_id"], {"project"}), obj, "contains")
    for pk in set(data["evidence_ids"]):
        evidence = _lookup(workspace, pk, {"document"})
        _ensure_evidence(evidence)
        _link(workspace, obj, evidence, "informed_by")
    for field, key in [
        ("consultation_person_ids", "requires_consultation"),
        ("notification_person_ids", "requires_notification"),
    ]:
        for pk in set(data[field]):
            _link(workspace, obj, _lookup(workspace, pk, {"person"}), key)
    emit("DecisionCreated", {"decision_id": obj.pk, "initial_status": "proposed"})
    return _object_data(obj)


def _approve_decision(workspace, data):
    if _actor().actor_type != "human":
        raise PermissionDenied("Decision approval is human-only.")
    obj = _lookup(workspace, data["decision_id"], {"decision"})
    person = _lookup(workspace, data["approver_person_id"], {"person"})
    identity = PersonIdentity.objects.filter(
        workspace=workspace, user_id=_actor().actor_id, person=person, can_approve=True, is_active=True
    ).first()
    if identity is None:
        raise PermissionDenied("No verified Person mapping and context_approver authority.")
    values = _values(obj)
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
    if _actor().actor_id in author_ids:
        raise PermissionDenied("An independent human must approve the reviewed proposal.")
    evidence_ids = _fundaments(workspace, obj.pk)
    if not evidence_ids:
        raise ValidationError("Decision approval requires evidence.")
    evidence_versions, snapshots = {}, {}
    for pk in evidence_ids:
        evidence = _lookup(workspace, pk, {"document"})
        _ensure_evidence(evidence)
        evidence_versions[str(pk)], snapshots[str(pk)] = evidence.version, _snapshot(evidence)
    existing = _approval(workspace, obj)
    if existing and existing.approver_id == _actor().actor_id and existing.evidence_versions == evidence_versions:
        return {**_object_data(obj), "decision_approval_id": str(existing.pk)}
    snapshot, reviewed = _snapshot(obj), obj.version
    with _special("ApproveDecision"):
        _link(workspace, obj, person, "made_by")
    semantic._touch([obj], _user_id())
    obj.refresh_from_db()
    vote = DecisionApproval.objects.create(
        workspace=workspace,
        decision=obj,
        approver_id=_actor().actor_id,
        approver_person=person,
        rationale=data["rationale"],
        reviewed_version=reviewed,
        resulting_version=obj.version,
        snapshot={"decision": snapshot, "evidence": snapshots, "authority_updated_at": identity.updated_at.isoformat()},
        evidence_versions=evidence_versions,
        created_by_id=_user_id(),
        updated_by_id=_user_id(),
    )
    emit(
        "DecisionApproved",
        {
            "decision_id": obj.pk,
            "decision_approval_id": vote.pk,
            "reviewed_version": reviewed,
            "resulting_version": obj.version,
            "approver_actor_id": _actor().actor_id,
            "approver_person_id": person.pk,
            "evidence_ids": list(evidence_ids),
        },
    )
    return {**_object_data(obj), "decision_approval_id": str(vote.pk)}


def _complete_action(workspace, data):
    obj = _lookup(workspace, data["action_id"], {"action"})
    evidence = _lookup(workspace, data["evidence_id"], {"document"})
    _ensure_evidence(evidence)
    status = _values(obj).get("status")
    if status not in {"todo", "in_progress", "waiting"} or ActionCompletion.objects.filter(action=obj).exists():
        raise ValidationError("This Action cannot be completed again or reopened.")
    now = timezone.now()
    snapshot = {"action": _snapshot(obj), "evidence": _snapshot(evidence)}
    _patch_properties(workspace, obj, {"status": "done", "completed_at": now.isoformat()})
    _link(workspace, evidence, obj, "verifies")
    completion = ActionCompletion.objects.create(
        workspace=workspace,
        action=obj,
        evidence=evidence,
        outcome=data["outcome"],
        snapshot=snapshot,
        completed_at=now,
        created_by_id=_user_id(),
        updated_by_id=_user_id(),
    )
    emit(
        "ActionCompleted",
        {
            "action_id": obj.pk,
            "completion_id": completion.pk,
            "evidence_id": evidence.pk,
            "completed_at": now,
            "before_status": status,
            "after_status": "done",
        },
    )
    return {**_object_data(obj), "completion_id": str(completion.pk)}


def _unlink(workspace, data):
    relation = (
        Relation.all_objects.filter(workspace=workspace, pk=data["relation_id"]).select_related("relation_type").first()
    )
    if relation is None:
        raise NotFound("Relation not found in this workspace.")
    if relation.deleted_at:
        return {"relation_id": str(relation.pk)}
    key = relation.relation_type.key
    source, target = _lookup(workspace, relation.source_id), _lookup(workspace, relation.target_id)
    if key == "made_by" and DecisionApproval.objects.filter(decision=source, approver_person=target).exists():
        raise PermissionDenied("Decision approval history cannot be removed.")
    if key == "verifies" and ActionCompletion.objects.filter(action=target, evidence=source).exists():
        raise PermissionDenied("Completion evidence cannot be removed.")
    if key == "informed_by" and _values(source).get("status") == "decided":
        raise PermissionDenied("Evidence of a taken Decision cannot be removed.")
    semantic.remove_relation(actor=_actor(), workspace=workspace, relation_id=relation.pk)
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
            "removed_at": timezone.now(),
        },
    )
    return {"relation_id": str(relation.pk)}


def _add_evidence(workspace, data):
    target = _lookup(workspace, data["target_id"])
    document = data["document"]
    created = "existing_id" not in document
    if created:
        props = {
            key: value for key, value in document.items() if key in {"document_type", "summary", "uri", "source_system"}
        }
        obj = _new(workspace, "document", document["title"], props, document.get("content"))
    else:
        obj = _lookup(workspace, document["existing_id"], {"document"})
    _ensure_evidence(obj)
    observed_at = data.get("observed_at")
    if observed_at and observed_at > timezone.now():
        raise ValidationError({"observed_at": "Observation cannot be in the future."})
    claimed_hash = data.get("content_hash", "")
    if claimed_hash and obj.content and claimed_hash != hashlib.sha256(obj.content.encode()).hexdigest():
        raise ValidationError({"content_hash": "Hash must match sanitized persisted content."})
    if data["relation_key"] == "informed_by":
        source, dest = target, obj
    else:
        source, dest = obj, target
    relation = _link(workspace, source, dest, data["relation_key"])
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
            created_by_id=_user_id(),
            updated_by_id=_user_id(),
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
        **_object_data(target),
        "document_id": str(obj.pk),
        "relation_id": str(relation.pk),
        "evidence_record_id": str(record.pk),
    }


def dispatch(workspace, name, data, content=None):
    from plane.radar.collaboration import COLLABORATION_COMMANDS

    if name in COLLABORATION_COMMANDS:
        from .collaboration import dispatch as collaboration_dispatch

        return collaboration_dispatch(workspace, name, data)
    if name in {"CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement"}:
        from .operations import dispatch as operation_dispatch

        return operation_dispatch(workspace, name, data)
    _context()
    # Lazy seed belongs to this command's transaction and provenance, with no separate commit.
    if _actor().actor_type == "human":
        semantic.initialize_semantic_model(actor=_actor(), workspace=workspace)
    if name == "CreateObject":
        return _create_object(workspace, data)
    if name == "UpdateObject":
        return _update(workspace, data)
    if name == "LinkObjects":
        source, target = _lookup(workspace, data["source_id"]), _lookup(workspace, data["target_id"])
        relation = _link(workspace, source, target, kind_id=data["relation_type_id"])
        from plane.radar.api.serializers import RelationSerializer

        return {"relation": RelationSerializer(relation).data}
    if name == "UnlinkObjects":
        return _unlink(workspace, data)
    if name == "CreateAction":
        return _create_action(workspace, data, content)
    if name == "RegisterRisk":
        return _register_risk(workspace, data, content)
    if name == "CreateDecision":
        return _create_decision(workspace, data, content)
    if name == "ApproveDecision":
        return _approve_decision(workspace, data)
    if name == "CompleteAction":
        return _complete_action(workspace, data)
    if name == "AddEvidence":
        return _add_evidence(workspace, data)
    raise ValidationError("Unknown command.")
