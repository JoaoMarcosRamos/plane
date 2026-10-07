"""Phase 1.8 CoS product runtime: real DeepAgentsAdapter/API router, scripted or real provider model.

Usage (from the CoS checkout, so its own settings/.env resolve the provider for --provider):
    RADAR_AGENT_RUNTIME_TOKEN=... ../COS_AGENT_V2/.venv/bin/python cos-runtime-server.py scripted|provider LEDGER.sqlite
The transport key comes from the environment and must match the Plane API (`.secrets/radar-e2e-runtime.env`).
"""

import json
import os
import sys
from pathlib import Path

COS = Path(__file__).resolve().parents[3] / "COS_AGENT_V2"
sys.path.insert(0, str(COS))
os.chdir(COS)

import uvicorn
from app.api import agent_runtime as api
from app.database.agent_runtime import AgentRuntimeRepository
from app.database.schema import metadata, radar_agent_runs
from app.runtime.deep_agents import DeepAgentsAdapter, generate
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import create_engine

mode, ledger = sys.argv[1], sys.argv[2]
engine = create_engine(f"sqlite:///{ledger}", connect_args={"check_same_thread": False})
metadata.create_all(engine, tables=[radar_agent_runs])
api.settings.radar_agent_runtime_token = SecretStr(
    os.environ["RADAR_AGENT_RUNTIME_TOKEN"]
)


def scripted(request):
    """Deterministic model output; the Deep Agents graph, parsing and CoS validation stay real."""
    from app.agent import agent as engine_module
    from langchain_core.messages import AIMessage
    from tests.agent.conftest import ScriptedChatModel

    if request.skill != "risk_review":
        from app.runtime.deep_agents import system_context

        return {
            "text": system_context(request)[:8000],
            "truncated": request.context.truncated,
            "sources": [
                {"id": str(o.id), "version": o.version} for o in request.context.objects
            ],
        }
    objects = request.context.objects
    risk = next(o for o in objects if o.type == "risk")
    targets = sorted(
        (o for o in objects if o.type in {"objective", "project"}),
        key=lambda o: o.type != "objective",
    )
    actions = {
        "objective": (
            "Validar licenciamento de IA",
            "Confirmar prazo e alternativas para evitar atraso",
        ),
        "project": (
            "Preparar plano B do Sandbox IA",
            "Definir ambiente alternativo caso a licença atrase",
        ),
    }
    suggestions = []
    for target in targets:
        title, description = actions[target.type]
        suggestions.append(
            {
                "explanation": f"O licenciamento pode atrasar '{target.title}'. Esta é uma inferência para revisão humana.",
                "suggested_relation": {
                    "source_id": str(risk.id),
                    "target_id": str(target.id),
                    "relation": "threatens",
                },
                "suggested_action": {
                    "title": title,
                    "description": description,
                    "next_step": "Consultar a equipe de licenciamento",
                    "mitigates_risk_id": str(risk.id),
                },
                "confidence": 0.8 if target.type == "objective" else 0.55,
                "evidence": [
                    {
                        "object_id": str(o.id),
                        "version": o.version,
                        "field": "title",
                        "quote": o.title,
                    }
                    for o in (risk, target)
                ],
                "context_used": [
                    str(r.id)
                    for r in request.context.relations
                    if {r.source, r.target} == {risk.id, target.id}
                ],
            }
        )
    output = {
        "summary": "Licenciamento pode afetar a entrega. As sugestões aguardam revisão humana.",
        "suggestions": suggestions,
    }
    model = ScriptedChatModel(
        responses=[AIMessage(content=json.dumps(output, ensure_ascii=False))]
    )
    builder = engine_module.build_product_runtime_agent
    engine_module.build_product_runtime_agent = lambda: builder(model)
    try:
        return generate(request)
    finally:
        engine_module.build_product_runtime_agent = builder


if mode == "provider":
    from app.agent.model import resolve_model_spec

    print(f"provider model: {resolve_model_spec()}", flush=True)
    executor = generate
elif mode == "scripted":
    executor = scripted
else:
    raise SystemExit("mode must be scripted or provider")

adapter = DeepAgentsAdapter(AgentRuntimeRepository(engine), executor)
api.runtime = lambda: adapter
app = FastAPI()
app.include_router(api.router)
uvicorn.run(
    app, host=os.environ.get("RADAR_E2E_HOST", "127.0.0.1"), port=8940, log_level="info"
)
