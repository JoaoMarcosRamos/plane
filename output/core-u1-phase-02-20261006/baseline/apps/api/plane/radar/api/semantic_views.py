from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from plane.radar.commands import (
    initialize_semantic_model,
    set_property_value,
    remove_property_value,
    create_relation,
    remove_relation,
)
from plane.radar.commands.objects import authorize_primitive
from plane.radar.commands.semantic import get_active_object, active_relations
from plane.radar.commands.semantic import initialize_properties_command
from plane.radar.models import PropertyDefinition, PropertyValue, RelationType
from .views import RadarAPIView
from .serializers import (
    ObjectSerializer,
    PropertyDefinitionSerializer,
    PropertyValueSerializer,
    PropertyInputSerializer,
    RelationTypeSerializer,
    RelationSerializer,
    RelationInputSerializer,
)


def property_snapshot(workspace, object_id):
    obj = get_active_object(workspace, object_id, lock=True)
    values = PropertyValue.objects.filter(
        workspace=workspace, object=obj, definition__is_active=True, definition__deleted_at__isnull=True
    )
    persisted = {item.definition_id: item for item in values}
    rows = []
    for definition in PropertyDefinition.objects.filter(
        workspace=workspace, object_type_id=obj.object_type_id, is_active=True
    ):
        value = persisted.get(definition.pk)
        rows.append(
            {
                "definition": PropertyDefinitionSerializer(definition).data,
                "stored_value": PropertyValueSerializer(value).data if value else None,
                "value": value.value if value else definition.config.get("default"),
                "has_value": value is not None or "default" in definition.config,
            }
        )
    return {"object": ObjectSerializer(obj).data, "properties": rows}


class PropertyDefinitionsView(RadarAPIView):
    def get(self, request, slug):
        workspace = self.workspace()
        initialize_semantic_model(actor=self.actor("Initialize semantic schema"), workspace=workspace)
        definitions = PropertyDefinition.objects.filter(
            workspace=workspace, is_active=True, object_type__is_active=True, object_type__deleted_at__isnull=True
        )
        object_type = request.query_params.get("object_type")
        if object_type:
            type_id = serializers.UUIDField().run_validation(object_type)
            definitions = definitions.filter(object_type_id=type_id)
        return Response(PropertyDefinitionSerializer(definitions, many=True).data)


class ObjectPropertiesView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        actor = self.actor("Read object properties")
        authorize_primitive(actor, workspace, write=False)
        initialize_semantic_model(actor=actor, workspace=workspace)
        return Response(property_snapshot(workspace, object_id))

    @transaction.atomic
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
    @transaction.atomic
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

    @transaction.atomic
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
    def get(self, request, slug):
        workspace = self.workspace()
        initialize_semantic_model(actor=self.actor("Initialize semantic schema"), workspace=workspace)
        return Response(
            RelationTypeSerializer(RelationType.objects.filter(workspace=workspace, is_active=True), many=True).data
        )


class ObjectRelationsView(RadarAPIView):
    @transaction.atomic
    def get(self, request, slug, object_id):
        workspace = self.workspace()
        authorize_primitive(self.actor("Read object relations"), workspace, write=False)
        direction = request.query_params.get("direction", "both")
        if direction not in {"both", "outgoing", "incoming"}:
            raise ValidationError({"direction": "Use both, outgoing or incoming."})
        obj = get_active_object(workspace, object_id, lock=True)
        predicate = {"both": Q(source=obj) | Q(target=obj), "outgoing": Q(source=obj), "incoming": Q(target=obj)}
        relations = active_relations(workspace).filter(predicate[direction]).order_by("created_at", "id")
        return Response(
            {"object": ObjectSerializer(obj).data, "relations": RelationSerializer(relations, many=True).data}
        )


class RelationsView(RadarAPIView):
    @transaction.atomic
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
    @transaction.atomic
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
