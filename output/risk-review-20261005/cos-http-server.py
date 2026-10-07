"""Disposable test transport running the actual Deep Agents graph with a scripted model."""
import json
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "COS_AGENT_V2"))
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import create_engine
import uvicorn
from langchain_core.messages import AIMessage
from app.api import agent_runtime as api
from app.database.agent_runtime import AgentRuntimeRepository
from app.database.schema import metadata, radar_agent_runs
from app.runtime.deep_agents import DeepAgentsAdapter, generate
from app.agent import agent as engine_module
from tests.agent.conftest import ScriptedChatModel

engine = create_engine(f"sqlite:////private/tmp/risk-review-http-{uuid4()}.sqlite", connect_args={"check_same_thread": False})
metadata.create_all(engine, tables=[radar_agent_runs])
api.settings.radar_agent_runtime_token = SecretStr("radar-local-integration-test-key-0001")
builder = engine_module.build_product_runtime_agent

def scripted(request):
    if request.skill != "risk_review":
        from app.runtime.deep_agents import system_context
        return {"text": system_context(request)[:8000], "truncated": request.context.truncated,
                "sources": [{"id": str(o.id), "version": o.version} for o in request.context.objects]}
    objects = request.context.objects
    risk = next(o for o in objects if o.type == "risk")
    target = next(o for o in objects if o.type in {"objective", "project"})
    suggestion = {"explanation": "O licenciamento pode atrasar a implantação de Governança de IA e o Sandbox IA. Esta é uma inferência para revisão humana.",
        "suggested_relation": {"source_id": str(risk.id), "target_id": str(target.id), "relation": "threatens"},
        "suggested_action": {"title": "Validar licenciamento de IA", "description": "Confirmar prazo e alternativas para evitar atraso", "next_step": "Consultar a equipe de licenciamento", "mitigates_risk_id": str(risk.id)},
        "confidence": 0.8, "evidence": [{"object_id": str(o.id), "version": o.version, "field": "title", "quote": o.title} for o in (risk, target)], "context_used": []}
    output = {"summary": "Licenciamento pode afetar a entrega. As sugestões aguardam revisão humana.", "suggestions": [suggestion]}
    model = ScriptedChatModel(responses=[AIMessage(content=json.dumps(output))])
    engine_module.build_product_runtime_agent = lambda: builder(model)
    return generate(request)

adapter = DeepAgentsAdapter(AgentRuntimeRepository(engine), scripted)
api.runtime = lambda: adapter
app = FastAPI(); app.include_router(api.router)
uvicorn.run(app, host="0.0.0.0", port=8935, log_level="warning")
