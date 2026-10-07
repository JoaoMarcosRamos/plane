"""Disposable HTTP server for the real CoS adapter and typed requests."""
import sys
sys.path.insert(0, "/Users/joaomarcosramos/Documents/Github/COS_AGENT_V2")
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import create_engine
import uvicorn
from app.api import agent_runtime as api
from app.database.agent_runtime import AgentRuntimeRepository
from app.database.schema import metadata, radar_agent_runs
from app.runtime.deep_agents import DeepAgentsAdapter, system_context

engine = create_engine("sqlite:////private/tmp/radar-general-validation-20261004.sqlite", connect_args={"check_same_thread": False})
metadata.create_all(engine, tables=[radar_agent_runs])
api.settings.radar_agent_runtime_token = SecretStr("radar-local-integration-test-key-0001")

def generate(request):
    return {"text": system_context(request)[:8000], "truncated": request.context.truncated,
            "sources": [{"id": str(obj.id), "version": obj.version} for obj in request.context.objects]}

adapter = DeepAgentsAdapter(AgentRuntimeRepository(engine), generate)
api.runtime = lambda: adapter
app = FastAPI()
app.include_router(api.router)
uvicorn.run(app, host="0.0.0.0", port=8926, log_level="warning")
