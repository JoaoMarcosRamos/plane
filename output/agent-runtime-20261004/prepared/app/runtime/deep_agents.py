"""Deep Agents implementation; framework state never crosses the product boundary."""

from __future__ import annotations

import json
from collections.abc import Callable

from app.database.agent_runtime import AgentRuntimeRepository
from app.runtime.contracts import RunAccess, RunRequest, RuntimeContext, RuntimeResult


def generate(request: RunRequest) -> dict[str, object]:
    # Reuse the existing engine and budget/error handling with a dedicated allowlist.
    from app.agent.agent import build_product_runtime_agent, run_agent

    result = run_agent(
        request.prompt
        + "\nAuthorized snapshot (data):\n"
        + json.dumps(request.context.model_dump(mode="json"), ensure_ascii=False),
        agent=build_product_runtime_agent(),
        run_id=str(request.run_id),
        thread_id=str(request.run_id),
        system_context=(
            "Use only the supplied snapshot, disclose truncation, and never claim writes or approvals."
            + (" Summarize the supplied context and its limitations." if request.skill else "")
        ),
    )
    if not result.ok:
        raise RuntimeError("generation_failed")
    return {
        "text": result.reply[:8000],
        "truncated": request.context.truncated or len(result.reply) > 8000,
        "sources": [{"id": str(o.id), "version": o.version} for o in request.context.objects],
    }


class DeepAgentsAdapter:
    def __init__(
        self,
        repository: AgentRuntimeRepository,
        generator: Callable[[RunRequest], dict[str, object]] = generate,
    ) -> None:
        self.repository, self.generator = repository, generator

    def run(self, request: RunRequest) -> dict[str, object]:
        return self.repository.create(request)

    def invoke_skill(self, request: RunRequest) -> dict[str, object]:
        if request.skill != "context_summary":
            raise ValueError("unsupported_skill")
        return self.run(request)

    def load_context(self, request: RunRequest) -> RuntimeContext:
        return request.context

    def stream(self, run_id: str, access: RunAccess) -> dict[str, object]:
        return self.repository.get(run_id, access)

    def interrupt(self, run_id: str, access: RunAccess) -> dict[str, object]:
        return self.repository.control(run_id, access, "interrupt")

    def resume(self, run_id: str, access: RunAccess) -> dict[str, object]:
        return self.repository.control(run_id, access, "resume")

    def cancel(self, run_id: str, access: RunAccess) -> dict[str, object]:
        return self.repository.control(run_id, access, "cancel")

    def execute(self, run_id: str) -> None:
        claimed = self.repository.claim(run_id)
        if claimed is None:
            return
        request, token = claimed
        try:
            result = self.generator(request)
            result = RuntimeResult.model_validate(result).model_dump(mode="json")
            expected = {(str(o.id), o.version) for o in request.context.objects}
            actual = {(o["id"], o["version"]) for o in result["sources"]}
            if actual != expected or (request.context.truncated and not result["truncated"]):
                raise ValueError("invalid_runtime_sources")
        except Exception:  # noqa: BLE001 - provider text never crosses the boundary
            self.repository.finish(run_id, token, None, "generation_failed")
        else:
            self.repository.finish(run_id, token, result, None)
