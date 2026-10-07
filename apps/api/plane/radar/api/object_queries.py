"""Server-side candidate policy using the same facts as the relation writer."""

from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from plane.radar.active import active_objects, active_relation_types
from plane.radar.models import Relation
from plane.radar.commands.objects import authorize_primitive
from plane.radar.commands.access import require_human_membership
from plane.radar.commands.capabilities import get_capability


def object_query(view, workspace, revision):
    params = view.request.query_params
    authorize_primitive(view.actor("Search objects"), workspace, write=False)
    objects = active_objects(workspace)
    scope = {"workspace": str(workspace.pk), "revision": revision}
    for key in ("q", "object_type", "type_keys", "exclude", "capability", "relation_type", "object_id", "direction"):
        scope[key] = params.get(key, "")
    query = scope["q"].strip()
    if len(query) > 255:
        raise ValidationError({"q": "Use at most 255 characters."})
    if query:
        objects = objects.filter(title__icontains=query)
    if scope["object_type"]:
        objects = objects.filter(object_type_id=serializers.UUIDField().run_validation(scope["object_type"]))
    if scope["type_keys"] and "*" not in scope["type_keys"].split(","):
        objects = objects.filter(object_type__key__in=scope["type_keys"].split(","))
    if scope["exclude"]:
        objects = objects.exclude(pk=serializers.UUIDField().run_validation(scope["exclude"]))
    if scope["capability"]:
        capability = get_capability(scope["capability"])
        if capability.creation is None:
            raise ValidationError({"capability": "Use a registered creation capability."})
        require_human_membership(view.actor("Search creation candidates"), workspace)
        predicate = Q(object_type__rules__creation__capability=capability.name)
        from plane.radar.commands.descriptors import DEFAULT_CREATION

        if capability.name == DEFAULT_CREATION:
            predicate |= Q(object_type__rules__creation__isnull=True)
        objects = objects.filter(predicate)
    if scope["relation_type"]:
        require_human_membership(view.actor("Search relation candidates"), workspace)
        kind = get_object_or_404(
            active_relation_types(workspace), pk=serializers.UUIDField().run_validation(scope["relation_type"])
        )
        anchor = get_object_or_404(
            active_objects(workspace).select_related("object_type"),
            pk=serializers.UUIDField().run_validation(scope["object_id"]),
        )
        direction = scope["direction"] or "outgoing"
        if direction not in {"outgoing", "incoming"}:
            raise ValidationError({"direction": "Use outgoing or incoming."})
        scope["object_version"] = anchor.version
        outgoing = direction == "outgoing"
        fixed_types = kind.source_types if outgoing else kind.target_types
        candidate_types = kind.target_types if outgoing else kind.source_types
        if "*" not in fixed_types and anchor.object_type.key not in fixed_types:
            return objects.none(), scope
        if "*" not in candidate_types:
            objects = objects.filter(object_type__key__in=candidate_types)
        if kind.allowed_pairs:
            keys = [
                pair[1 if outgoing else 0]
                for pair in kind.allowed_pairs
                if pair[0 if outgoing else 1] == anchor.object_type.key
            ]
            objects = objects.filter(object_type__key__in=keys)
        if not kind.allow_self:
            objects = objects.exclude(pk=anchor.pk)
        edges = Relation.objects.filter(workspace=workspace, relation_type=kind)
        existing = (
            edges.filter(source=anchor, target_id=OuterRef("pk"))
            if outgoing
            else edges.filter(source_id=OuterRef("pk"), target=anchor)
        )
        objects = objects.alias(already_linked=Exists(existing)).filter(already_linked=False)
        if kind.cardinality in {"0..1", "1..1"}:
            if outgoing and edges.filter(source=anchor).exists():
                objects = objects.none()
            elif not outgoing:
                objects = objects.alias(occupied=Exists(edges.filter(source_id=OuterRef("pk")))).filter(occupied=False)
    elif scope["object_id"] or scope["direction"]:
        raise ValidationError({"relation_type": "Required with object_id or direction."})
    return objects, scope
