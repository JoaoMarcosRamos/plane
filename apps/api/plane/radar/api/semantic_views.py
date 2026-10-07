from plane.radar.locks import observed_atomic
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from plane.radar.commands import (
    set_property_value,
    remove_property_value,
    create_relation,
    remove_relation,
)
from plane.radar.commands.objects import authorize_primitive
from plane.radar.commands.semantic import get_active_object, active_relations
from plane.radar.commands.semantic import initialize_properties_command
from plane.radar.active import active_definitions, active_values, active_relation_types
from plane.radar.workspace_schema import lock_schema
from .views import RadarAPIView
from .serializers import (
    ObjectSerializer,
    ObjectSummarySerializer,
    PropertyDefinitionSerializer,
    PropertyValueSerializer,
    PropertyInputSerializer,
    RelationTypeSerializer,
    RelationSerializer,
    RelationInputSerializer,
)


def property_snapshot(workspace, object_id):
    revision = lock_schema(workspace)
    obj = get_active_object(workspace, object_id, lock=True)
    values = active_values(workspace).filter(object=obj)
    persisted = {item.definition_id: item for item in values}
    rows = []
    for definition in active_definitions(workspace).filter(object_type_id=obj.object_type_id):
        value = persisted.get(definition.pk)
        rows.append(
            {
                "definition": PropertyDefinitionSerializer(definition).data,
                "stored_value": PropertyValueSerializer(value).data if value else None,
                "value": value.value if value else definition.config.get("default"),
                "has_value": value is not None or "default" in definition.config,
            }
        )
    return {"schema_revision": revision, "object": ObjectSerializer(obj).data, "properties": rows}


class ObjectCapacitiesView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug, object_id):
        from plane.radar.capacities import object_capacities

        relation_ids = request.query_params.get("relation_ids")
        if relation_ids is not None:
            raw = relation_ids.split(",") if relation_ids else []
            if len(raw) > 100:
                raise ValidationError({"relation_ids": "Use at most 100 relation IDs."})
            relation_ids = [serializers.UUIDField().run_validation(value) for value in raw]
        return Response(
            object_capacities(
                actor=self.actor("Read object capacities"),
                workspace=self.workspace(),
                object_id=object_id,
                relation_ids=relation_ids,
            )
        )


class PropertyDefinitionsView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug):
        workspace = self.workspace()
        revision = lock_schema(workspace)
        definitions = active_definitions(workspace)
        object_type = request.query_params.get("object_type")
        if object_type:
            type_id = serializers.UUIDField().run_validation(object_type)
            definitions = definitions.filter(object_type_id=type_id)
        return Response(
            PropertyDefinitionSerializer(definitions, many=True).data,
            headers={"X-Radar-Schema-Revision": str(revision)},
        )


class ObjectPropertiesView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        actor = self.actor("Read object properties")
        authorize_primitive(actor, workspace, write=False)
        return Response(property_snapshot(workspace, object_id))

    @observed_atomic
    def post(self, request, slug, object_id):
        if request.data:
            raise ValidationError("Default initialization accepts an empty payload.")
        workspace = self.workspace()
        result = initialize_properties_command(
            actor=self.actor("Initialize object defaults"),
            workspace=workspace,
            object_id=object_id,
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        return Response(result["data"])


class ObjectPropertyView(RadarAPIView):
    @observed_atomic
    def put(self, request, slug, object_id, definition_id):
        serializer = PropertyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace = self.workspace()
        result = set_property_value(
            actor=self.actor("Set object property"),
            workspace=workspace,
            object_id=object_id,
            definition_id=definition_id,
            **serializer.validated_data,
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        return Response(property_snapshot(workspace, object_id))

    @observed_atomic
    def delete(self, request, slug, object_id, definition_id):
        workspace = self.workspace()
        result = remove_property_value(
            actor=self.actor("Remove object property"),
            workspace=workspace,
            object_id=object_id,
            definition_id=definition_id,
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        return Response(property_snapshot(workspace, object_id))


class RelationTypesView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug):
        workspace = self.workspace()
        revision = lock_schema(workspace)
        return Response(
            RelationTypeSerializer(active_relation_types(workspace), many=True).data,
            headers={"X-Radar-Schema-Revision": str(revision)},
        )


class ObjectRelationsView(RadarAPIView):
    @observed_atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        authorize_primitive(self.actor("Read object relations"), workspace, write=False)
        direction = request.query_params.get("direction", "both")
        if direction not in {"both", "outgoing", "incoming"}:
            raise ValidationError({"direction": "Use both, outgoing or incoming."})
        revision = lock_schema(workspace)
        obj = get_active_object(workspace, object_id, lock=True)
        predicate = {"both": Q(source=obj) | Q(target=obj), "outgoing": Q(source=obj), "incoming": Q(target=obj)}
        from .pagination import page
        from plane.radar.active import active_objects
        from plane.radar.authorship import AUTHOR_RELATIONS

        relations, cursor = page(
            active_relations(workspace).filter(predicate[direction]),
            request.query_params,
            scope={
                "workspace": str(workspace.pk),
                "revision": revision,
                "object": str(obj.pk),
                "version": obj.version,
                "direction": direction,
            },
        )
        endpoint_ids = {pk for edge in relations for pk in (edge.source_id, edge.target_id)} - {obj.pk}
        endpoints = (
            active_objects(workspace).filter(pk__in=endpoint_ids).select_related(*AUTHOR_RELATIONS).defer("content")
        )
        return Response(
            {
                "schema_revision": revision,
                "object": ObjectSerializer(obj).data,
                "relations": RelationSerializer(relations, many=True).data,
                "endpoints": ObjectSummarySerializer(endpoints, many=True).data,
                "next_cursor": cursor,
            }
        )


class RelationsView(RadarAPIView):
    @observed_atomic
    def post(self, request, slug):
        serializer = RelationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        workspace = self.workspace()
        result = create_relation(
            actor=self.actor("Create relation"),
            workspace=workspace,
            relation_type_id=data["relation_type"],
            source_id=data["source"],
            target_id=data["target"],
            **self.command_options(),
        )
        pending = self.pending_response(result)
        if pending is not None:
            return pending
        objects = [get_active_object(workspace, pk) for pk in dict.fromkeys([result.source_id, result.target_id])]
        return Response(
            {"relation": RelationSerializer(result).data, "objects": ObjectSerializer(objects, many=True).data},
            status=status.HTTP_201_CREATED,
        )


class RelationDetailView(RadarAPIView):
    @observed_atomic
    def delete(self, request, slug, relation_id):
        workspace = self.workspace()
        # Read IDs through the scoped active query; mutation/authorization stays in command.
        result = get_object_or_404(active_relations(workspace), pk=relation_id)
        mutation = remove_relation(
            actor=self.actor("Remove relation"), workspace=workspace, relation_id=relation_id, **self.command_options()
        )
        pending = self.pending_response(mutation)
        if pending is not None:
            return pending
        objects = [get_active_object(workspace, pk) for pk in dict.fromkeys([result.source_id, result.target_id])]
        return Response({"objects": ObjectSerializer(objects, many=True).data})
