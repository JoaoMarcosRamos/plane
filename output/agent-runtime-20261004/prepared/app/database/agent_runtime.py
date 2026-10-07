"""Durable read-only runs, optimistic transitions and replayable event batches."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.database.schema import radar_agent_runs
from app.runtime.contracts import RunAccess, RunRequest, RunSnapshot, fingerprint

TERMINAL = {"completed", "failed", "cancelled", "unknown"}
LEASE_SECONDS = 180


class RuntimeConflict(ValueError):
    pass


class RuntimeNotFound(LookupError):
    pass


class AgentRuntimeRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(self, request: RunRequest) -> dict[str, Any]:
        data = request.model_dump(mode="json")
        state = {
            "status": "interrupted" if request.start_paused else "queued",
            "events": [
                {
                    "sequence": 1,
                    "type": "interrupted" if request.start_paused else "queued",
                    "timestamp": time.time(),
                }
            ],
            "result": None,
            "pending_result": None,
            "error": None,
            "lease": None,
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(radar_agent_runs).values(
                        run_id=str(request.run_id),
                        request_hash=fingerprint(data),
                        identity=data["identity"],
                        context_hash=fingerprint(data["context"]),
                        request=data,
                        version=1,
                        state=state,
                    )
                )
        except IntegrityError:
            existing = self._read(str(request.run_id))
            if existing["identity"] != data["identity"]:
                raise RuntimeNotFound("run_unavailable") from None
            if existing["request_hash"] != fingerprint(data):
                raise RuntimeConflict("idempotency_conflict") from None
        return self.get(str(request.run_id), self.access(request))

    @staticmethod
    def access(request: RunRequest) -> RunAccess:
        return RunAccess(
            identity=request.identity,
            context_hash=fingerprint(request.context.model_dump(mode="json")),
        )

    def _read(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(radar_agent_runs).where(radar_agent_runs.c.run_id == run_id))
                .mappings()
                .first()
            )
        if row is None:
            raise RuntimeNotFound("run_unavailable")
        return dict(row)

    def _change(
        self, run_id: str, change: Callable[[dict[str, Any]], bool], access: RunAccess | None = None
    ) -> dict[str, Any]:
        for _ in range(12):
            row = self._read(run_id)
            if access is not None:
                if row["identity"] != access.identity.model_dump(mode="json"):
                    raise RuntimeNotFound("run_unavailable")
                if row["context_hash"] != access.context_hash:
                    raise RuntimeConflict("context_stale")
            if not change(row):
                return row
            with self.engine.begin() as conn:
                count = conn.execute(
                    update(radar_agent_runs)
                    .where(
                        radar_agent_runs.c.run_id == run_id,
                        radar_agent_runs.c.version == row["version"],
                    )
                    .values(state=row["state"], version=row["version"] + 1)
                ).rowcount
            if count:
                row["version"] += 1
                return row
        raise RuntimeConflict("concurrent_transition")

    @staticmethod
    def _event(state: dict[str, Any], name: str) -> None:
        # Reserve room for cancellation/completion; repeated controls are bounded.
        if len(state["events"]) >= 120 and name not in TERMINAL:
            raise RuntimeConflict("event_budget_exhausted")
        state["events"].append(
            {"sequence": len(state["events"]) + 1, "type": name, "timestamp": time.time()}
        )

    @classmethod
    def _expire(cls, row: dict[str, Any]) -> bool:
        state = row["state"]
        if state["status"] in {"running", "pause_requested"} and state["lease"] < time.time():
            state.update(status="unknown", error="execution_lease_expired", pending_result=None)
            cls._event(state, "unknown")
            return True
        return False

    @staticmethod
    def public(row: dict[str, Any], after: int = 0) -> dict[str, Any]:
        state = row["state"]
        return RunSnapshot.model_validate(
            {
                "contract_version": "1.0",
                "run_id": row["run_id"],
                "status": state["status"],
                "result": state["result"],
                "error": state["error"],
                "events": [e for e in state["events"] if e["sequence"] > after],
                "cursor": len(state["events"]),
            }
        ).model_dump(mode="json")

    def get(self, run_id: str, access: RunAccess) -> dict[str, Any]:
        return self.public(self._change(run_id, self._expire, access), access.after)

    def control(self, run_id: str, access: RunAccess, action: str) -> dict[str, Any]:
        def mutate(row: dict[str, Any]) -> bool:
            if self._expire(row):
                return True
            s = row["state"]
            if s["status"] in TERMINAL:
                if action == "cancel" and s["status"] == "cancelled":
                    return False
                raise RuntimeConflict("run_terminal")
            if action == "cancel":
                s.update(status="cancelled", result=None, pending_result=None)
            elif action == "interrupt":
                if s["status"] in {"interrupted", "pause_requested"}:
                    return False
                s["status"] = "pause_requested" if s["status"] == "running" else "interrupted"
            elif action == "resume":
                if s["status"] == "queued":
                    return False
                if s["status"] != "interrupted":
                    raise RuntimeConflict("run_not_interrupted")
                if s["pending_result"] is not None:
                    s.update(status="completed", result=s["pending_result"], pending_result=None)
                else:
                    s["status"] = "queued"
            else:
                raise RuntimeConflict("unsupported_control")
            self._event(s, s["status"])
            return True

        return self.public(self._change(run_id, mutate, access))

    def claim(self, run_id: str) -> tuple[RunRequest, int] | None:
        def mutate(row: dict[str, Any]) -> bool:
            if self._expire(row):
                return True
            if row["state"]["status"] != "queued":
                return False
            s = row["state"]
            s.update(status="running", lease=time.time() + LEASE_SECONDS)
            # A token is unique to this successful claim, even if CAS retries.
            s["claim"] = row["version"] + 1
            self._event(s, "context_loaded")
            self._event(s, "running")
            return True

        # Distinguish a successful claim from observing another worker's claim.
        claimed: list[int] = []

        def claim_once(row: dict[str, Any]) -> bool:
            claimed.clear()
            queued = row["state"]["status"] == "queued"
            changed = mutate(row)
            if queued and changed:
                claimed.append(row["state"]["claim"])
            return changed

        row = self._change(run_id, claim_once)
        if not claimed:
            return None
        return RunRequest.model_validate(row["request"]), claimed[0]

    def finish(
        self, run_id: str, claim: int, result: dict[str, object] | None, error: str | None
    ) -> None:
        def mutate(row: dict[str, Any]) -> bool:
            if self._expire(row):
                return True
            s = row["state"]
            if s["status"] not in {"running", "pause_requested"} or s.get("claim") != claim:
                return False
            if error:
                s.update(status="failed", error=error)
            elif s["status"] == "pause_requested":
                s.update(status="interrupted", pending_result=result)
            else:
                s.update(status="completed", result=result)
            self._event(s, s["status"])
            return True

        self._change(run_id, mutate)
