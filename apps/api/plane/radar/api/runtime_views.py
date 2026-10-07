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

from plane.db.models import WorkspaceMember
from plane.radar.active import active_objects, active_relations, active_values
from plane.radar.workspace_schema import schema_revision, lock_schema
from plane.radar.commands.actor import Actor
from plane.radar.commands.control import review_command
from plane.radar.commands.execution import (
    require_human_membership,
    authorize,
    execute_command,
    validate_actor,
    command_envelope,
)
from plane.radar.commands.effects import plan_command, check_grant
from plane.radar.commands.capabilities import CAPABILITIES, runtime_definitions, command_contracts
from plane.radar.commands.queries import effective_values
from plane.radar.commands.inputs import CommandInput, INPUTS, StrictSerializer
from plane.radar.commands.operations import OPERATIONS
from plane.radar.models import (
    ActorGrant,
    CommandApproval,
    CommandExecution,
    PersonIdentity,
    RuntimeCredential,
    RuntimeObjectIdentity,
)
from plane.radar.mutation import json_value
from plane.radar.ontology.schema import load_schema
from plane.radar.runtime_identity import runtime_descriptor, runtime_identities, runtime_types
from plane.radar.operational import operation_projection, timezone_for


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
        identities = runtime_identities(credential.workspace, credential.context)
        if "*" not in grant.object_types:
            identities = identities.filter(object__object_type__key__in=grant.object_types)
        if credential.object_ids is not None:
            identities = identities.filter(external_id__in=credential.object_ids)
        if not identities.filter(object_id=credential.person_id).exists():
            raise AuthenticationFailed("Runtime Person unavailable in this scope.")
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

    def get_fields(self):
        fields = super().get_fields()
        fields["operation"].choices = list(OPERATIONS)
        return fields


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
        queryset = runtime_identities(c.workspace, c.context).select_related("object__object_type")
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
        from plane.db.models import Workspace

        Workspace.objects.select_for_update().get(pk=c.workspace_id)
        plan = plan_command(actor=actor, workspace=c.workspace, name=name, data=data)
        refs = {UUID(pk) for pk in plan.dependencies}
        if not refs.issubset(set(self.identities().values_list("object_id", flat=True))):
            raise PermissionDenied("Reference is unavailable in this credential scope.")
        if c.object_ids is not None and any(
            change["model"] == "radar.Object" and change["before"] is None for change in plan.preview["changes"]
        ):
            raise PermissionDenied("Creation requires context-wide authority.")
        check_grant(c.workspace, grant, name, data, plan=plan)
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
    @transaction.atomic
    def get(self, request, slug):
        c = request.auth
        revision = lock_schema(c.workspace)
        grant = ActorGrant.objects.get(workspace=c.workspace, actor_type="agent", actor_id=c.actor_id, is_active=True)
        membership = WorkspaceMember.objects.get(workspace=c.workspace, member_id=c.reviewer_id, is_active=True)
        definitions = {
            k: {"id": k, "description": k, **v}
            for k, v in runtime_definitions(c.workspace, context=c.context, object_types=grant.object_types).items()
            if OPERATIONS[k] in grant.commands and "LinkObjects" in grant.commands and "*" in grant.fields
        }
        eligible = runtime_types(c.workspace, context=c.context)
        if "*" not in grant.object_types:
            eligible = eligible.filter(key__in=grant.object_types)
        return Response(
            {
                "schema_revision": revision,
                "authority_revision": f"{grant.pk}:{grant.policy_version}:{membership.role}",
                "contract_version": "1.0",
                "backend": "command-layer",
                "tbox_version": load_schema()["version"],
                "ontology_sha256": load_schema()["sha256"],
                "context": c.context,
                "person_id": str(get_object_or_404(self.identities(), object_id=c.person_id).external_id),
                "definitions": definitions,
                "object_types": {row.key: runtime_descriptor(row, context=c.context) for row in eligible},
                "commands": [
                    name for name in grant.commands if name in CAPABILITIES and not CAPABILITIES[name].human_only
                ],
                "entity_count": self.identities().count(),
                "command_contracts": {
                    name: contract
                    for name, contract in command_contracts(nonhuman=True).items()
                    if name in grant.commands
                },
            }
        )


class RuntimePrepareView(RuntimeView):
    @transaction.atomic
    def post(self, request, slug):
        parsed = PrepareInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        p = parsed.validated_data
        name = OPERATIONS[p["operation"]]
        grant = ActorGrant.objects.get(
            workspace=request.auth.workspace, actor_type="agent", actor_id=request.auth.actor_id, is_active=True
        )
        definitions = runtime_definitions(
            request.auth.workspace, context=request.auth.context, object_types=grant.object_types
        )
        if p["operation"] not in definitions:
            raise PermissionDenied("This operation is unavailable under the current runtime schema and grant.")
        if set(p["parameters"]) - set(definitions[p["operation"]]["parameters"]):
            raise ValidationError("Undeclared operation parameters.")
        source = p["provenance"]["source"]
        expected_source = (
            f"telegram:update={source['update_id']};chat={source['chat_id']};message={source['message_id']};"
            f"author={source['author']};timestamp={source['timestamp']};sha256={source['text_sha256']}"
        )
        capability = CAPABILITIES[name]
        if capability.source_parameter and "evidence_id" not in p["parameters"]:
            if p["parameters"].get(capability.source_parameter) != expected_source:
                raise ValidationError({"code": "evidence_source_conflict"})
            if (
                capability.evidence_text_parameter
                and hashlib.sha256(
                    str(p["parameters"].get(capability.evidence_text_parameter, "")).encode()
                ).hexdigest()
                != source["text_sha256"]
            ):
                raise ValidationError({"code": "evidence_source_conflict"})
        data = dict(p["parameters"])
        data["context"] = request.auth.context
        target_key = CAPABILITIES[name].target_field
        if target_key:
            if not p.get("target_id"):
                raise ValidationError("Target required.")
            data[target_key] = self.resolve(p["target_id"])
        elif p.get("target_id"):
            raise ValidationError("Capture does not accept a target.")
        for key in CAPABILITIES[name].object_refs:
            if key in data and key != target_key:
                value = data[key]
                data[key] = [self.resolve(pk) for pk in value] if isinstance(value, list) else self.resolve(value)
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
                "expected_schema_revision": schema_revision(request.auth.workspace),
                "expected_versions": {
                    str(obj.pk): obj.version for obj in active_objects(request.auth.workspace).filter(pk__in=refs)
                },
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
    @transaction.atomic
    def post(self, request, slug):
        revision = lock_schema(request.auth.workspace)
        parsed = QueryInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        method, p = parsed.validated_data["method"], parsed.validated_data["parameters"]
        if (
            set(p) - {"entity_id", "query", "entity_type", "status", "limit", "depth", "context", "timezone"}
            or p.get("context", request.auth.context) != request.auth.context
        ):
            raise ValidationError("Query must use the bound context and declared parameters.")
        timezone_name = p.get("timezone", "UTC")
        timezone_for(timezone_name)
        if method == "list_action_types":
            return Response(RuntimeCapabilitiesView.get(self, request, slug).data["definitions"])
        if method == "validate_vault":
            from plane.radar.commands.primitives_semantic import validate_value

            failures = []
            for item in (
                active_values(request.auth.workspace)
                .filter(object_id__in=self.identities().values_list("object_id", flat=True))
                .select_related("definition")
            ):
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
            active_relations(request.auth.workspace)
            .filter(source_id__in=by_id, target_id__in=by_id)
            .select_related("relation_type")
        )

        def entity(i):
            values = effective_values(i.object)
            projected = operation_projection(i.object, values, timezone_name=timezone_name)
            # Keep system projections in the existing operational namespace;
            # arbitrary workspace properties (including `deadline`) stay intact.
            operation_data = {
                "schema_version": projected["schema_version"],
                "migration_required": projected["migration_required"],
                "deadline": projected["deadline"],
                **projected["operation_data"],
            }

            def canonical(value):
                if isinstance(value, dict):
                    # Acceptance maps have Object UUID keys; apply the same
                    # boundary as values and omit identities outside this scope.
                    return {key: canonical(v) for k, v in value.items() if (key := canonical(k)) is not None}
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
                    "schema_revision": revision,
                    "id": i.external_id,
                    "title": i.object.title,
                    "type": i.object.object_type.key,
                    "revision": i.object.version,
                    "scope": i.context,
                    **values,
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
                        "status": effective_values(i.object).get("status"),
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
                "schema_revision": revision,
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
