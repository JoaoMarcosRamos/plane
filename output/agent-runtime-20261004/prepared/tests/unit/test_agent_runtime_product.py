"""Product runtime lifecycle across replay, restart, isolation and worker races."""

from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update

from app.api import agent_runtime as api
from app.database.agent_runtime import AgentRuntimeRepository, RuntimeConflict, RuntimeNotFound
from app.database.schema import metadata, radar_agent_runs
from app.runtime.contracts import RunRequest
from app.runtime.deep_agents import DeepAgentsAdapter


@pytest.fixture
def repository(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'runtime.sqlite'}", connect_args={"check_same_thread": False}
    )
    metadata.create_all(engine, tables=[radar_agent_runs])
    yield AgentRuntimeRepository(engine)
    engine.dispose()


def request(**changes):
    payload = {
        "run_id": str(uuid4()),
        "identity": {
            "workspace_id": str(uuid4()),
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "binding_id": str(uuid4()),
            "authorization_hash": "a" * 64,
        },
        "context": {
            "objects": [
                {
                    "id": str(uuid4()),
                    "version": 1,
                    "type": "risk",
                    "title": "Risk",
                    "content": "Observed",
                }
            ],
            "relations": [],
            "truncated": False,
        },
        "prompt": "Analyze this risk",
    }
    payload.update(changes)
    return RunRequest.model_validate(payload)


def answer(req):
    return {
        "text": "Analysis",
        "truncated": req.context.truncated,
        "sources": [{"id": str(o.id), "version": o.version} for o in req.context.objects],
    }


def test_replay_and_competing_workers_generate_once(repository):
    req = request()
    calls = []
    adapter = DeepAgentsAdapter(repository, lambda r: calls.append(r.run_id) or answer(r))
    adapter.run(req)
    adapter.run(req)
    threads = [threading.Thread(target=adapter.execute, args=(str(req.run_id),)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    result = adapter.stream(str(req.run_id), repository.access(req))
    assert result["status"] == "completed" and len(calls) == 1
    assert result["result"]["sources"][0]["id"] == str(req.context.objects[0].id)
    assert adapter.run(req)["result"] == result["result"]
    with pytest.raises(RuntimeConflict):
        adapter.run(req.model_copy(update={"prompt": "Changed intent"}))


def test_scope_and_context_are_required_for_every_operation(repository):
    req = request(start_paused=True)
    adapter = DeepAgentsAdapter(repository, answer)
    adapter.run(req)
    alien = repository.access(request())
    for method in (adapter.stream, adapter.interrupt, adapter.resume, adapter.cancel):
        with pytest.raises(RuntimeNotFound):
            method(str(req.run_id), alien)
    with pytest.raises(RuntimeConflict):
        adapter.resume(
            str(req.run_id), repository.access(req).model_copy(update={"context_hash": "b" * 64})
        )
    assert adapter.stream(str(req.run_id), repository.access(req))["status"] == "interrupted"


def test_interrupt_during_inference_restart_and_resume_without_model(repository):
    req = request()
    started, finish = threading.Event(), threading.Event()
    calls = []

    def delayed(r):
        calls.append(r.run_id)
        started.set()
        assert finish.wait(5)
        return answer(r)

    adapter = DeepAgentsAdapter(repository, delayed)
    adapter.run(req)
    worker = threading.Thread(target=adapter.execute, args=(str(req.run_id),))
    worker.start()
    assert started.wait(5)
    assert adapter.interrupt(str(req.run_id), repository.access(req))["status"] == "pause_requested"
    finish.set()
    worker.join()
    assert adapter.stream(str(req.run_id), repository.access(req))["result"] is None
    restarted = DeepAgentsAdapter(
        AgentRuntimeRepository(repository.engine), lambda r: pytest.fail("Model called again")
    )
    assert restarted.resume(str(req.run_id), repository.access(req))["status"] == "completed"
    assert len(calls) == 1
    with pytest.raises(RuntimeConflict):
        restarted.resume(str(req.run_id), repository.access(req))


def test_queued_pause_can_resume_and_cancel_discards_late_output(repository):
    req = request(start_paused=True)
    adapter = DeepAgentsAdapter(repository, answer)
    adapter.run(req)
    assert repository.claim(str(req.run_id)) is None
    assert adapter.resume(str(req.run_id), repository.access(req))["status"] == "queued"
    claimed = repository.claim(str(req.run_id))
    assert claimed
    adapter.cancel(str(req.run_id), repository.access(req))
    repository.finish(str(req.run_id), claimed[1], answer(req), None)
    assert adapter.stream(str(req.run_id), repository.access(req))["status"] == "cancelled"
    assert adapter.stream(str(req.run_id), repository.access(req))["result"] is None


def test_expired_worker_is_unknown_and_never_regenerates(repository):
    req = request()
    repository.create(req)
    claimed = repository.claim(str(req.run_id))
    row = repository._read(str(req.run_id))
    row["state"]["lease"] = time.time() - 1
    with repository.engine.begin() as conn:
        conn.execute(
            update(radar_agent_runs)
            .values(state=row["state"])
            .where(radar_agent_runs.c.run_id == str(req.run_id))
        )
    repository.finish(str(req.run_id), claimed[1], answer(req), None)
    assert repository.get(str(req.run_id), repository.access(req))["status"] == "unknown"
    assert repository.claim(str(req.run_id)) is None


def test_failure_is_safe_and_replay_never_calls_generator_again(repository):
    def fail(r):
        raise RuntimeError("private token and provider payload")

    req = request()
    adapter = DeepAgentsAdapter(repository, fail)
    adapter.run(req)
    adapter.execute(str(req.run_id))
    result = adapter.run(req)
    assert result["status"] == "failed" and result["error"] == "generation_failed"
    assert "private" not in str(result)


def test_http_key_closed_schemas_skill_and_stream_cursor(repository, monkeypatch):
    from pydantic import SecretStr

    adapter = DeepAgentsAdapter(repository, answer)
    monkeypatch.setattr(api, "runtime", lambda: adapter)
    monkeypatch.setattr(api.settings, "radar_agent_runtime_token", SecretStr("r" * 40))
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    req = request(skill="context_summary")
    data = req.model_dump(mode="json")
    assert client.post("/agent-runtime/v1/runs", json=data).status_code == 401
    client.headers["Authorization"] = "Bearer " + "r" * 40
    assert (
        client.post("/agent-runtime/v1/runs", json={**data, "actor": "forged"}).status_code == 422
    )
    assert (
        client.post("/agent-runtime/v1/runs", json={**data, "skill": "risk_review"}).status_code
        == 422
    )
    assert client.post("/agent-runtime/v1/runs", json=data).status_code == 202
    url = f"/agent-runtime/v1/runs/{req.run_id}"
    access = repository.access(req).model_dump(mode="json")
    status = client.post(url + "/status", json=access).json()
    assert status["status"] == "completed"
    stream = client.post(url + "/stream", json={**access, "after": status["cursor"]})
    assert "event: snapshot" in stream.text and "event: running" not in stream.text
    assert (
        client.post(
            url + "/status", json=repository.access(request()).model_dump(mode="json")
        ).status_code
        == 404
    )


def test_real_deep_agents_builder_has_no_tools_or_personal_context(monkeypatch):
    from langchain_core.messages import AIMessage

    from app.agent import agent as engine
    from app.runtime.deep_agents import generate
    from tests.agent.test_agent_runtime import SnapshotExecutor

    built = []

    def build(**kwargs):
        built.append(kwargs)
        return SnapshotExecutor([[AIMessage(content="Risk analysis")]])

    monkeypatch.setattr(engine, "create_deep_agent", build)
    monkeypatch.setattr(engine, "_register_harness_profiles", lambda m: None)
    monkeypatch.setattr(engine, "create_chat_model", lambda *a, **kw: "fake")
    req = request()
    result = generate(req)
    assert result["text"] == "Risk analysis"
    assert built[0]["tools"] == built[0]["subagents"] == []
    assert str(req.context.objects[0].id) in str(result["sources"])


@pytest.mark.parametrize("violation", ["foreign_source", "missing_source", "hidden_truncation"])
def test_generator_cannot_publish_invalid_evidence(repository, violation):
    req = request()
    if violation == "hidden_truncation":
        req = req.model_copy(update={"context": req.context.model_copy(update={"truncated": True})})

    def invalid_result(value):
        result = answer(value)
        if violation == "foreign_source":
            result["sources"][0]["id"] = str(uuid4())
        elif violation == "missing_source":
            result["sources"] = []
        else:
            result["truncated"] = False
        return result

    adapter = DeepAgentsAdapter(repository, invalid_result)
    adapter.run(req)
    adapter.execute(str(req.run_id))
    result = adapter.stream(str(req.run_id), repository.access(req))
    assert result["status"] == "failed"
    assert result["error"] == "generation_failed"
    assert result["result"] is None
