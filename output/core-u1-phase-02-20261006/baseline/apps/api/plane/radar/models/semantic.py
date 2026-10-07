from django.db import models
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from .core import RadarBaseModel, Object, ObjectType

PROPERTY_TYPES = (
    "string",
    "string_list",
    "number",
    "integer",
    "boolean",
    "enum",
    "date",
    "datetime",
    "email",
    "uri",
    "user",
)


class PropertyDefinition(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_property_definitions")
    object_type = models.ForeignKey(ObjectType, on_delete=models.PROTECT, related_name="property_definitions")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=100)
    value_type = models.CharField(max_length=32, choices=[(key, key) for key in PROPERTY_TYPES])
    config = models.JSONField(default=dict)
    is_required = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_property_definitions"
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "key"], condition=Q(deleted_at__isnull=True), name="radar_prop_type_key_live"
            ),
            models.CheckConstraint(condition=Q(value_type__in=PROPERTY_TYPES), name="radar_prop_valid_type"),
        ]


class PropertyValue(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_property_values")
    object = models.ForeignKey(Object, on_delete=models.PROTECT, related_name="property_values")
    definition = models.ForeignKey(PropertyDefinition, on_delete=models.PROTECT, related_name="values")
    value = models.JSONField()

    def validate_domain_links(self):
        if self.object.object_type_id != self.definition.object_type_id:
            raise ValidationError({"definition": "Definition belongs to another Object type."})

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_property_values"
        constraints = [
            models.UniqueConstraint(
                fields=["object", "definition"],
                condition=Q(deleted_at__isnull=True),
                name="radar_value_object_def_live",
            )
        ]
        indexes = [models.Index(fields=["workspace", "definition"], name="radar_value_ws_def_idx")]


class RelationType(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_relation_types")
    key = models.SlugField(max_length=64)
    forward_label = models.CharField(max_length=100)
    reverse_label = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    source_types = models.JSONField(default=list)
    target_types = models.JSONField(default=list)
    allowed_pairs = models.JSONField(default=list)
    cardinality = models.CharField(
        max_length=8, choices=[("0..1", "0..1"), ("0..n", "0..n"), ("1..1", "1..1")], default="0..n"
    )
    allow_self = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_relation_types"
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"], condition=Q(deleted_at__isnull=True), name="radar_reltype_ws_key_live"
            ),
            models.CheckConstraint(
                condition=Q(cardinality__in=["0..1", "0..n", "1..1"]), name="radar_reltype_cardinality"
            ),
        ]


class Relation(RadarBaseModel):
    workspace = models.ForeignKey("db.Workspace", on_delete=models.PROTECT, related_name="radar_relations")
    relation_type = models.ForeignKey(RelationType, on_delete=models.PROTECT, related_name="relations")
    source = models.ForeignKey(Object, on_delete=models.PROTECT, related_name="outgoing_relations")
    target = models.ForeignKey(Object, on_delete=models.PROTECT, related_name="incoming_relations")

    class Meta(RadarBaseModel.Meta):
        db_table = "radar_relations"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "relation_type", "source", "target"],
                condition=Q(deleted_at__isnull=True),
                name="radar_relation_live_unique",
            )
        ]
        indexes = [
            models.Index(fields=["workspace", "source"], name="radar_relation_ws_source_idx"),
            models.Index(fields=["workspace", "target"], name="radar_relation_ws_target_idx"),
        ]
