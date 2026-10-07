"""Session facade for isolated product executions in COS_AGENT_V2."""

from uuid import uuid4
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response

from plane.radar.agent_runtime import (
    binding_for,
    fingerprint,
    load_context,
    runtime_request,
    verify_snapshot,
    RuntimeConflict,
)
from plane.radar.workspace_schema import lock_schema
from plane.radar.commands.inputs import StrictSerializer
from plane.radar.models import AgentRuntimeRun
from .views import RadarAPIView


class ContextInput(StrictSerializer):
    binding_id = serializers.UUIDField()
    root_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=10)


class RunInput(ContextInput):
    prompt = serializers.CharField(max_length=4000)
    skill = serializers.ChoiceField(
        choices=["context_summary", "risk_review"], required=False, allow_null=True, default=None
    )
    start_paused = serializers.BooleanField(default=False)


class AccessInput(StrictSerializer):
    after = serializers.IntegerField(default=0, min_value=0)


class AgentContextView(RadarAPIView):
    @transaction.atomic
    def post(self, request, slug):
        parsed = ContextInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        workspace = self.workspace()
        lock_schema(workspace)
        _, grant, _, objects = binding_for(
            user=request.user, workspace=workspace, binding_id=parsed.validated_data["binding_id"]
        )
        return Response(load_context(objects, grant, parsed.validated_data["root_ids"]))


class AgentRunsView(RadarAPIView):
    def post(self, request, slug):
        parsed = RunInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        data = parsed.validated_data
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 128:
            raise serializers.ValidationError("Send an Idempotency-Key of 1–128 characters.")
        workspace = self.workspace()
        binding, grant, identity, objects = binding_for(
            user=request.user, workspace=workspace, binding_id=data["binding_id"]
        )
        input_data = {
            "binding_id": str(binding.pk),
            "root_ids": sorted(str(pk) for pk in set(data["root_ids"])),
            "prompt": data["prompt"],
            "skill": data["skill"],
            "start_paused": data["start_paused"],
        }
        # Lock the workspace only for local intent creation, never for the HTTP call.
        with transaction.atomic():
            type(workspace).objects.select_for_update().get(pk=workspace.pk)
            binding, grant, identity, objects = binding_for(
                user=request.user, workspace=workspace, binding_id=data["binding_id"]
            )
            run = AgentRuntimeRun.objects.filter(workspace=workspace, user=request.user, idempotency_key=key).first()
            if run is not None:
                if run.input_hash != fingerprint(input_data):
                    raise RuntimeConflict({"code": "idempotency_conflict"})
                verify_snapshot(objects, run.request_data["context"])
                if identity != run.request_data["identity"]:
                    raise RuntimeConflict({"code": "authorization_stale"})
            else:
                snapshot = load_context(objects, grant, data["root_ids"])
                run_id = uuid4()
                payload = {
                    "contract_version": "1.0",
                    "run_id": str(run_id),
                    "identity": identity,
                    "context": snapshot,
                    "agent_config": binding.agent_config_snapshot,
                    "prompt": data["prompt"],
                    "skill": data["skill"],
                    "start_paused": data["start_paused"],
                }
                run = AgentRuntimeRun.objects.create(
                    id=run_id,
                    workspace=workspace,
                    user=request.user,
                    binding=binding,
                    idempotency_key=key,
                    input_hash=fingerprint(input_data),
                    request_data=payload,
                )
        # A lost response can be reconciled by replaying this same stored run ID and intent.
        return Response(runtime_request("runs", run.request_data), status=202)


class AgentRunControlView(RadarAPIView):
    def post(self, request, slug, run_id, operation):
        if operation not in {"status", "stream", "interrupt", "resume", "cancel"}:
            from rest_framework.exceptions import NotFound

            raise NotFound("Operation unavailable.")
        parsed = AccessInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        workspace = self.workspace()
        run = get_object_or_404(AgentRuntimeRun, pk=run_id, workspace=workspace, user=request.user)
        _, _, identity, objects = binding_for(user=request.user, workspace=workspace, binding_id=run.binding_id)
        verify_snapshot(objects, run.request_data["context"])
        if identity != run.request_data["identity"]:
            raise RuntimeConflict({"code": "authorization_stale"})
        payload = {
            "identity": identity,
            "context_hash": fingerprint(run.request_data["context"]),
            "after": parsed.validated_data["after"],
        }
        result = runtime_request(f"runs/{run.id}/{operation}", payload, stream=operation == "stream")
        if operation == "stream":
            response = HttpResponse(result, content_type="text/event-stream")
            response["Cache-Control"] = "no-store"
            return response
        return Response(result)
