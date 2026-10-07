"""Explicit provisioning; operational GET is always read-only."""

import hashlib
import json
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from plane.db.models import WorkspaceMember
from plane.radar.active import active_types, active_definitions, active_relation_types
from plane.radar.commands.schema import install_schema, preview_upgrade, upgrade_schema, update_metadata
from plane.radar.commands.inputs import StrictSerializer
from plane.radar.commands.capabilities import command_contracts, guard_contracts
from plane.radar.commands.access import require_human_membership, role_can_write
from plane.radar.models import WorkspaceSchemaState
from plane.radar.workspace_schema import lock_schema
from .views import RadarAPIView
from .serializers import ObjectTypeSerializer, PropertyDefinitionSerializer, RelationTypeSerializer


class SchemaOperationInput(StrictSerializer):
    operation = serializers.ChoiceField(choices=["install", "preview_upgrade", "upgrade", "edit"])
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    reviewed_hash = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)
    group = serializers.ChoiceField(choices=["types", "properties", "relations"], required=False)
    definition_id = serializers.UUIDField(required=False)
    patch = serializers.JSONField(required=False)


def schema_catalog(workspace, actor):
    require_human_membership(actor, workspace, write=False)
    revision = lock_schema(workspace)
    state = WorkspaceSchemaState.objects.filter(workspace=workspace).first()
    membership = WorkspaceMember.objects.get(workspace=workspace, member_id=actor.actor_id, is_active=True)
    authority = {"membership": str(membership.pk), "role": membership.role, "active": membership.is_active}
    return {
        "status": "uninitialized" if state is None else "legacy" if state.origin == "legacy" else "installed",
        "schema_revision": revision,
        "package_version": state.package_version or None if state else None,
        "authority_revision": hashlib.sha256(json.dumps(authority, sort_keys=True).encode()).hexdigest(),
        "can_write": role_can_write(membership.role),
        "object_types": ObjectTypeSerializer(active_types(workspace), many=True).data,
        "property_definitions": PropertyDefinitionSerializer(active_definitions(workspace), many=True).data,
        "relation_types": RelationTypeSerializer(active_relation_types(workspace), many=True).data,
        "capabilities": command_contracts(),
        "transition_guards": guard_contracts(),
    }


class WorkspaceSchemaView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug):
        return Response(schema_catalog(self.workspace(), self.actor("Read workspace schema")))

    @transaction.atomic
    def post(self, request, slug):
        parsed = SchemaOperationInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        data = parsed.validated_data
        operation = data.pop("operation")
        workspace, actor = self.workspace(), self.actor("Manage workspace schema")
        if operation != "install" and "expected_revision" not in data:
            raise serializers.ValidationError({"expected_revision": "Review the current schema revision first."})
        required = {
            "install": set(),
            "preview_upgrade": {"expected_revision"},
            "upgrade": {"expected_revision", "reviewed_hash"},
            "edit": {"expected_revision", "group", "definition_id", "patch"},
        }[operation]
        if set(data) != required:
            raise serializers.ValidationError({"input": f"Expected only: {sorted(required)}."})
        if operation == "preview_upgrade":
            return Response(preview_upgrade(actor=actor, workspace=workspace, **data))
        if operation == "install":
            install_schema(actor=actor, workspace=workspace)
        elif operation == "upgrade":
            upgrade_schema(actor=actor, workspace=workspace, **data)
        else:
            update_metadata(actor=actor, workspace=workspace, **data)
        return Response(schema_catalog(workspace, actor))
