"""Versioned, authenticated CoS port. Every write invokes the common dispatcher."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.radar.commands.actor import Actor
from plane.radar.commands.control import review_command
from plane.radar.commands.execution import (
    require_human_membership,
    authorize,
    execute_command,
    validate_actor,
    command_envelope,
)
from plane.radar.commands.handlers import references, check_grant
from plane.radar.commands.queries import effective_values
from plane.radar.commands.inputs import CommandInput, INPUTS, StrictSerializer
from plane.radar.collaboration import COLLABORATION_COMMANDS
from plane.radar.commands.operations import OPERATIONS
from plane.radar.models import (
    ActorGrant,
    CommandApproval,
    CommandExecution,
    Object,
    OperationalRecord,
    PersonIdentity,
    Relation,
    RuntimeCredential,
    RuntimeObjectIdentity,
)
from plane.radar.mutation import json_value
from plane.radar.ontology.schema import load_schema


DEFINITIONS = {
    "capture_issue": {
        "target_types": [],
        "parameters": {
            k: {"type": "string", "required": k in {"title", "case_title", "evidence_title", "source"}}
            for k in ("title", "case_title", "evidence_title", "source", "priority", "owner_id")
        },
    },
    "delegate": {
        "target_types": ["action"],
        "parameters": {
            "executor_id": {"type": "string"},
            "executor_ids": {"type": "string_list"},
            "due_at": {"type": "datetime", "required": True},
            "next_review_at": {"type": "datetime"},
        },
    },
    "review": {
        "target_types": [k for k in load_schema()["object_types"] if k != "person"],
        "parameters": {
            "assessment": {"type": "string", "required": True},
            "evidence_id": {"type": "string", "required": True},
            "next_review_at": {"type": "datetime"},
            "disposition": {"type": "string"},
        },
    },
    "record_measurement": {
        "target_types": ["indicator"],
        "parameters": {
            "value": {"type": "number", "required": True},
            "measured_at": {"type": "datetime", "required": True},
            **{k: {"type": "string"} for k in ("evidence_id", "evidence_title", "evidence_source", "evidence_text")},
        },
    },
}


class RuntimeAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if len(parts) != 2 or parts[0].lower() != b"bearer":
            raise AuthenticationFailed("Runtime credential required.")
        credential = (
            RuntimeCredential.objects.select_related("workspace", "reviewer", "person")
            .filter(
                token_hash=hashlib.sha256(parts[1]).hexdigest(),
                channel="telegram",
                is_active=True,
                workspace__slug=request.parser_context["kwargs"]["slug"],
            )
            .first()
        )
        if credential is None:
            raise AuthenticationFailed("Runtime credential unavailable.")
        actor = Actor(
            actor_type="human",
            actor_id=credential.reviewer_id,
            reason="Authenticate runtime",
            source="radar.cos.host",
            correlation_id=credential.pk,
        )
        require_human_membership(actor, credential.workspace)
        if (
            not PersonIdentity.objects.filter(
                workspace=credential.workspace,
                user_id=credential.reviewer_id,
                person_id=credential.person_id,
                is_active=True,
            ).exists()
            or effective_values(credential.person).get("status") != "active"
        ):
            raise AuthenticationFailed("Runtime identity unavailable.")
        grant = ActorGrant.objects.filter(
            workspace=credential.workspace,
            actor_type="agent",
            actor_id=credential.actor_id,
            delegator_id=credential.reviewer_id,
            is_active=True,
        ).first()
        if grant is None:
            raise AuthenticationFailed("Runtime grant unavailable.")
        return credential.reviewer, credential

    def authenticate_header(self, request):
        return "Bearer"


class ProvenanceInput(StrictSerializer):
    run_id = serializers.UUIDField()
    correlation_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=1200)
    source = serializers.DictField()

    def validate_source(self, data):
        required = {"update_id", "chat_id", "message_id", "author", "timestamp", "text_sha256"}
        if (
            set(data) != required
            or type(data["update_id"]) is not int
            or type(data["chat_id"]) is not int
            or type(data["message_id"]) is not int
        ):
            raise serializers.ValidationError("Use authenticated message metadata.")
        StrictSerializer._check_type(serializers.DateTimeField(), data["timestamp"])
        serializers.DateTimeField().run_validation(data["timestamp"])
        serializers.RegexField(r"^[a-f0-9]{64}$").run_validation(data["text_sha256"])
        return data


class PrepareInput(StrictSerializer):
    operation = serializers.ChoiceField(choices=list(OPERATIONS))
    target_id = serializers.CharField(required=False, allow_null=True)
    parameters = serializers.DictField()
    idempotency_key = serializers.CharField(max_length=96)
    provenance = ProvenanceInput()


class ResolveInput(StrictSerializer):
    command_id = serializers.UUIDField()
    intent_hash = serializers.RegexField(r"^[a-f0-9]{64}$")
    idempotency_key = serializers.CharField(max_length=128)
    approve = serializers.BooleanField()
    rationale = serializers.CharField(max_length=1200)
    source = serializers.DictField()


class CommandPrepareInput(StrictSerializer):
    envelope = CommandInput()
    provenance = ProvenanceInput()


class QueryInput(StrictSerializer):
    method = serializers.ChoiceField(
        choices=["read_entity", "search_entities", "get_entity_context", "list_action_types", "validate_vault"]
    )
    parameters = serializers.DictField(default=dict)


class RuntimeView(APIView):
    authentication_classes = [RuntimeAuthentication]
    permission_classes = [IsAuthenticated]

    def binding_hash(self):
        c = self.request.auth
        return hashlib.sha256(
            json.dumps(
                {
                    "person_id": str(c.person_id),
                    "reviewer_id": str(c.reviewer_id),
                    "context": c.context,
                    "is_manager": c.is_manager,
                    "object_ids": c.object_ids,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            code = (
                "not_authorized"
                if isinstance(exc, (PermissionDenied, AuthenticationFailed))
                else "not_found"
                if isinstance(exc, NotFound)
                else "invalid_parameters"
            )
            if isinstance(exc.detail, dict) and "code" in exc.detail:
                code = str(exc.detail["code"])
            allowed = {
                "not_authorized",
                "not_found",
                "invalid_parameters",
                "revision_conflict",
                "idempotency_conflict",
                "approval_stale",
                "measurement_in_future",
                "measurement_out_of_order",
                "evidence_source_conflict",
                "evidence_required",
            }
            code = code if code in allowed else "invalid_parameters"
            return Response(
                {
                    "status": "conflict" if exc.status_code == 409 else "rejected",
                    "code": code,
                    "created_ids": [],
                    "target_id": None,
                    "revision": None,
                    "operation_id": None,
                },
                status=exc.status_code,
            )
        return super().handle_exception(exc)

    def identities(self):
        c = self.request.auth
        grant = ActorGrant.objects.get(workspace=c.workspace, actor_type="agent", actor_id=c.actor_id, is_active=True)
        queryset = RuntimeObjectIdentity.objects.filter(
            workspace=c.workspace,
            context=c.context,
            object__object_type__is_active=True,
            object__object_type__deleted_at__isnull=True,
            object__deleted_at__isnull=True,
        ).select_related("object__object_type")
        if "*" not in grant.object_types:
            queryset = queryset.filter(object__object_type__key__in=grant.object_types)
        if c.object_ids is not None:
            queryset = queryset.filter(external_id__in=c.object_ids)
        return queryset

    def resolve(self, external_id):
        return get_object_or_404(self.identities(), external_id=external_id).object_id

    def actor(self, provenance):
        c = self.request.auth
        if provenance["source"]["author"] != c.external_author:
            raise PermissionDenied("Message author does not match the credential.")
        actor = Actor(
            actor_type="agent",
            actor_id=c.actor_id,
            reason=provenance["reason"],
            source="radar.cos.telegram",
            correlation_id=provenance["correlation_id"],
            run_id=provenance["run_id"],
            timestamp=datetime.fromisoformat(provenance["source"]["timestamp"].replace("Z", "+00:00")),
            on_behalf_of=c.reviewer_id,
            metadata={
                "credential_id": str(c.pk),
                "binding_hash": self.binding_hash(),
                "context": c.context,
                "message": provenance["source"],
            },
        )
        validate_actor(actor)
        return actor

    def scope(self, name, data, actor):
        c = self.request.auth
        if actor.metadata.get("binding_hash") != self.binding_hash():
            from plane.radar.commands.execution import CommandConflict

            raise CommandConflict({"code": "approval_stale"})
        grant = authorize(actor, c.workspace, name)
        refs = references(c.workspace, name, data)
        if not refs.issubset(set(self.identities().values_list("object_id", flat=True))):
            raise PermissionDenied("Reference is unavailable in this credential scope.")
        if c.object_ids is not None and (
            name.startswith("Create")
            or name in {"CaptureIssue", "AddEvidence", "RegisterRisk"}
            or name == "RecordMeasurement"
            and "evidence_id" not in data
        ):
            raise PermissionDenied("Creation requires context-wide authority.")
        check_grant(c.workspace, grant, name, data, refs)
        return refs


class RuntimeCommandPrepareView(RuntimeView):
    @transaction.atomic
    def post(self, request, slug):
        parsed = CommandPrepareInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        p = parsed.validated_data
        envelope = p["envelope"]
        if "approval_id" in envelope or "proposal_id" in envelope or envelope["command_name"] not in INPUTS:
            raise ValidationError("Preparation cannot include approval/takeover authority.")
        actor = self.actor(p["provenance"])
        serializer = INPUTS[envelope["command_name"]](data=envelope["input"])
        serializer.is_valid(raise_exception=True)
        refs = self.scope(envelope["command_name"], serializer.validated_data, actor)
        refs.update(envelope["assertion"]["evidence_ids"])
        if not refs.issubset(self.identities().values_list("object_id", flat=True)):
            raise PermissionDenied("Assertion evidence is unavailable in this context.")
        result = execute_command(actor=actor, workspace=request.auth.workspace, envelope=json_value(envelope))
        execution = CommandExecution.objects.get(pk=result["command_id"])
        return Response(
            {
                "command_id": str(execution.pk),
                "intent_hash": execution.intent_hash,
                "idempotency_key": execution.idempotency_key,
                "status": execution.status,
                "code": result["code"],
            },
            status=202,
        )


class RuntimeCapabilitiesView(RuntimeView):
    def get(self, request, slug):
        c = request.auth
        grant = ActorGrant.objects.get(workspace=c.workspace, actor_type="agent", actor_id=c.actor_id, is_active=True)
        definitions = {
            k: {"id": k, "description": k, **v}
            for k, v in DEFINITIONS.items()
            if OPERATIONS[k] in grant.commands and "LinkObjects" in grant.commands and "*" in grant.fields
        }
        return Response(
            {
                "contract_version": "1.0",
                "backend": "command-layer",
                "tbox_version": load_schema()["version"],
                "ontology_sha256": load_schema()["sha256"],
                "context": c.context,
                "person_id": str(get_object_or_404(self.identities(), object_id=c.person_id).external_id),
                "definitions": definitions,
                "commands": [
                    name
                    for name in grant.commands
                    if name in INPUTS and name not in COLLABORATION_COMMANDS | {"ApproveDecision"}
                ],
                "entity_count": self.identities().count(),
            }
        )


class RuntimePrepareView(RuntimeView):
    @transaction.atomic
    def post(self, request, slug):
        parsed = PrepareInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        p = parsed.validated_data
        name = OPERATIONS[p["operation"]]
        if set(p["parameters"]) - set(DEFINITIONS[p["operation"]]["parameters"]):
            raise ValidationError("Undeclared operation parameters.")
        source = p["provenance"]["source"]
        expected_source = (
            f"telegram:update={source['update_id']};chat={source['chat_id']};message={source['message_id']};"
            f"author={source['author']};timestamp={source['timestamp']};sha256={source['text_sha256']}"
        )
        if p["operation"] == "capture_issue" and p["parameters"].get("source") != expected_source:
            raise ValidationError({"code": "evidence_source_conflict"})
        if p["operation"] == "record_measurement" and "evidence_id" not in p["parameters"]:
            if (
                p["parameters"].get("evidence_source") != expected_source
                or hashlib.sha256(str(p["parameters"].get("evidence_text", "")).encode()).hexdigest()
                != source["text_sha256"]
            ):
                raise ValidationError({"code": "evidence_source_conflict"})
        data = dict(p["parameters"])
        data["context"] = request.auth.context
        target_key = {"delegate": "action_id", "review": "target_id", "record_measurement": "indicator_id"}.get(
            p["operation"]
        )
        if target_key:
            if not p.get("target_id"):
                raise ValidationError("Target required.")
            data[target_key] = self.resolve(p["target_id"])
        elif p.get("target_id"):
            raise ValidationError("Capture does not accept a target.")
        for key in ("executor_id", "owner_id", "evidence_id"):
            if key in data:
                data[key] = self.resolve(data[key])
        if "executor_ids" in data:
            data["executor_ids"] = [self.resolve(pk) for pk in data["executor_ids"]]
        serializer = INPUTS[name](data=json_value(data))
        serializer.is_valid(raise_exception=True)
        actor = self.actor(p["provenance"])
        refs = self.scope(name, serializer.validated_data, actor)
        result = execute_command(
            actor=actor,
            workspace=request.auth.workspace,
            envelope={
                "command_name": name,
                "command_version": 1,
                "idempotency_key": p["idempotency_key"],
                "expected_versions": {str(obj.pk): obj.version for obj in Object.objects.filter(pk__in=refs)},
                "reason": actor.reason,
                "input": json_value(data),
                "assertion": {"kind": "asserted", "evidence_ids": []},
            },
        )
        execution = CommandExecution.objects.get(pk=result["command_id"])
        revision = execution.envelope["expected_versions"].get(str(data.get(target_key)), 0)
        return Response(
            {
                "operation": p["operation"],
                "context": request.auth.context,
                "target_id": p.get("target_id"),
                "expected_revision": revision,
                "parameters": p["parameters"],
                "execution_context": {
                    "backend": "command-layer",
                    "contract_version": "1.0",
                    "command_id": str(execution.pk),
                    "intent_hash": execution.intent_hash,
                    "idempotency_key": execution.idempotency_key,
                    "operation": p["operation"],
                    "target_id": p.get("target_id"),
                    "expected_revision": revision,
                    "parameters_hash": hashlib.sha256(
                        json.dumps(json_value(p["parameters"]), sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                },
                "status": result["status"],
            },
            status=202,
        )


def project_result(result, workspace):
    # Only canonical Object IDs cross this boundary; auxiliary row IDs are private.
    object_ids = result.get("versions_after", {})
    identities = {
        str(i.object_id): i.external_id
        for i in RuntimeObjectIdentity.objects.filter(workspace=workspace, object_id__in=object_ids)
    }
    target = result.get("data", {}).get("object", {}).get("id")
    return {
        "status": "executed",
        "code": "ok",
        "operation_id": result["command_id"],
        "target_id": identities.get(str(target)),
        "revision": object_ids.get(str(target)),
        "created_ids": [identities[pk] for pk in result["created_ids"] if pk in identities],
    }


class RuntimeResolveView(RuntimeView):
    @transaction.atomic
    def post(self, request, slug):
        parsed = ResolveInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        p, c = parsed.validated_data, request.auth
        source = ProvenanceInput().fields["source"].run_validation(p["source"])
        # Reuse the trusted metadata validator for the human confirmation as well.
        source = ProvenanceInput().validate_source(source)
        if source["author"] != c.external_author:
            raise PermissionDenied("Confirmation author does not match the reviewer.")
        execution = get_object_or_404(
            CommandExecution.objects.select_for_update(),
            pk=p["command_id"],
            workspace=c.workspace,
            actor_type="agent",
            actor_id=c.actor_id,
        )
        if (
            execution.intent_hash != p["intent_hash"]
            or execution.idempotency_key != p["idempotency_key"]
            or execution.actor_context.get("metadata", {}).get("credential_id") != str(c.pk)
        ):
            raise PermissionDenied("Saved intention does not match this credential.")
        original = dict(execution.actor_context)
        for key in ("actor_id", "correlation_id", "run_id", "approval_id", "on_behalf_of"):
            if original.get(key):
                original[key] = UUID(original[key])
        original["timestamp"] = datetime.fromisoformat(original["timestamp"])
        actor = Actor(**original)
        serializer = INPUTS[execution.command_name](data=execution.envelope["input"])
        serializer.is_valid(raise_exception=True)
        self.scope(execution.command_name, serializer.validated_data, actor)
        approval = get_object_or_404(CommandApproval, execution=execution)
        if approval.status == "pending":
            reviewer = Actor(
                actor_type="human",
                actor_id=c.reviewer_id,
                reason=p["rationale"],
                source="radar.cos.telegram.confirmation",
                correlation_id=actor.correlation_id,
                timestamp=datetime.fromisoformat(source["timestamp"].replace("Z", "+00:00")),
                metadata={"message": source, "credential_id": str(c.pk)},
            )
            review_command(
                actor=reviewer,
                workspace=c.workspace,
                command_id=execution.pk,
                intent_hash=p["intent_hash"],
                approve=p["approve"],
                rationale=p["rationale"],
            )
            approval.refresh_from_db()
        if not p["approve"] or approval.status == "rejected":
            if execution.status in {"executed", "noop"}:
                raise ValidationError("An executed intention cannot be rejected.")
            return Response(
                {
                    "status": "rejected",
                    "code": "not_authorized",
                    "created_ids": [],
                    "target_id": None,
                    "revision": None,
                    "operation_id": str(execution.pk),
                }
            )
        envelope = command_envelope(execution)
        envelope["approval_id"] = str(approval.pk)
        result = execute_command(
            actor=replace(actor, approval_id=approval.pk), workspace=c.workspace, envelope=envelope
        )
        return Response(project_result(result, c.workspace))


class RuntimeQueryView(RuntimeView):
    def post(self, request, slug):
        parsed = QueryInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        method, p = parsed.validated_data["method"], parsed.validated_data["parameters"]
        if (
            set(p) - {"entity_id", "query", "entity_type", "status", "limit", "depth", "context"}
            or p.get("context", request.auth.context) != request.auth.context
        ):
            raise ValidationError("Query must use the bound context and declared parameters.")
        if method == "list_action_types":
            return Response(RuntimeCapabilitiesView.get(self, request, slug).data["definitions"])
        if method == "validate_vault":
            from plane.radar.commands.primitives_semantic import validate_value
            from plane.radar.models import PropertyValue

            failures = []
            for item in PropertyValue.objects.filter(
                object_id__in=self.identities().values_list("object_id", flat=True)
            ).select_related("definition"):
                try:
                    validate_value(item.definition, item.value, request.auth.workspace)
                except ValidationError:
                    failures.append({"code": "invalid_property_value", "severity": "error"})
            return Response(
                {
                    "valid": not failures,
                    "error_count": len(failures),
                    "warning_count": 0,
                    "finding_count": len(failures),
                    "issues": failures[:20],
                }
            )
        limit, depth = p.get("limit", 100), p.get("depth", 1)
        if type(limit) is not int or not 1 <= limit <= 100 or type(depth) is not int or not 0 <= depth <= 3:
            raise ValidationError("Query limit/depth out of range.")
        identities = list(self.identities())
        by_id = {i.object_id: i for i in identities}
        external = {i.external_id: i for i in identities}
        edges = list(
            Relation.objects.filter(
                workspace=request.auth.workspace, source_id__in=by_id, target_id__in=by_id
            ).select_related("relation_type")
        )

        def entity(i):
            record = OperationalRecord.objects.filter(object_id=i.object_id).first()
            operation_data = record.data if record else {}

            def canonical(value):
                if isinstance(value, dict):
                    return {k: canonical(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [canonical(v) for v in value]
                try:
                    identifier = UUID(value) if isinstance(value, str) and len(value) == 36 else None
                except ValueError:
                    identifier = None
                return by_id[identifier].external_id if identifier in by_id else None if identifier else value

            return {
                "title": i.object.title,
                "body": i.object.content,
                "metadata": {
                    "id": i.external_id,
                    "title": i.object.title,
                    "type": i.object.object_type.key,
                    "revision": i.object.version,
                    "scope": i.context,
                    **effective_values(i.object),
                    "operation_data": canonical(operation_data),
                    "relations": [
                        {"type": e.relation_type.key, "target_id": by_id[e.target_id].external_id}
                        for e in edges
                        if e.source_id == i.object_id
                    ],
                },
            }

        if method == "search_entities":
            query = str(p.get("query", "")).casefold()
            matches = [
                i
                for i in identities
                if (not query or query in i.object.title.casefold() or query in i.external_id.casefold())
                and (not p.get("entity_type") or i.object.object_type.key == p["entity_type"])
                and (not p.get("status") or effective_values(i.object).get("status") == p["status"])
            ]
            return Response(
                [
                    {
                        "id": i.external_id,
                        "title": i.object.title,
                        "type": i.object.object_type.key,
                        "status": effective_values(i.object)["status"],
                        "revision": i.object.version,
                    }
                    for i in sorted(matches, key=lambda x: (x.object.title.casefold(), x.external_id))[:limit]
                ]
            )
        root = external.get(p.get("entity_id"))
        if root is None:
            raise NotFound("Entity unavailable.")
        if method == "read_entity":
            return Response(entity(root))
        selected, frontier = {root.object_id}, {root.object_id}
        truncated = False
        for _ in range(depth):
            neighbors = {
                pk
                for e in edges
                if e.source_id in frontier or e.target_id in frontier
                for pk in (e.source_id, e.target_id)
            } - selected
            room = max(0, 21 - len(selected))
            truncated |= len(neighbors) > room
            frontier = set(sorted(neighbors)[:room])
            selected |= frontier
        return Response(
            {
                "root_id": root.external_id,
                "entities": [entity(by_id[pk]) for pk in sorted(selected)],
                "edges": [
                    {
                        "source_id": by_id[e.source_id].external_id,
                        "target_id": by_id[e.target_id].external_id,
                        "type": e.relation_type.key,
                    }
                    for e in edges
                    if e.source_id in selected and e.target_id in selected
                ][:41],
                "truncated": truncated,
            }
        )
