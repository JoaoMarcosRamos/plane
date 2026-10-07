"""Server-to-server product API. Distinct key and routes from the synthetic API."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine

from app.config import settings
from app.database.agent_runtime import AgentRuntimeRepository, RuntimeConflict, RuntimeNotFound
from app.runtime.contracts import RunAccess, RunRequest
from app.runtime.deep_agents import DeepAgentsAdapter

bearer = HTTPBearer(auto_error=False)


def authenticate(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    secret = settings.radar_agent_runtime_token
    expected = secret.get_secret_value() if secret else ""
    if len(expected) < 32 or not expected.isascii():
        raise HTTPException(503, "runtime_unconfigured")
    supplied = credentials.credentials if credentials else ""
    if not supplied.isascii() or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(
    prefix="/agent-runtime/v1", tags=["agent-runtime"], dependencies=[Depends(authenticate)]
)


@lru_cache(maxsize=1)
def runtime() -> DeepAgentsAdapter:
    return DeepAgentsAdapter(
        AgentRuntimeRepository(create_engine(settings.database_url, pool_pre_ping=True))
    )


def close_runtime() -> None:
    if runtime.cache_info().currsize:
        runtime().repository.engine.dispose()
        runtime.cache_clear()


def invoke(operation: Callable[..., dict[str, Any]], *args: object) -> dict[str, Any]:
    try:
        return operation(*args)
    except RuntimeNotFound:
        raise HTTPException(404, "run_unavailable") from None
    except RuntimeConflict as error:
        raise HTTPException(409, str(error)) from None


@router.post("/runs", status_code=202)
def run(request: RunRequest, tasks: BackgroundTasks) -> dict[str, Any]:
    adapter = runtime()
    result = invoke(adapter.invoke_skill if request.skill else adapter.run, request)
    if result["status"] == "queued":
        tasks.add_task(adapter.execute, str(request.run_id))
    return result


@router.post("/runs/{run_id}/{operation}", response_model=None)
def control(
    run_id: UUID, operation: str, access: RunAccess, tasks: BackgroundTasks
) -> dict[str, Any] | StreamingResponse:
    adapter = runtime()
    if operation not in {"status", "stream", "interrupt", "resume", "cancel"}:
        raise HTTPException(404, "operation_unavailable")
    method = adapter.stream if operation in {"status", "stream"} else getattr(adapter, operation)
    result = invoke(method, str(run_id), access)
    if operation == "resume" and result["status"] == "queued":
        tasks.add_task(adapter.execute, str(run_id))
    if operation == "stream":

        def events() -> Iterator[str]:
            for event in result["events"]:
                yield f"id: {event['sequence']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
            # A snapshot ends each finite batch; client reconnects using its cursor.
            snapshot = {k: v for k, v in result.items() if k != "events"}
            yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

        return StreamingResponse(
            events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
        )
    return result
