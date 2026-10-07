"""Product runtime facade: authenticated scope, bounded snapshot and HTTP port."""

import hashlib
import json
from uuid import uuid4
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from plane.radar.commands.actor import Actor
from plane.radar.commands.execution import require_human_membership, schema_fingerprint
from plane.radar.commands.queries import effective_values
from plane.radar.models import (
    ActorGrant,
    Object,
    PersonIdentity,
    PropertyValue,
    Relation,
    RuntimeCredential,
    RuntimeObjectIdentity,
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class RuntimeUnavailable(APIException):
    status_code = 503
    default_detail = {"code": "runtime_unavailable"}


class RuntimeConflict(APIException):
    status_code = 409
    default_detail = {"code": "runtime_conflict"}


def binding_for(*, user, workspace, binding_id, include_config=True):
    require_human_membership(
        Actor(
            actor_type="human",
            actor_id=user.pk,
            reason="Use product runtime",
            source="radar.session",
            correlation_id=uuid4(),
        ),
        workspace,
    )
    binding = get_object_or_404(
        RuntimeCredential, pk=binding_id, workspace=workspace, reviewer=user, channel="plane", is_active=True
    )
    if (
        binding.external_author != f"plane:{user.pk}"
        or not Object.objects.filter(pk=binding.person_id, workspace=workspace, object_type__key="person").exists()
        or effective_values(binding.person).get("status") != "active"
    ):
        raise PermissionDenied("Runtime identity unavailable.")
    identity = PersonIdentity.objects.filter(
        workspace=workspace, user=user, person=binding.person, is_active=True
    ).first()
    grant = ActorGrant.objects.filter(
        workspace=workspace, actor_type="agent", actor_id=binding.actor_id, delegator=user, is_active=True
    ).first()
    if identity is None or grant is None or not grant.commands:
        raise PermissionDenied("Runtime authority unavailable.")
    if not RuntimeObjectIdentity.objects.filter(
        workspace=workspace, context=binding.context, object=binding.person
    ).exists():
        raise PermissionDenied("Runtime Person unavailable in this context.")
    authorization = {
        "binding": str(binding.pk),
        "context": binding.context,
        "object_ids": binding.object_ids,
        "manager": binding.is_manager,
        "person": str(binding.person_id),
        "person_version": binding.person.version,
        "grant": str(grant.pk),
        "policy_version": grant.policy_version,
        "schema_hash": schema_fingerprint(workspace),
        "commands": grant.commands,
        "object_types": grant.object_types,
        "fields": grant.fields,
        "can_approve": identity.can_approve,
    }
    if include_config:
        from plane.radar.agent_config import effective_configuration

        snapshot, grant = effective_configuration(binding, grant)
        binding.agent_config_snapshot = snapshot
        authorization["agent_config"] = snapshot
    scope = {
        "channel": "plane.session",
        "workspace_id": str(workspace.pk),
        "user_id": str(user.pk),
        "agent_id": str(binding.actor_id),
        "binding_id": str(binding.pk),
        "authorization_hash": fingerprint(authorization),
    }
    objects = Object.objects.filter(
        workspace=workspace,
        object_type__is_active=True,
        id__in=RuntimeObjectIdentity.objects.filter(workspace=workspace, context=binding.context).values("object_id"),
    )
    if "*" not in grant.object_types:
        objects = objects.filter(object_type__key__in=grant.object_types)
    if binding.object_ids is not None:
        objects = objects.filter(
            id__in=RuntimeObjectIdentity.objects.filter(
                workspace=workspace, context=binding.context, external_id__in=binding.object_ids
            ).values("object_id")
        )
    if include_config and snapshot["permissions"]["object_ids"] is not None:
        objects = objects.filter(pk__in=snapshot["permissions"]["object_ids"])
    return binding, grant, scope, objects


def load_context(objects, grant, root_ids):
    roots = set(root_ids)
    if not roots or len(roots) > 10 or objects.filter(pk__in=roots).count() != len(roots):
        raise NotFound("Context roots unavailable.")
    visible = objects.values("pk")
    candidates = list(
        Relation.objects.filter(source_id__in=visible, target_id__in=visible)
        .filter(Q(source_id__in=roots) | Q(target_id__in=roots))
        .select_related("relation_type")
        .order_by("pk")[:41]
    )
    selected = set(roots)
    truncated = len(candidates) > 40
    for edge in candidates[:40]:
        for pk in (edge.source_id, edge.target_id):
            if len(selected) < 21:
                selected.add(pk)
            elif pk not in selected:
                truncated = True
    result = []
    allowed = set(grant.fields)
    for obj in objects.filter(pk__in=selected).select_related("object_type").order_by("pk"):
        properties = {}
        values = PropertyValue.objects.filter(object=obj)
        if "*" not in allowed:
            values = values.filter(definition__key__in=allowed)
        visible_values = list(values.select_related("definition").order_by("pk")[:21])
        truncated |= len(visible_values) > 20
        for prop in visible_values[:20]:
            # A field with unbounded JSON/text is omitted instead of leaking an oversized value.
            if len(json.dumps(prop.value, ensure_ascii=True)) <= 500:
                properties[prop.definition.key] = prop.value
            else:
                truncated = True
        title = obj.title if "*" in allowed or "title" in allowed else ""
        content = obj.content if "*" in allowed or "content" in allowed else ""
        truncated |= len(title) > 200 or len(content) > 1500
        result.append(
            {
                "id": str(obj.pk),
                "version": obj.version,
                "type": obj.object_type.key,
                "title": title[:200],
                "content": content[:1500],
                "properties": properties,
            }
        )
    ids = {o["id"] for o in result}
    relations = [
        {"id": str(e.pk), "source": str(e.source_id), "target": str(e.target_id), "type": e.relation_type.key}
        for e in candidates[:40]
        if str(e.source_id) in ids and str(e.target_id) in ids
    ]
    snapshot = {"objects": result, "relations": relations, "truncated": truncated}
    if len(json.dumps(snapshot, ensure_ascii=True)) > 30000:
        snapshot["truncated"] = True
        for item in result:
            item["properties"] = {}
            item["content"] = item["content"][:200]
    if len(json.dumps(snapshot, ensure_ascii=True)) > 30000:
        raise ValidationError("Context exceeds the serialized character budget.")
    return snapshot


def verify_snapshot(objects, snapshot):
    expected = {item["id"]: item["version"] for item in snapshot["objects"]}
    current = {str(obj.pk): obj.version for obj in objects.filter(pk__in=expected)}
    if current != expected:
        raise RuntimeConflict({"code": "context_stale"})


def runtime_request(path, payload, *, stream=False):
    base = settings.RADAR_AGENT_RUNTIME_URL
    token = settings.RADAR_AGENT_RUNTIME_TOKEN
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or len(token) < 32
        or not token.isascii()
    ):
        raise RuntimeUnavailable()
    try:
        response = requests.post(
            base.rstrip("/") + "/" + path,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(5, 20),
            allow_redirects=False,
            stream=True,
        )
        with response:
            if response.status_code == 404:
                raise NotFound("Run unavailable.")
            if response.status_code == 409:
                raise RuntimeConflict()
            if not 200 <= response.status_code < 300:
                raise RuntimeUnavailable()
            content = bytearray()
            for chunk in response.iter_content(8192):
                content.extend(chunk)
                if len(content) > 100000:
                    raise RuntimeUnavailable()
            if stream:
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise RuntimeUnavailable()
                return bytes(content)
            data = json.loads(content)
            if not isinstance(data, dict) or data.get("contract_version") != "1.0":
                raise RuntimeUnavailable()
            return data
    except (requests.RequestException, ValueError):
        raise RuntimeUnavailable() from None
