"""Structured configuration; grants remain the ceiling for every execution."""

from copy import copy

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from plane.radar.commands.control import require_workspace_admin
from plane.radar.commands.execution import CommandConflict, run_internal
from plane.radar.commands.inputs import StrictSerializer
from plane.radar.models import AgentConfiguration


class IdentityInput(StrictSerializer):
    name = serializers.CharField(max_length=100)
    soul = serializers.CharField(max_length=2000, allow_blank=True)


class RoleInput(StrictSerializer):
    name = serializers.CharField(max_length=100)
    purpose = serializers.CharField(max_length=2000, allow_blank=True)


class PoliciesInput(StrictSerializer):
    guidelines = serializers.ListField(child=serializers.CharField(max_length=500), max_length=20)
    require_human_approval = serializers.BooleanField()
    read_only = serializers.BooleanField()

    def validate(self, data):
        if not data["require_human_approval"] or not data["read_only"]:
            raise serializers.ValidationError("This runtime requires human approval and read-only execution.")
        return data


class PermissionsInput(StrictSerializer):
    commands = serializers.ListField(child=serializers.CharField(max_length=64), max_length=50)
    object_types = serializers.ListField(child=serializers.CharField(max_length=64), max_length=100)
    fields = serializers.ListField(child=serializers.CharField(max_length=64), max_length=100)
    object_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100, allow_null=True)

    def validate(self, data):
        for key, values in data.items():
            if values is not None and len(values) != len(set(values)):
                raise serializers.ValidationError({key: "Duplicate permissions are not allowed."})
        data["object_ids"] = [str(pk) for pk in data["object_ids"]] if data["object_ids"] is not None else None
        return data


class ConfigurationInput(StrictSerializer):
    expected_version = serializers.IntegerField(min_value=0)
    identity = IdentityInput()
    role = RoleInput()
    policies = PoliciesInput()
    permissions = PermissionsInput()


def configuration_snapshot(binding, grant):
    config = AgentConfiguration.objects.filter(workspace=binding.workspace, binding=binding).first()
    if config is None:
        # Legacy bindings have an explicit, immutable default; GET never persists it.
        return {
            "schema_version": "1.0",
            "version": 0,
            "identity": {"name": "RADAR Copilot", "soul": "Support thoughtful, evidence-based management."},
            "role": {"name": "Management copilot", "purpose": "Analyze the authorized Objects and Relations."},
            "policies": {"guidelines": [], "require_human_approval": True, "read_only": True},
            "permissions": {
                "commands": list(grant.commands),
                "object_types": list(grant.object_types),
                "fields": list(grant.fields),
                "object_ids": None,
            },
        }
    return {
        "schema_version": "1.0",
        "version": config.version,
        **{key: getattr(config, key) for key in ("identity", "role", "policies", "permissions")},
    }


def intersect_scope(requested, ceiling):
    if "*" in requested:
        return sorted(set(ceiling))
    if "*" in ceiling:
        return sorted(set(requested))
    return sorted(set(requested) & set(ceiling))


def effective_configuration(binding, grant):
    snapshot = configuration_snapshot(binding, grant)
    effective = copy(grant)
    permissions = dict(snapshot["permissions"])
    for key in ("commands", "object_types", "fields"):
        permissions[key] = intersect_scope(permissions[key], getattr(grant, key))
        setattr(effective, key, permissions[key])
    return {**snapshot, "permissions": permissions}, effective


def configure_agent(*, actor, workspace, binding_id, data):
    parsed = ConfigurationInput(data=data)
    parsed.is_valid(raise_exception=True)
    data = parsed.validated_data

    def operation():
        from plane.radar.agent_runtime import binding_for
        from plane.db.models import User

        require_workspace_admin(actor, workspace)
        binding, grant, _, objects = binding_for(
            user=User.objects.get(pk=actor.actor_id), workspace=workspace, binding_id=binding_id, include_config=False
        )
        permissions = data["permissions"]
        for key in ("commands", "object_types", "fields"):
            requested, ceiling = set(permissions[key]), set(getattr(grant, key))
            if (key == "commands" or "*" not in ceiling) and not requested <= ceiling:
                raise PermissionDenied({key: "Configuration cannot expand the administrative grant."})
        ids = permissions["object_ids"]
        if ids is not None and objects.filter(pk__in=ids).count() != len(ids):
            raise PermissionDenied("Configured Objects must belong to the authorized binding context.")
        config = AgentConfiguration.objects.filter(workspace=workspace, binding=binding).first()
        if data["expected_version"] != (config.version if config else 0):
            raise CommandConflict({"code": "agent_config_stale"})
        values = {key: data[key] for key in ("identity", "role", "policies", "permissions")}
        if config is None:
            config = AgentConfiguration.objects.create(
                workspace=workspace,
                binding=binding,
                created_by_id=actor.actor_id,
                updated_by_id=actor.actor_id,
                **values,
            )
        else:
            for key, value in values.items():
                setattr(config, key, value)
            config.version += 1
            config.updated_by_id = actor.actor_id
            config.save()
        return config

    return run_internal(actor=actor, workspace=workspace, name="AgentConfigurationConfigured", operation=operation)
