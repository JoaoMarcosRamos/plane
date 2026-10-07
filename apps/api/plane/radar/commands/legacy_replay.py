"""Frozen pre-plan v1 authority declaration, used only for confirmed historical replay.

Never use this declaration for a new intention, preview or review. New ledger
entries carry the complete authority plan captured by effects.py.
"""

from rest_framework.exceptions import PermissionDenied
from plane.radar.models import ActorGrant, Object, PropertyDefinition
from . import primitives_objects as objects, primitives_semantic as semantic
from .handlers import human_only_policy, references

# Frozen v1 CreateObject specialization: refs and composed commands were embedded in properties.
LEGACY_SPECIALIZED = {"action": "CreateAction", "risk": "RegisterRisk", "decision": "CreateDecision"}


def legacy_creation(workspace, data):
    specialized = LEGACY_SPECIALIZED.get(objects.get_object_type(workspace, data["object_type_id"]).key)
    if specialized is None:
        return None, {}
    payload = {key: value for key, value in data["properties"].items() if key != "status"}
    from .inputs import INPUTS

    serializer = INPUTS[specialized](data={"title": data["title"], **payload})
    serializer.is_valid(raise_exception=True)
    return specialized, serializer.validated_data


def legacy_references(workspace, name, data):
    if name != "CreateObject" or data.get("parameters"):
        return references(workspace, name, data)
    specialized, payload = legacy_creation(workspace, data)
    return references(workspace, specialized, payload) if specialized else set()


def legacy_check_grant(workspace, grant: ActorGrant | None, name, data, refs):
    if human_only_policy(workspace, name, data) and grant is not None:
        raise PermissionDenied("Decision approval and decision taking are human-only.")
    if grant is None:
        return
    if name in {"CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement"}:
        from .operations import check_context

        check_context(workspace, data, refs)
        created = {
            "CaptureIssue": {"case", "management_item", "document"},
            "RecordMeasurement": {"document"} if "evidence_id" not in data else set(),
        }.get(name, set())
        types = (
            set(Object.objects.filter(workspace=workspace, pk__in=refs).values_list("object_type__key", flat=True))
            | created
        )
        if "*" not in grant.object_types and not types.issubset(grant.object_types):
            raise PermissionDenied("Grant does not cover every operation Object type.")
        if "*" not in grant.fields or "LinkObjects" not in grant.commands:
            raise PermissionDenied("Operational commands require composed relation and field authority.")
        return
    types = set(Object.objects.filter(workspace=workspace, pk__in=refs).values_list("object_type__key", flat=True))
    created_type = {
        "CreateAction": "action",
        "RegisterRisk": "risk",
        "CreateDecision": "decision",
        "AddEvidence": "document",
    }.get(name)
    extra_commands = set()
    if name == "CreateObject":
        types.add(objects.get_object_type(workspace, data["object_type_id"]).key)
        specialized, _ = legacy_creation(workspace, data)
        if specialized:
            extra_commands.add(specialized)
    elif created_type:
        types.add(created_type)
    if (
        name in {"CompleteAction", "AddEvidence"}
        or refs
        and name in {"CreateObject", "CreateAction", "RegisterRisk", "CreateDecision"}
    ):
        extra_commands.add("LinkObjects")
    if not extra_commands.issubset(set(grant.commands)):
        raise PermissionDenied("Grant does not cover every composed command effect.")
    if "*" not in grant.object_types and not types.issubset(set(grant.object_types)):
        raise PermissionDenied("Grant does not cover every Object type.")
    if name == "UpdateObject":
        fields = set(data["changes"]) | set(data["set_properties"]) | set(data["remove_properties"])
        obj = semantic.get_active_object(workspace, data["object_id"])
        fields.update(semantic.property_effect_fields(obj, data["set_properties"], data["remove_properties"]))
        if "*" not in grant.fields and not fields.issubset(set(grant.fields)):
            raise PermissionDenied("Grant does not cover every modified field.")
    elif name.startswith("Create") or name in {"RegisterRisk", "CompleteAction", "AddEvidence"}:
        if "*" not in grant.fields:
            # Creation includes defaults and derived values, not just the explicit payload.
            keys = {
                definition.key
                for definition in PropertyDefinition.objects.filter(
                    workspace=workspace, object_type__key__in=types, is_active=True
                )
            }
            keys.update({"title", "content"})
            if not keys.issubset(set(grant.fields)):
                raise PermissionDenied("Grant does not cover initial/default/derived fields.")
