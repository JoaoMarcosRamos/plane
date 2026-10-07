"""One authenticated, transactional entry point for every RADAR domain writer."""

import hashlib
import json
import math
from dataclasses import asdict, replace
from datetime import timedelta
from typing import Callable
from uuid import UUID, uuid4

from django.apps import apps
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from plane.db.models import Workspace
from plane.radar.models import (
    ActorGrant,
    CommandApproval,
    CommandExecution,
    DomainEvent,
    Object,
    ObjectType,
    PropertyDefinition,
    Provenance,
    RelationType,
)
from plane.radar.mutation import MutationContext, current_mutation, json_value
from plane.radar.ontology.schema import load_schema
from plane.radar.locks import lock_workspace, observed_atomic
from .actor import Actor
from .access import require_human_membership
from .inputs import CommandInput, INPUTS
from .rules import implementation_contract


class CommandConflict(APIException):
    status_code = 409
    default_code = "revision_conflict"


class ApprovalRequired(APIException):
    status_code = 409
    default_code = "approval_required"


def _hash(value) -> str:
    try:
        encoded = json.dumps(json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Use finite, JSON-compatible values.") from exc
    return hashlib.sha256(encoded.encode()).hexdigest()


def schema_fingerprint(workspace) -> str:
    """Approval binds to the effective workspace schema, including local defaults."""
    from plane.radar.workspace_schema import schema_revision
    from .capabilities import CAPABILITIES, GUARDS

    return _hash(
        {
            "rules": implementation_contract(),
            "capabilities": [asdict(capability) for capability in CAPABILITIES.values()],
            "guards": [asdict(guard) for guard in GUARDS.values()],
            "schema_revision": schema_revision(workspace),
            "types": list(
                ObjectType.objects.filter(workspace=workspace).order_by("pk").values("id", "key", "is_active", "rules")
            ),
            "properties": list(
                PropertyDefinition.objects.filter(workspace=workspace)
                .order_by("pk")
                .values("id", "object_type_id", "key", "value_type", "config", "is_required", "is_active")
            ),
            "relations": list(
                RelationType.objects.filter(workspace=workspace)
                .order_by("pk")
                .values(
                    "id",
                    "key",
                    "source_types",
                    "target_types",
                    "allowed_pairs",
                    "cardinality",
                    "allow_self",
                    "is_active",
                )
            ),
        }
    )


def command_envelope(execution: CommandExecution) -> dict:
    """Replay only client command fields; stored authority metadata stays server-owned."""
    fields = set(CommandInput().fields)
    return {key: value for key, value in execution.envelope.items() if key in fields}


def validate_actor(actor: Actor) -> None:
    if not isinstance(actor, Actor) or actor.actor_type not in {"human", "agent", "system", "integration"}:
        raise PermissionDenied("An explicit registered actor is required.")
    for field in ("actor_id", "correlation_id"):
        if not isinstance(getattr(actor, field), UUID):
            raise PermissionDenied(f"Actor {field} must be a UUID.")
    for field in ("run_id", "approval_id", "on_behalf_of"):
        value = getattr(actor, field)
        if value is not None and not isinstance(value, UUID):
            raise PermissionDenied(f"Actor {field} must be a UUID.")
    if not isinstance(actor.reason, str) or not actor.reason.strip():
        raise PermissionDenied("Actor reason is required.")
    if not isinstance(actor.source, str) or not actor.source.strip() or len(actor.source) > 255:
        raise PermissionDenied("Actor source is required (up to 255 characters).")
    if not hasattr(actor.timestamp, "tzinfo") or timezone.is_naive(actor.timestamp):
        raise PermissionDenied("Actor timestamp must include a timezone.")
    if actor.timestamp > timezone.now():
        # Tolerate transport latency and small clock skew, never accept future observations.
        if actor.timestamp > timezone.now() + timedelta(seconds=30):
            raise PermissionDenied("Actor timestamp is in the future.")
    if actor.confidence is not None and (
        type(actor.confidence) not in (int, float)
        or not math.isfinite(actor.confidence)
        or not 0 <= actor.confidence <= 1
    ):
        raise ValidationError({"confidence": "Use a finite number between 0 and 1."})
    if actor.actor_type == "agent" and actor.run_id is None:
        raise PermissionDenied("Agent actors require a run_id.")
    if not isinstance(actor.metadata, dict):
        raise ValidationError("Actor metadata must be a JSON object.")
    _hash(actor.metadata)


def authorize(actor: Actor, workspace: Workspace, command_name: str, *, read=False) -> ActorGrant | None:
    validate_actor(actor)
    from .capabilities import CAPABILITIES

    capability = CAPABILITIES.get(command_name)
    if capability and capability.human_only and actor.actor_type != "human":
        raise PermissionDenied("This capability requires a human actor.")
    if not Workspace.objects.filter(pk=workspace.pk).exists():
        raise NotFound("Workspace not found.")
    if actor.actor_type == "human":
        require_human_membership(actor, workspace, write=not read)
        return None
    if read or command_name not in INPUTS:
        raise PermissionDenied("Schema/control commands require a human actor.")
    grant = ActorGrant.objects.filter(
        workspace=workspace, actor_type=actor.actor_type, actor_id=actor.actor_id, is_active=True
    ).first()
    if grant is None or command_name not in grant.commands:
        raise PermissionDenied("No grant for this actor and command in this workspace.")
    require_human_membership(replace(actor, actor_type="human", actor_id=grant.delegator_id), workspace)
    if actor.on_behalf_of is not None and actor.on_behalf_of != grant.delegator_id:
        raise PermissionDenied("The actor does not represent this delegator.")
    return grant


def lock_expected_versions(workspace: Workspace, expected: dict, refs: set[UUID], *, read_dependencies=None) -> dict:
    try:
        normalized = {UUID(str(key)): value for key, value in expected.items()}
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"expected_versions": "Keys must be Object UUIDs."}) from exc
    objects = list(Object.objects.select_for_update().filter(workspace=workspace, pk__in=refs).order_by("pk"))
    if {obj.pk for obj in objects} != refs:
        raise NotFound("Object not found in this workspace.")
    implicit = {UUID(pk): value for pk, value in (read_dependencies or {}).items()}
    required = refs - set(implicit)
    if not required <= set(normalized) <= refs or any(type(v) is not int or v < 1 for v in normalized.values()):
        raise ValidationError({"expected_versions": "Provide every input/written Object version (integer >= 1)."})
    for obj in objects:
        if obj.version != normalized.get(obj.pk, implicit.get(obj.pk)):
            raise CommandConflict({"code": "revision_conflict", "object_id": str(obj.pk)})
    return {str(obj.pk): obj.version for obj in objects}


def _flush(context: MutationContext, command_id: UUID, outcome: str, extra=None) -> tuple[Provenance, list]:
    from plane.radar.workspace_schema import advance_schema_revision, schema_revision

    advance_schema_revision(context)
    actor = context.actor
    metadata = {
        "schema_revision": schema_revision(context.workspace_id),
        "actor": json_value(asdict(actor)),
        "schema_version": load_schema()["version"],
        "ontology_sha256": load_schema()["sha256"],
        "rules_contract": implementation_contract(),
        **(extra or {}),
    }
    provenance = Provenance.objects.create(
        workspace_id=context.workspace_id,
        command_id=command_id,
        command_name=context.command_name,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        reason=actor.reason,
        source=actor.source,
        correlation_id=actor.correlation_id,
        run_id=actor.run_id,
        approval_id=actor.approval_id,
        confidence=actor.confidence,
        context=json_value(metadata),
        changes=list(context.changes.values()),
        outcome=outcome,
    )
    context.provenance_id = provenance.pk
    try:
        for (label, pk), change in context.changes.items():
            model = apps.get_model(label)
            fields = {"last_provenance_id": provenance.pk}
            if change["before"] is None:
                fields["created_provenance_id"] = provenance.pk
            model.all_objects.filter(pk=pk).update(**fields)
    finally:
        context.provenance_id = None
    events = []
    versions_before = {
        change["id"]: change["before"]["version"]
        for change in context.changes.values()
        if change["model"] == "radar.Object" and change["before"] is not None
    }
    versions_after = {
        change["id"]: change["after"]["version"]
        for change in context.changes.values()
        if change["model"] == "radar.Object"
    }
    for event_type, payload in context.events:
        event = DomainEvent.objects.create(
            workspace_id=context.workspace_id,
            execution_id=command_id,
            provenance=provenance,
            event_type=event_type,
            payload=json_value(
                {
                    "command_id": command_id,
                    "correlation_id": actor.correlation_id,
                    "actor": asdict(actor),
                    "provenance_id": provenance.pk,
                    **payload,
                    "causation_id": metadata.get("proposal_id") or command_id,
                    "versions_before": versions_before,
                    "versions_after": versions_after,
                }
            ),
        )
        events.append(str(event.pk))
    return provenance, events


def emit(name: str, payload: dict) -> None:
    context = current_mutation.get()
    if context is None:
        raise RuntimeError("Domain events require a command context.")
    context.events.append((name, payload))


@observed_atomic
def run_internal(*, actor: Actor, workspace: Workspace, name: str, operation: Callable, read=False):
    """Audited human schema/control command; not an agent tool or a public raw writer."""
    parent = current_mutation.get()
    if parent is not None:
        if parent.actor != actor or parent.workspace_id != workspace.pk:
            raise PermissionDenied("Nested commands must preserve their Actor and workspace.")
        return operation()
    authorize(actor, workspace, name, read=read)
    lock_workspace(workspace, operation=name)
    context = MutationContext(actor, workspace.pk, name)
    token = current_mutation.set(context)
    try:
        result = operation()
        validate_bound_relations(context)
        if context.changes:
            emit(name, {"affected_ids": [change["id"] for change in context.changes.values()]})
            _flush(context, uuid4(), "executed")
        return result
    finally:
        current_mutation.reset(token)


def _result(context, execution, data, provenance, events, before):
    if execution.command_name == "InitializeObjectProperties":
        from plane.radar.authorship import AUTHOR_RELATIONS, object_authorship

        obj = Object.objects.select_related(*AUTHOR_RELATIONS).get(
            workspace_id=context.workspace_id, pk=data["object"]["id"]
        )
        data["object"].update(object_authorship([obj])[obj.pk])
    created = [change["id"] for change in context.changes.values() if change["before"] is None]
    object_ids = {pk for label, pk in context.changes if label == "radar.Object"}
    after = {str(obj.pk): obj.version for obj in Object.objects.filter(pk__in=object_ids)}
    return json_value(
        {
            "command_id": execution.pk,
            "status": "executed" if context.changes else "noop",
            "code": None,
            "correlation_id": context.actor.correlation_id,
            "created_ids": created,
            "affected_ids": [change["id"] for change in context.changes.values()],
            "versions_before": before,
            "versions_after": after,
            "event_ids": events,
            "provenance_id": provenance.pk,
            "approval_id": context.actor.approval_id,
            "proposal_id": execution.envelope.get("proposal_id"),
            "findings": data.pop("findings", []),
            "data": data,
        }
    )


@observed_atomic
def preview_command(*, actor, workspace, name, data, expected_schema_revision, evidence_ids=()):
    """Authorized planning without a ledger entry, provenance or persisted facts."""
    from plane.radar.workspace_schema import require_schema, check_schema_revision, schema_revision
    from .effects import plan_command, check_grant
    from .handlers import requires_human_review

    authorize(actor, workspace, name)
    lock_workspace(workspace, operation=name)
    grant = authorize(actor, workspace, name)
    if grant is not None and actor.on_behalf_of is None:
        actor = replace(actor, on_behalf_of=grant.delegator_id)
    require_schema(workspace)
    check_schema_revision(workspace, expected_schema_revision)
    if name not in INPUTS:
        raise ValidationError({"command_name": "Unknown command."})
    serializer = INPUTS[name](data=json_value(data))
    serializer.is_valid(raise_exception=True)
    plan = plan_command(
        actor=actor, workspace=workspace, name=name, data=serializer.validated_data, evidence_ids=evidence_ids
    )
    check_grant(workspace, grant, name, serializer.validated_data, plan=plan)
    return {
        "schema_revision": schema_revision(workspace),
        "expected_versions": plan.dependencies,
        "requires_review": requires_human_review(workspace, actor, grant, name, serializer.validated_data),
        "effect_plan": plan.as_dict(),
    }


@observed_atomic
def execute_command(*, actor: Actor, workspace: Workspace, envelope: dict, upload=None) -> dict:
    """Actor is authenticated by the caller, never reconstructed from arbitrary JSON."""
    from .handlers import dispatch, references, requires_human_review
    from .legacy_replay import legacy_check_grant, legacy_references
    from .capabilities import get_capability
    from .effects import plan_command, check_grant, capture_plan, verify_plan

    validate_actor(actor)
    parent = current_mutation.get()
    if parent is not None and (parent.actor != actor or parent.workspace_id != workspace.pk):
        raise PermissionDenied("Nested commands must preserve their Actor and workspace.")
    parsed = CommandInput(data=json_value(envelope))
    parsed.is_valid(raise_exception=True)
    request = parsed.validated_data
    name = request["command_name"]
    if name not in INPUTS:
        raise ValidationError({"command_name": "Unknown command."})
    if request.get("workspace_id", workspace.pk) != workspace.pk:
        raise NotFound("Workspace not found.")
    if request["reason"].strip() != actor.reason.strip():
        raise ValidationError({"reason": "Must match the authenticated Actor context."})
    assertion = request["assertion"]
    confidence = assertion.get("confidence", actor.confidence)
    if actor.confidence is not None and "confidence" in assertion and actor.confidence != confidence:
        raise ValidationError({"confidence": "Actor and assertion must agree."})
    approval_id = request.get("approval_id", actor.approval_id)
    if actor.approval_id is not None and approval_id != actor.approval_id:
        raise ValidationError({"approval_id": "Actor and command must agree."})
    actor = replace(actor, confidence=confidence, approval_id=approval_id)
    grant = authorize(actor, workspace, name)
    # A workspace lock also serializes changes to grants, schema and approval authority.
    # Object locks below still enforce exact revisions. No lock spans another workspace.
    lock_workspace(workspace, operation=name)
    grant = authorize(actor, workspace, name)
    if grant is not None and actor.on_behalf_of is None:
        actor = replace(actor, on_behalf_of=grant.delegator_id)
    serializer = INPUTS[name](data=request["input"])
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    intent = {key: value for key, value in request.items() if key not in {"approval_id", "workspace_id"}}
    intent["input"] = data
    intent["ontology_sha256"] = load_schema()["sha256"]
    intent["actor_scope"] = {
        "source": actor.source,
        "run_id": actor.run_id,
        "on_behalf_of": actor.on_behalf_of,
        "confidence": actor.confidence,
        **({"metadata": actor.metadata} if actor.metadata else {}),
    }
    execution = CommandExecution.objects.filter(
        workspace=workspace,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        idempotency_key=request["idempotency_key"],
    ).first()
    if execution is not None and execution.status == "pending_approval":
        if execution.envelope.get("rules_contract") != implementation_contract():
            raise CommandConflict({"code": "approval_stale"})
    if execution is None or "rules_contract" in execution.envelope:
        intent["rules_contract"] = (
            execution.envelope["rules_contract"] if execution is not None else implementation_contract()
        )
    intent_hash = _hash(intent)
    if execution is not None:
        if execution.intent_hash != intent_hash:
            raise CommandConflict({"code": "idempotency_conflict"})
        if execution.status in {"executed", "noop"}:
            if "effect_plan" in execution.envelope:
                check_grant(workspace, grant, name, data, plan=execution.envelope["effect_plan"])
            else:
                legacy_check_grant(workspace, grant, name, data, legacy_references(workspace, name, data))
            return execution.result
        if execution.status == "rejected":
            raise PermissionDenied("This intention was rejected; submit a new proposal.")
    else:
        execution = CommandExecution.objects.create(
            workspace=workspace,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            idempotency_key=request["idempotency_key"],
            intent_hash=intent_hash,
            command_name=name,
            envelope=json_value(
                {**request, "schema_hash": schema_fingerprint(workspace), "rules_contract": implementation_contract()}
            ),
            actor_context=json_value(asdict(actor)),
        )
    from plane.radar.workspace_schema import require_schema, check_schema_revision

    if execution.status == "pending_approval" and execution.envelope["schema_hash"] != schema_fingerprint(workspace):
        raise CommandConflict({"code": "approval_stale"})
    if request.get("proposal_id"):
        proposal = CommandExecution.objects.filter(
            pk=request["proposal_id"], workspace=workspace, actor_type="agent", status="rejected"
        ).first()
        if proposal is None or actor.actor_type != "human":
            raise ValidationError(
                {"proposal_id": "Human takeover requires a retired agent proposal in this workspace."}
            )
    declared_refs = references(workspace, name, data) | set(assertion["evidence_ids"])
    known = set(
        Object.objects.select_for_update()
        .filter(workspace=workspace, pk__in=declared_refs)
        .values_list("pk", flat=True)
    )
    if known != declared_refs:
        raise NotFound("Object not found in this workspace.")
    require_schema(workspace)
    if "expected_schema_revision" in request:
        check_schema_revision(workspace, request["expected_schema_revision"])
    plan = plan_command(
        actor=actor, workspace=workspace, name=name, data=data, evidence_ids=assertion["evidence_ids"], upload=upload
    )
    refs = {UUID(pk) for pk in plan.dependencies}
    read_dependencies = {pk: value for pk, value in plan.dependencies.items() if pk not in plan.required_versions}
    before = lock_expected_versions(workspace, request["expected_versions"], refs, read_dependencies=read_dependencies)
    check_grant(workspace, grant, name, data, plan=plan)
    if execution.status == "pending_approval":
        verify_plan(execution.envelope.get("effect_plan"), plan.as_dict(), stale=True)
    else:
        execution.envelope = {**execution.envelope, "effect_plan": plan.as_dict()}
        execution.save(update_fields=["envelope"])
    if execution.status == "pending_approval" and actor.approval_id is None:
        return execution.result
    context = MutationContext(actor, workspace.pk, name, upload=upload)
    token = current_mutation.set(context)
    try:
        approval = None
        needed = requires_human_review(workspace, actor, grant, name, data)
        if needed:
            if execution.envelope["schema_hash"] != schema_fingerprint(workspace):
                raise CommandConflict({"code": "approval_stale"})
            preview = plan.as_dict()
            approval, _ = CommandApproval.objects.get_or_create(
                execution=execution,
                defaults={
                    "workspace": workspace,
                    "intent_hash": intent_hash,
                    "policy_version": grant.policy_version if grant else 1,
                    "expires_at": timezone.now() + timedelta(minutes=30),
                },
            )
            if actor.approval_id is None:
                if approval.status == "rejected":
                    raise PermissionDenied("Command approval was rejected.")
                emit("CommandApprovalRequested", {"approval_id": approval.pk, "command_id": execution.pk})
                provenance, events = _flush(
                    context,
                    execution.pk,
                    "pending_approval",
                    {
                        "intent_hash": intent_hash,
                        "input": data,
                        "assertion": assertion,
                        "expected_versions": before,
                        "schema_hash": execution.envelope["schema_hash"],
                    },
                )
                result = json_value(
                    {
                        "command_id": execution.pk,
                        "status": "pending_approval",
                        "code": "approval_required",
                        "correlation_id": actor.correlation_id,
                        "created_ids": [],
                        "affected_ids": [],
                        "versions_before": {},
                        "versions_after": {},
                        "event_ids": events,
                        "provenance_id": provenance.pk,
                        "approval_id": approval.pk,
                        "proposal_id": execution.pk if actor.actor_type == "agent" else None,
                        "findings": [],
                        "data": {"effect_plan": preview},
                    }
                )
                execution.status, execution.result = "pending_approval", result
                execution.save(update_fields=["status", "result"])
                return result
            if (
                approval.pk != actor.approval_id
                or approval.status != "approved"
                or approval.intent_hash != intent_hash
                or approval.expires_at <= timezone.now()
                or approval.policy_version != (grant.policy_version if grant else 1)
            ):
                raise CommandConflict({"code": "approval_stale"})
            reviewer = replace(actor, actor_type="human", actor_id=approval.approver_id)
            require_human_membership(reviewer, workspace)
        elif actor.approval_id is not None:
            raise ValidationError({"approval_id": "This command does not require an execution approval."})
        data_result = dispatch(workspace, name, data)
        validate_bound_relations(context)
        actual = capture_plan(workspace, get_capability(name), data, context, declared_refs)
        verify_plan(plan.as_dict(), actual.as_dict())
        if approval is not None:
            approval.status = "consumed"
            approval.save(update_fields=["status", "updated_at"])
        outcome = "executed" if context.changes else "noop"
        provenance, events = _flush(
            context,
            execution.pk,
            outcome,
            {
                "intent_hash": intent_hash,
                "input": data,
                "assertion": assertion,
                "expected_versions": before,
                "grant_id": str(grant.pk) if grant else None,
                "policy_version": grant.policy_version if grant else 1,
                "approver_id": str(approval.approver_id) if approval else None,
                "proposal_id": request.get("proposal_id"),
                "initiator": execution.actor_context,
                "schema_hash": schema_fingerprint(workspace),
                "decision_approval_id": data_result.get("decision_approval_id"),
                "effect_plan": plan.as_dict(),
            },
        )
        result = _result(context, execution, data_result, provenance, events, before)
        execution.status, execution.result = result["status"], result
        execution.save(update_fields=["status", "result"])
        return result
    finally:
        current_mutation.reset(token)


def validate_bound_relations(context: MutationContext) -> None:
    from plane.radar.models import RuntimeObjectIdentity
    from plane.radar.active import active_objects
    from .primitives_semantic import validate_required_relations

    ids = context.created_objects | context.touched | {pk for label, pk in context.changes if label == "radar.Object"}
    for identity in RuntimeObjectIdentity.objects.filter(
        workspace_id=context.workspace_id,
        object_id__in=active_objects(context.workspace_id).filter(pk__in=ids).values("pk"),
    ).select_related("object__object_type", "object__workspace"):
        validate_required_relations(identity.object, context=identity.context)
