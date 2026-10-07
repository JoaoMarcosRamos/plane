"""Workspace runtime opt-in and registered external identity strategies (Core C19).

Eligibility never creates a binding, credential or grant. Current reads share this
policy; historical identities remain immutable and readable through provenance.
"""

import re
from dataclasses import dataclass
from uuid import uuid4

from rest_framework.exceptions import PermissionDenied, ValidationError

from plane.radar.active import active_objects, active_types
from plane.radar.models import RuntimeObjectIdentity

CONTEXT_KINDS = frozenset({"company", "manager"})
CONTEXT = re.compile(r"(company|manager):[A-Za-z0-9_.-]{1,120}")
PREFIX = re.compile(r"[A-Z][A-Z0-9]{1,15}")


@dataclass(frozen=True)
class DatedTokenIdentity:
    """The existing PREFIX-YYYYMMDD-TOKEN wire format; dates/IDs are never rewritten."""

    def accepts(self, external_id, prefix):
        return isinstance(external_id, str) and bool(
            re.fullmatch(re.escape(prefix) + r"-\d{8}-[A-Z0-9]{6}", external_id)
        )

    def generate(self, prefix, at):
        return f"{prefix}-{at:%Y%m%d}-{uuid4().hex[:6].upper()}"


IDENTITY_STRATEGIES = {"dated_token_v1": DatedTokenIdentity()}


def validate_runtime_descriptor(descriptor):
    if not isinstance(descriptor, dict) or type(descriptor.get("enabled")) is not bool:
        raise ValidationError({"runtime": "Declare an explicit enabled boolean."})
    if not descriptor["enabled"]:
        if set(descriptor) != {"enabled"}:
            raise ValidationError({"runtime": "A disabled runtime declares enabled only."})
        return descriptor
    if set(descriptor) != {"enabled", "identity", "contexts"}:
        raise ValidationError({"runtime": "Declare enabled, identity and allowed context kinds only."})
    identity, contexts = descriptor["identity"], descriptor["contexts"]
    if (
        not isinstance(identity, dict)
        or set(identity) != {"strategy", "prefix"}
        or not isinstance(identity["strategy"], str)
        or identity["strategy"] not in IDENTITY_STRATEGIES
        or not isinstance(identity["prefix"], str)
        or not PREFIX.fullmatch(identity["prefix"])
    ):
        raise ValidationError(
            {"runtime": "Select a registered identity strategy and a 2–16 character uppercase prefix."}
        )
    if (
        not isinstance(contexts, list)
        or not contexts
        or not all(isinstance(value, str) and value in CONTEXT_KINDS for value in contexts)
        or len(set(contexts)) != len(contexts)
    ):
        raise ValidationError({"runtime": "Use unique company/manager context kinds."})
    return descriptor


def context_kind(context):
    if not isinstance(context, str) or not CONTEXT.fullmatch(context) or len(context) > 128:
        raise ValidationError({"context": "Use a declared company/manager context, up to 128 characters."})
    return context.split(":", 1)[0]


def runtime_descriptor(object_type, *, context=None):
    if not isinstance(object_type.rules, dict):
        raise ValidationError({"runtime": "Object type rules must be an object."})
    descriptor = validate_runtime_descriptor((object_type.rules or {}).get("runtime", {"enabled": False}))
    if not descriptor["enabled"]:
        raise PermissionDenied("This Object type is not enabled for runtime integration.")
    if context is not None and context_kind(context) not in descriptor["contexts"]:
        raise PermissionDenied("This Object type is not enabled for this context kind.")
    return descriptor


def runtime_types(workspace, *, context=None):
    """Fail closed for retired or malformed metadata, including metadata from legacy imports."""
    allowed = []
    for row in active_types(workspace).only("id", "key", "rules"):
        try:
            runtime_descriptor(row, context=context)
        except (ValidationError, PermissionDenied):
            continue
        allowed.append(row.pk)
    return active_types(workspace).filter(pk__in=allowed)


def runtime_identities(workspace, context):
    context_kind(context)
    return RuntimeObjectIdentity.objects.filter(
        workspace=workspace,
        context=context,
        object_id__in=active_objects(workspace)
        .filter(object_type__in=runtime_types(workspace, context=context))
        .values("pk"),
    )


def validate_binding_compatibility(workspace, object_type, descriptor):
    """Revocation is allowed; changing the contract must preserve every historical binding."""
    descriptor = validate_runtime_descriptor(descriptor)
    if not descriptor["enabled"]:
        return
    identity = descriptor["identity"]
    for binding in RuntimeObjectIdentity.all_objects.filter(workspace=workspace, object__object_type=object_type):
        if context_kind(binding.context) not in descriptor["contexts"] or not IDENTITY_STRATEGIES[
            identity["strategy"]
        ].accepts(binding.external_id, identity["prefix"]):
            raise ValidationError(
                {"runtime": "Existing identities require an explicit migration before changing this contract."}
            )


def bind_identity(workspace, obj, context, *, user_id, external_id=None, at=None):
    """Only called in a coordinated command. Both provisioning and composed effects use it."""
    descriptor = runtime_descriptor(obj.object_type, context=context)
    identity = descriptor["identity"]
    strategy = IDENTITY_STRATEGIES[identity["strategy"]]
    from plane.radar.commands.primitives_semantic import validate_required_relations
    from plane.radar.mutation import current_mutation

    mutation = current_mutation.get()
    # A composed capability can bind a newly created Object before assembling its
    # links. The dispatcher validates the final graph at the end of the command.
    if external_id is not None or mutation is None or obj.pk not in mutation.created_objects:
        validate_required_relations(obj, context=context)
    existing = RuntimeObjectIdentity.all_objects.filter(workspace=workspace, object=obj).first()
    if existing:
        if (
            existing.deleted_at
            or existing.context != context
            or external_id is not None
            and existing.external_id != external_id
        ):
            raise ValidationError("Runtime identity is immutable.")
        return existing
    if external_id is None:
        if at is None:
            raise ValidationError("Identity generation requires a command timestamp.")
        # Workspace coordination serializes writers; the database unique constraint remains the final guard.
        for _ in range(16):
            external_id = strategy.generate(identity["prefix"], at)
            if not RuntimeObjectIdentity.all_objects.filter(workspace=workspace, external_id=external_id).exists():
                break
        else:
            raise ValidationError("Unable to allocate a unique runtime identity.")
    if not strategy.accepts(external_id, identity["prefix"]):
        raise ValidationError({"external_id": "Use the identity format declared by this workspace Object type."})
    if RuntimeObjectIdentity.all_objects.filter(workspace=workspace, external_id=external_id).exists():
        raise ValidationError({"external_id": "This runtime identity is already bound in this workspace."})
    return RuntimeObjectIdentity.objects.create(
        workspace=workspace,
        object=obj,
        context=context,
        external_id=external_id,
        created_by_id=user_id,
        updated_by_id=user_id,
    )
