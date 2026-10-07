"""Explicit admin installation, previewed package upgrades and guarded local metadata edits."""

from copy import deepcopy
from types import SimpleNamespace
from django.db import transaction
from django.db.models import Count
from rest_framework.exceptions import ValidationError, NotFound
from plane.radar.models import Object, ObjectType, PropertyValue, Relation, WorkspaceSchemaState, SchemaUpgrade
from plane.radar.ontology.contracts import validate_property_config, validate_relation_descriptor
from plane.radar.ontology.package import package_definitions, package_hash
from plane.radar.ontology.schema import load_schema
from plane.radar.workspace_schema import (
    MODELS,
    SchemaConflict,
    check_schema_revision,
    metadata_records,
    record_spec,
    legacy_base,
    lock_schema,
    require_schema,
)
from .control import require_workspace_admin
from .execution import run_internal
from .primitives_semantic import validate_value
from .rules import effective_invariants

ABSENT = object()


def three_way(base, local, candidate, path=""):
    """Merge individual config fields, treating ordered lists as atomic values."""
    if all(isinstance(item, dict) for item in (base, local, candidate)):
        merged, conflicts = {}, []
        for key in sorted(set(base) | set(local) | set(candidate)):
            value, found = three_way(
                base.get(key, ABSENT), local.get(key, ABSENT), candidate.get(key, ABSENT), f"{path}.{key}"
            )
            if value is not ABSENT:
                merged[key] = value
            conflicts.extend(found)
        return merged, conflicts
    if candidate == base or candidate == local:
        return deepcopy(local) if local is not ABSENT else ABSENT, []
    if local == base:
        return deepcopy(candidate) if candidate is not ABSENT else ABSENT, []
    return deepcopy(local) if local is not ABSENT else ABSENT, [path.lstrip(".")]


def validate_fact_compatibility(workspace, row, spec):
    """Refuse changes that require migrating existing facts; never rewrite their values."""
    if row._meta.model_name == "objecttype":
        from plane.radar.runtime_identity import validate_binding_compatibility

        validate_binding_compatibility(workspace, row, spec.get("rules", {}).get("runtime", {"enabled": False}))
    if row._meta.model_name == "propertydefinition":
        validate_property_config(spec["value_type"], spec["config"])
        if row.value_type != spec["value_type"]:
            raise ValidationError({row.key: "Kind changes require an explicit fact migration."})
        candidate = SimpleNamespace(key=row.key, value_type=spec["value_type"], config=spec["config"])
        if "default" in spec["config"]:
            validate_value(candidate, spec["config"]["default"], workspace)
        for value in PropertyValue.objects.filter(workspace=workspace, definition=row).iterator():
            validate_value(candidate, value.value, workspace)
        if (
            spec["is_required"]
            and "default" not in spec["config"]
            and Object.objects.filter(workspace=workspace, object_type=row.object_type, deleted_at__isnull=True)
            .exclude(pk__in=PropertyValue.objects.filter(definition=row).values("object_id"))
            .exists()
        ):
            raise ValidationError({row.key: "Required property needs values/default or an explicit fact migration."})
    if row._meta.model_name == "relationtype":
        known = set(ObjectType.objects.filter(workspace=workspace).values_list("key", flat=True))
        validate_relation_descriptor(spec, known)
        edges = Relation.objects.filter(workspace=workspace, relation_type=row).select_related(
            "source__object_type", "target__object_type"
        )
        if (
            spec["cardinality"] in {"0..1", "1..1"}
            and edges.values("source_id").annotate(n=Count("id")).filter(n__gt=1).exists()
        ):
            raise ValidationError({row.key: "Cardinality reduction requires an explicit relation migration."})
        for edge in edges.iterator():
            source, target = edge.source.object_type.key, edge.target.object_type.key
            if (
                "*" not in spec["source_types"]
                and source not in spec["source_types"]
                or "*" not in spec["target_types"]
                and target not in spec["target_types"]
                or spec["allowed_pairs"]
                and [source, target] not in spec["allowed_pairs"]
                or not spec["allow_self"]
                and edge.source_id == edge.target_id
            ):
                raise ValidationError({row.key: "Existing edges do not satisfy the candidate descriptor."})
        if spec["cardinality"] == "1..1" and row.cardinality != "1..1":
            sources = Object.objects.filter(workspace=workspace)
            if "*" not in spec["source_types"]:
                sources = sources.filter(object_type__key__in=spec["source_types"])
            if sources.exclude(pk__in=edges.values("source_id")).exists():
                raise ValidationError({row.key: "Required relation needs an explicit relation migration."})


def validate_effective_schema(workspace):
    from plane.radar.active import active_types, active_definitions, active_objects
    from .descriptors import validate_effective_descriptors
    from .primitives_semantic import effective_values
    from .rules import evaluate_invariants

    for kind in active_types(workspace):
        definitions = {row.key: row for row in active_definitions(workspace).filter(object_type=kind)}
        validate_effective_descriptors(kind, definitions)
        invariants = effective_invariants(kind, definitions)
        if invariants:
            for obj in active_objects(workspace).filter(object_type=kind):
                values = effective_values(obj)
                derived = evaluate_invariants(invariants, values, values)
                if any(values.get(key) != value for key, value in derived.items()):
                    raise ValidationError({"rules": "Existing derived facts require an explicit migration."})


def validate_metadata_fields(spec):
    for field, value in spec.items():
        if field in {"is_active", "is_required", "allow_self"} and type(value) is not bool:
            raise ValidationError({field: "Use a boolean."})
        if field in {"name", "forward_label", "reverse_label", "description", "icon"}:
            limit = 64 if field == "icon" else 100 if field != "description" else None
            if not isinstance(value, str) or limit is not None and len(value) > limit:
                raise ValidationError({field: "Use text within the declared field length."})


def validate_new_definition(workspace, key, spec):
    validate_metadata_fields(spec)
    if key.startswith("properties:"):
        type_key, prop_key = key.split(":", 1)[1].split(".", 1)
        validate_property_config(spec["value_type"], spec["config"])
        if (
            spec["is_required"]
            and "default" not in spec["config"]
            and Object.objects.filter(workspace=workspace, object_type__key=type_key).exists()
        ):
            raise ValidationError({prop_key: "New required property needs a default or an explicit fact migration."})


def create_definition(workspace, key, spec, user_id):
    validate_new_definition(workspace, key, spec)
    group, identifier = key.split(":", 1)
    args = {"workspace": workspace, "is_system": True, "created_by_id": user_id, "updated_by_id": user_id, **spec}
    if group == "properties":
        type_key, prop_key = identifier.split(".", 1)
        args.update(object_type=ObjectType.objects.get(workspace=workspace, key=type_key), key=prop_key)
    else:
        args["key"] = identifier
    return MODELS[group].objects.create(**args)


@transaction.atomic
def install_schema(*, actor, workspace):
    def operation():
        require_workspace_admin(actor, workspace)
        state = WorkspaceSchemaState.objects.filter(workspace=workspace).first()
        if state is not None:
            return state
        definitions = package_definitions()
        existing = metadata_records(workspace)
        if existing:
            base, divergences = legacy_base(workspace)
            state = WorkspaceSchemaState.objects.create(
                workspace=workspace,
                origin="legacy",
                installed_base=base,
                divergences=divergences,
                created_by_id=actor.actor_id,
                updated_by_id=actor.actor_id,
            )
            return state
        ids = {}
        for key, spec in definitions.items():
            ids[key] = str(create_definition(workspace, key, spec, actor.actor_id).pk)
        state = WorkspaceSchemaState.objects.create(
            workspace=workspace,
            origin="package",
            package_version=load_schema()["version"],
            package_hash=package_hash(definitions),
            installed_base={"definitions": definitions, "ids": ids},
            created_by_id=actor.actor_id,
            updated_by_id=actor.actor_id,
        )
        SchemaUpgrade.objects.create(
            workspace=workspace,
            to_version=state.package_version,
            package_hash=state.package_hash,
            diff={"kind": "install", "created": list(ids)},
            created_by_id=actor.actor_id,
            updated_by_id=actor.actor_id,
        )
        return state

    result = run_internal(actor=actor, workspace=workspace, name="InstallWorkspaceSchema", operation=operation)
    result.refresh_from_db()
    return result


def upgrade_plan(workspace, definitions):
    state = WorkspaceSchemaState.objects.get(workspace=workspace)
    base = state.installed_base.get("definitions", {})
    ids = state.installed_base.get("ids", {})
    records = metadata_records(workspace)
    changes, conflicts, preserved = {}, [], []
    for key in sorted(
        set(base) | set(definitions),
        key=lambda key: (key.split(":")[0] != "types", key.split(":")[0] == "relations", key),
    ):
        group = key.split(":", 1)[0]
        row = MODELS[group].all_objects.filter(pk=ids.get(key), workspace=workspace).first() if ids.get(key) else None
        candidate = definitions.get(key)
        if row is None:
            if key in records:
                conflicts.append({"key": key, "fields": ["unmanaged_definition"]})
            elif candidate is not None:
                changes[key] = {"id": None, "after": candidate}
            continue
        if row.deleted_at:
            preserved.append({"key": key, "reason": "deleted"})
            continue
        old = base.get(key, {})
        local = record_spec(row, old)
        if candidate is None:
            candidate = {**old, "is_active": False}
        merged, fields = three_way(old, local, candidate)
        # Explicit retirement always wins over package activity changes.
        if not row.is_active:
            merged["is_active"] = False
            fields = [f for f in fields if f != "is_active"]
            preserved.append({"key": key, "reason": "inactive"})
        if fields:
            conflicts.append({"key": key, "fields": fields})
        elif merged != local:
            changes[key] = {"id": str(row.pk), "after": merged}
    blockers = []
    for key, change in changes.items():
        if change["id"] is None:
            try:
                validate_new_definition(workspace, key, change["after"])
            except ValidationError as exc:
                blockers.append({"key": key, "detail": exc.detail})
        if change["id"] is not None:
            row = MODELS[key.split(":")[0]].objects.get(pk=change["id"], workspace=workspace)
            try:
                validate_metadata_fields(change["after"])
                validate_fact_compatibility(workspace, row, change["after"])
            except ValidationError as exc:
                blockers.append({"key": key, "detail": exc.detail})
    return {
        "schema_revision": state.revision,
        "changes": changes,
        "conflicts": conflicts,
        "preserved": preserved,
        "candidate_hash": package_hash(definitions),
        "migration_blockers": blockers,
    }


@transaction.atomic
def preview_upgrade(*, actor, workspace, expected_revision, definitions=None):
    require_workspace_admin(actor, workspace)
    lock_schema(workspace)
    require_schema(workspace)
    check_schema_revision(workspace, expected_revision)
    return upgrade_plan(workspace, definitions or package_definitions())


@transaction.atomic
def upgrade_schema(*, actor, workspace, expected_revision, reviewed_hash, definitions=None, version=None):
    definitions = deepcopy(definitions if definitions is not None else package_definitions())
    version = version or load_schema()["version"]

    def operation():
        require_workspace_admin(actor, workspace)
        require_schema(workspace)
        check_schema_revision(workspace, expected_revision)
        plan = upgrade_plan(workspace, definitions)
        if reviewed_hash != plan["candidate_hash"] or plan["conflicts"] or plan["migration_blockers"]:
            raise SchemaConflict({"code": "schema_upgrade_conflict", "plan": plan})
        state = WorkspaceSchemaState.objects.get(workspace=workspace)
        if state.package_hash == reviewed_hash and state.package_version == version:
            return state
        ids = deepcopy(state.installed_base.get("ids", {}))
        for key, change in plan["changes"].items():
            if change["id"] is None:
                row = create_definition(workspace, key, change["after"], actor.actor_id)
                ids[key] = str(row.pk)
            else:
                row = MODELS[key.split(":")[0]].objects.get(pk=change["id"], workspace=workspace)
                validate_fact_compatibility(workspace, row, change["after"])
                for field, value in change["after"].items():
                    setattr(row, field, value)
                row.updated_by_id = actor.actor_id
                row.save()
        validate_effective_schema(workspace)
        SchemaUpgrade.objects.create(
            workspace=workspace,
            from_version=state.package_version,
            to_version=version,
            package_hash=reviewed_hash,
            diff=plan,
            created_by_id=actor.actor_id,
            updated_by_id=actor.actor_id,
        )
        state.package_version, state.package_hash, state.origin = version, reviewed_hash, "package"
        state.installed_base = {"definitions": definitions, "ids": ids}
        state.divergences = plan["preserved"]
        # A package/base-only change still invalidates approvals and open forms.
        if not plan["changes"]:
            state.revision += 1
        state.updated_by_id = actor.actor_id
        state.save()
        return state

    state = run_internal(actor=actor, workspace=workspace, name="UpgradeWorkspaceSchema", operation=operation)
    state.refresh_from_db()
    return state


@transaction.atomic
def update_metadata(*, actor, workspace, group, definition_id, patch, expected_revision):
    def operation():
        require_workspace_admin(actor, workspace)
        require_schema(workspace)
        check_schema_revision(workspace, expected_revision)
        if group not in MODELS or not isinstance(patch, dict) or not patch:
            raise ValidationError("Select a metadata group and nonempty patch.")
        try:
            row = MODELS[group].objects.get(pk=definition_id, workspace=workspace)
        except MODELS[group].DoesNotExist as exc:
            raise NotFound("Metadata not found in this workspace.") from exc
        allowed = set(next(spec for key, spec in package_definitions().items() if key.startswith(f"{group}:")))
        if set(patch) - allowed:
            raise ValidationError({"patch": "Identity, ownership and audit fields are immutable."})
        before = record_spec(row, allowed)
        after = {**before, **patch}
        validate_metadata_fields(after)
        if before == after:
            return row
        validate_fact_compatibility(workspace, row, after)
        for field, value in patch.items():
            setattr(row, field, value)
        row.updated_by_id = actor.actor_id
        row.save()
        validate_effective_schema(workspace)
        if group == "types" and (before.get("rules") or {}).get("presentation") != (row.rules or {}).get(
            "presentation"
        ):
            from plane.radar.active import active_definitions
            from .descriptors import effective_presentation

            definitions = {item.key: item for item in active_definitions(workspace).filter(object_type=row)}
            effective_presentation(row, definitions, strict=True)
        return row

    return run_internal(actor=actor, workspace=workspace, name="UpdateSchemaMetadata", operation=operation)
