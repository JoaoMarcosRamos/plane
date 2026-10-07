from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from plane.db.models import WorkspaceMember
from plane.radar.agent_config import (
    ConfigurationInput,
    configuration_snapshot,
    configure_agent,
    effective_configuration,
)
from plane.radar.agent_runtime import binding_for
from plane.radar.models import RuntimeCredential
from .views import RadarAPIView


def configuration_data(user, workspace, binding_id):
    binding, grant, _, objects = binding_for(
        user=user, workspace=workspace, binding_id=binding_id, include_config=False
    )
    snapshot = configuration_snapshot(binding, grant)
    effective, _ = effective_configuration(binding, grant)
    options = list(objects.select_related("object_type").order_by("pk")[:101])
    return {
        "binding_id": str(binding.pk),
        "agent_id": str(binding.actor_id),
        "context": binding.context,
        "can_edit": workspace.owner_id == user.pk
        or WorkspaceMember.objects.filter(workspace=workspace, member=user, role=20, is_active=True).exists(),
        "configuration": snapshot,
        "effective_permissions": effective["permissions"],
        "grant_ceiling": {key: getattr(grant, key) for key in ("commands", "object_types", "fields")},
        "object_options": [
            {
                "id": str(obj.pk),
                "title": obj.title if "*" in grant.fields or "title" in grant.fields else "",
                "type": obj.object_type.key,
            }
            for obj in options[:100]
        ],
        "objects_truncated": len(options) > 100,
    }


class AgentConfigurationsView(RadarAPIView):
    def get(self, request, slug):
        workspace = self.workspace()
        bindings = RuntimeCredential.objects.filter(
            workspace=workspace, reviewer=request.user, channel="plane", is_active=True
        ).order_by("pk")
        results = []
        for binding in bindings:
            try:
                results.append(configuration_data(request.user, workspace, binding.pk))
            except (NotFound, PermissionDenied):
                # A revoked or invalid binding never exposes identity/configuration.
                continue
        return Response(results)


class AgentConfigurationDetailView(RadarAPIView):
    def get(self, request, slug, binding_id):
        return Response(configuration_data(request.user, self.workspace(), binding_id))

    def put(self, request, slug, binding_id):
        parsed = ConfigurationInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        workspace = self.workspace()
        configure_agent(
            actor=self.actor("Configure RADAR agent"),
            workspace=workspace,
            binding_id=binding_id,
            data=parsed.validated_data,
        )
        return Response(configuration_data(request.user, workspace, binding_id))
