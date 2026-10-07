from collections.abc import Mapping
from django.db.models import QuerySet
from rest_framework import serializers
from plane.radar.authorship import AUTHOR_RELATIONS, object_authorship
from plane.radar.models import Object, ObjectType, PropertyDefinition, PropertyValue, RelationType, Relation
from plane.radar.commands.inputs import StrictSerializer


class ObjectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectType
        fields = [
            "id",
            "workspace",
            "key",
            "name",
            "description",
            "icon",
            "rules",
            "is_system",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class ObjectListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        if isinstance(data, QuerySet):
            data = data.select_related(*AUTHOR_RELATIONS)
        objects = list(data)
        self.context["radar_authorship"] = object_authorship(objects)
        return super().to_representation(objects)


class ObjectSerializer(serializers.ModelSerializer):
    object_type_detail = ObjectTypeSerializer(source="object_type", read_only=True)
    created_actor = serializers.SerializerMethodField()
    updated_actor = serializers.SerializerMethodField()

    def authorship(self, obj):
        summaries = self.context.setdefault("radar_authorship", {})
        if obj.pk not in summaries:
            summaries.update(object_authorship([obj]))
        return summaries[obj.pk]

    def get_created_actor(self, obj):
        return self.authorship(obj)["created_actor"]

    def get_updated_actor(self, obj):
        return self.authorship(obj)["updated_actor"]

    class Meta:
        model = Object
        list_serializer_class = ObjectListSerializer
        fields = [
            "id",
            "workspace",
            "object_type",
            "object_type_detail",
            "title",
            "content",
            "version",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "created_actor",
            "updated_actor",
        ]
        read_only_fields = fields


class ObjectInputSerializer(StrictSerializer):
    object_type = serializers.UUIDField()
    title = serializers.CharField(max_length=255)
    content = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    properties = serializers.DictField(required=False)
    parameters = serializers.DictField(required=False)

    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown or read-only field." for key in unknown})
        return super().to_internal_value(data)


class StrictInputSerializer(StrictSerializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"non_field_errors": ["Expected a JSON object."]})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unknown or read-only field." for key in unknown})
        return super().to_internal_value(data)


class PropertyInputSerializer(StrictInputSerializer):
    value = serializers.JSONField()


class RelationInputSerializer(StrictInputSerializer):
    relation_type = serializers.UUIDField()
    source = serializers.UUIDField()
    target = serializers.UUIDField()


class PropertyDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyDefinition
        fields = [
            "id",
            "workspace",
            "object_type",
            "key",
            "name",
            "value_type",
            "config",
            "is_required",
            "is_active",
            "is_system",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PropertyValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyValue
        fields = [
            "id",
            "workspace",
            "object",
            "definition",
            "value",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RelationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelationType
        fields = [
            "id",
            "workspace",
            "key",
            "forward_label",
            "reverse_label",
            "description",
            "source_types",
            "target_types",
            "allowed_pairs",
            "cardinality",
            "allow_self",
            "is_system",
            "is_active",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RelationSerializer(serializers.ModelSerializer):
    relation_type_detail = RelationTypeSerializer(source="relation_type", read_only=True)

    class Meta:
        model = Relation
        fields = [
            "id",
            "workspace",
            "relation_type",
            "relation_type_detail",
            "source",
            "target",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
