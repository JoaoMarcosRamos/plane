"""RADAR product DTOs. No harness types or model-controlled authority."""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeIdentity(ClosedModel):
    channel: Literal["plane.session"] = "plane.session"
    workspace_id: UUID
    user_id: UUID
    agent_id: UUID
    binding_id: UUID
    authorization_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ContextObject(ClosedModel):
    id: UUID
    version: int = Field(ge=1)
    type: str = Field(max_length=80)
    title: str = Field(max_length=200)
    content: str = Field(max_length=1500)
    properties: dict[str, object] = Field(default_factory=dict)


class ContextRelation(ClosedModel):
    id: UUID
    source: UUID
    target: UUID
    type: str = Field(max_length=80)


class RuntimeContext(ClosedModel):
    objects: list[ContextObject] = Field(min_length=1, max_length=21)
    relations: list[ContextRelation] = Field(default_factory=list, max_length=40)
    truncated: bool

    @model_validator(mode="after")
    def check_bounds(self) -> RuntimeContext:
        if len(json.dumps(self.model_dump(mode="json"), ensure_ascii=True)) > 30000:
            raise ValueError("Context exceeds the serialized character budget")
        ids = {item.id for item in self.objects}
        if len(ids) != len(self.objects) or any(
            r.source not in ids or r.target not in ids for r in self.relations
        ):
            raise ValueError("Context references must be unique and visible")
        return self


class RunRequest(ClosedModel):
    contract_version: Literal["1.0"] = "1.0"
    run_id: UUID
    identity: RuntimeIdentity
    context: RuntimeContext
    prompt: str = Field(min_length=1, max_length=4000)
    skill: Literal["context_summary"] | None = None
    start_paused: bool = False


class RunAccess(ClosedModel):
    identity: RuntimeIdentity
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    after: int = Field(default=0, ge=0)


class RadarAgentRuntime(Protocol):
    def run(self, request: RunRequest) -> dict[str, object]: ...
    def stream(self, run_id: str, access: RunAccess) -> dict[str, object]: ...
    def invoke_skill(self, request: RunRequest) -> dict[str, object]: ...
    def load_context(self, request: RunRequest) -> RuntimeContext: ...
    def interrupt(self, run_id: str, access: RunAccess) -> dict[str, object]: ...
    def resume(self, run_id: str, access: RunAccess) -> dict[str, object]: ...


class ContextSource(ClosedModel):
    id: UUID
    version: int = Field(ge=1)


class RuntimeResult(ClosedModel):
    text: str = Field(max_length=8000)
    sources: list[ContextSource] = Field(max_length=21)
    truncated: bool


class RuntimeEvent(ClosedModel):
    sequence: int = Field(ge=1)
    type: Literal[
        "queued",
        "context_loaded",
        "running",
        "pause_requested",
        "interrupted",
        "completed",
        "failed",
        "cancelled",
        "unknown",
    ]
    timestamp: float = Field(ge=0)


class RunSnapshot(ClosedModel):
    contract_version: Literal["1.0"] = "1.0"
    run_id: UUID
    status: Literal[
        "queued",
        "running",
        "pause_requested",
        "interrupted",
        "completed",
        "failed",
        "cancelled",
        "unknown",
    ]
    result: RuntimeResult | None
    error: Literal["generation_failed", "execution_lease_expired"] | None
    events: list[RuntimeEvent] = Field(max_length=125)
    cursor: int = Field(ge=0, le=125)
