"""Transactional plans: the same effects drive preview, grants and execution.

The conservative workspace lock is held by the caller. A registered handler is
exercised under a rolled-back savepoint, including its executable guards. This
extends the existing approval preview rather than introducing a second writer.
Handlers may only write transactionally; external I/O belongs in the outbox.
"""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from plane.radar.models import Object, PropertyDefinition
from plane.radar.mutation import MutationContext, current_mutation, json_value
from .capabilities import get_capability, resolve


AUDIT_TIMES = {"created_at", "updated_at", "deleted_at"}


def effect_preview(context):
    aliases = {}
    counts = {}
    for change in context.changes.values():
        if change["before"] is None:
            model = change["model"]
            counts[model] = counts.get(model, 0) + 1
            aliases[change["id"]] = f"$new:{model}:{counts[model]}"

    def symbolic(value, key=None):
        if isinstance(value, dict):
            return {k: symbolic(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [symbolic(v) for v in value]
        if isinstance(value, str) and value in context.server_times:
            return "$server_timestamp"
        return aliases.get(value, value) if isinstance(value, str) else value

    changes = []
    for change in context.changes.values():
        normalized = symbolic(change)
        for side in ("before", "after"):
            if normalized[side]:
                for key in AUDIT_TIMES:
                    if normalized[side].get(key) is not None:
                        normalized[side][key] = "$server_timestamp"
        if change["model"] == "radar.RuntimeObjectIdentity" and change["before"] is None:
            normalized["after"]["external_id"] = (
                f"$server_identity:{change['after']['external_id'].rsplit('-', 2)[0]}:{aliases[change['id']]}"
            )
        changes.append(normalized)
    return {
        "preview_only": True,
        "changes": changes,
        "events": [{"event_type": name, "payload": symbolic(json_value(payload))} for name, payload in context.events],
        "payloads": symbolic(context.payloads),
    }


@dataclass(frozen=True)
class EffectPlan:
    preview: dict
    dependencies: dict
    required_versions: dict
    object_types: tuple[str, ...]
    fields: tuple[str, ...]
    commands: tuple[str, ...]
    human_only: bool

    def as_dict(self):
        return json_value(
            {
                **self.preview,
                "dependencies": self.dependencies,
                "required_versions": self.required_versions,
                "authority": {
                    "object_types": self.object_types,
                    "fields": self.fields,
                    "commands": self.commands,
                    "human_only": self.human_only,
                },
                "contract": "transactional_effects_v1",
            }
        )


def capture_plan(workspace, capability, data, context, refs):
    required = {str(pk) for pk in refs}
    dependencies = {
        str(pk): version for pk, version in context.dependencies.items() if pk not in context.created_objects
    }
    for obj in Object.objects.filter(workspace=workspace, pk__in=refs):
        dependencies.setdefault(str(obj.pk), obj.version)
    types = set(
        Object.objects.filter(workspace=workspace, pk__in=dependencies).values_list("object_type__key", flat=True)
    )
    fields, commands = capability.field_scope(data), {capability.name}
    if capability.composed_capability:
        composed = resolve(capability.composed_capability)(workspace, data)
        if composed:
            commands.add(composed)
    for change in context.changes.values():
        model, before, after = change["model"], change["before"], change["after"]
        from django.apps import apps

        # Writes to a child row also require the Object's reviewed version.
        for field in apps.get_model(model)._meta.concrete_fields:
            if field.is_relation and field.related_model._meta.label == "radar.Object" and after[field.attname]:
                required.add(after[field.attname])
        if model == "radar.Object":
            obj = Object.objects.select_related("object_type").get(pk=change["id"])
            types.add(obj.object_type.key)
            if before is not None:
                dependencies[str(obj.pk)] = before["version"]
                required.add(str(obj.pk))
            fields.update(field for field in ("title", "content") if before is None or before[field] != after[field])
        elif model == "radar.PropertyValue":
            fields.add(PropertyDefinition.all_objects.get(pk=after["definition_id"]).key)
        elif model == "radar.Relation":
            commands.add("UnlinkObjects" if after["deleted_at"] else "LinkObjects")
        elif model == "radar.OperationalRecord":
            fields.update(
                key for key, value in after["data"].items() if before is None or before["data"].get(key) != value
            )
        elif model == "radar.OperationalEntry":
            fields.add({"delegation": "assignment", "review": "review", "measurement": "measurement"}[after["kind"]])
    # Observation while computing requested derived fields is also part of the plan.
    dependencies.update(
        {str(pk): version for pk, version in context.dependencies.items() if pk not in context.created_objects}
    )
    return EffectPlan(
        effect_preview(context),
        dependencies,
        {pk: dependencies[pk] for pk in sorted(required) if pk in dependencies},
        tuple(sorted(types)),
        tuple(sorted(fields)),
        tuple(sorted(commands)),
        capability.is_human_only(workspace, data),
    )


def plan_handler(*, actor, workspace, capability, data, refs, upload=None):
    from .execution import validate_bound_relations

    context = MutationContext(actor, workspace.pk, capability.name, upload=upload)
    token = current_mutation.set(context)
    try:
        with transaction.atomic():
            capability.execute(workspace, data)
            validate_bound_relations(context)
            plan = capture_plan(workspace, capability, data, context, refs)
            transaction.set_rollback(True)
        return plan
    finally:
        current_mutation.reset(token)


def plan_command(*, actor, workspace, name, data, evidence_ids=(), upload=None):
    """Called under a workspace lock; callers must authenticate/authorize first."""
    capability = get_capability(name)
    if capability.is_human_only(workspace, data) and actor.actor_type != "human":
        raise PermissionDenied("This capability is human-only.")
    refs = capability.references(workspace, data) | {UUID(str(pk)) for pk in evidence_ids}
    from plane.radar.active import active_objects
    from rest_framework.exceptions import NotFound

    known = set(active_objects(workspace).select_for_update().filter(pk__in=refs).values_list("pk", flat=True))
    if known != refs:
        raise NotFound("Active dependency not found in this workspace.")
    return resolve(capability.planner)(
        actor=actor, workspace=workspace, capability=capability, data=data, refs=refs, upload=upload
    )


def check_grant(workspace, grant, name, data, refs=None, *, plan):
    authority = plan.as_dict()["authority"] if isinstance(plan, EffectPlan) else plan["authority"]
    if authority["human_only"] and grant is not None:
        raise PermissionDenied("This capability is human-only.")
    if grant is None:
        return
    for scope in ("commands", "object_types", "fields"):
        allowed = set(getattr(grant, scope))
        if (scope == "commands" or "*" not in allowed) and not set(authority[scope]).issubset(allowed):
            raise PermissionDenied(f"Grant does not cover every planned {scope} effect.")
    if "context" in data:
        from .operations import check_context

        dependencies = plan.dependencies if isinstance(plan, EffectPlan) else plan["dependencies"]
        check_context(workspace, data, {UUID(pk) for pk in dependencies})


def verify_plan(expected, actual, *, stale=False):
    from .execution import CommandConflict

    if expected != actual:
        raise CommandConflict({"code": "approval_stale" if stale else "effect_plan_conflict"})
