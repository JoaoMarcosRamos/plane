"""HTTP port for RADAR Command Layer 1.0; no model-selected identity or direct writes."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx

from app.errors import RadarQueryError, RadarStartupError
from app.observability import correlation_fields
from app.security.radar_provenance import radar_source_context

CORE_SHA256 = "8ea1a14a17c25ff1e6a4945bf75f51982b7ce2243b3509df18a5f74a3bfd6ab7"


def parameters_hash(parameters: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def correlation_uuid(value: str, namespace: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, f"cos:{namespace}:{value}"))


class RadarCommandRuntime:
    """One backend for reads, preparation, approval and reconciliation."""

    backend = "command-layer"
    package_version = "command-layer/1.0"
    abox_schema_version = "postgresql/1"
    state = "ready"
    error_code = None
    validation_error_count = 0

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        context: str,
        person_id: str,
        allowed_tbox_versions: frozenset[str],
        client: httpx.Client | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not token
        ):
            raise RadarStartupError("incomplete_configuration")
        self.base_url = base_url.rstrip("/") + "/"
        self.context, self.person_id = context, person_id
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)
        self._headers = {"Authorization": f"Bearer {token}"}
        self._versions = allowed_tbox_versions
        self.agent_tools = self
        self.operation_runtime = self
        self.vault = self  # No filesystem object; compatibility with the service lifecycle.
        try:
            self.ensure_current()
        except Exception:
            self.client.close()
            raise

    def _request(self, path: str, payload: dict[str, object] | None = None) -> Any:
        try:
            response = (
                self.client.get(self.base_url + path, headers=self._headers)
                if payload is None
                else self.client.post(self.base_url + path, headers=self._headers, json=payload)
            )
            raw = response.json()
        except (httpx.HTTPError, ValueError):
            raise RadarQueryError("persistence_failure") from None
        if response.status_code >= 500:
            raise RadarQueryError("persistence_failure")
        if response.status_code >= 400:
            code = raw.get("code") if isinstance(raw, dict) else None
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
            raise RadarQueryError(code if code in allowed else "not_authorized")
        return raw

    def ensure_current(self) -> None:
        raw = self._request("capabilities/")
        if (
            not isinstance(raw, dict)
            or raw.get("contract_version") != "1.0"
            or raw.get("ontology_sha256") != CORE_SHA256
            or raw.get("tbox_version") not in self._versions
            or raw.get("context") != self.context
            or raw.get("person_id") != self.person_id
            or not isinstance(raw.get("definitions"), dict)
        ):
            raise RadarStartupError("package_contract_invalid")
        self.definitions = raw["definitions"]
        self.tbox_version = raw["tbox_version"]
        self.entity_count = raw["entity_count"]

    def close(self) -> None:
        self.client.close()

    def prepare_command(self, envelope: dict[str, object]) -> dict[str, object]:
        """Trusted host port for the common catalog; not a generic model tool."""
        source, correlation = radar_source_context(), correlation_fields()
        if source is None or not correlation.get("run_id") or not correlation.get("thread_id"):
            raise RadarQueryError("radar_source_unavailable")
        raw = self._request(
            "commands/prepare/",
            {
                "envelope": envelope,
                "provenance": {
                    "run_id": correlation_uuid(correlation["run_id"], "run"),
                    "correlation_id": correlation_uuid(correlation["thread_id"], "thread"),
                    "reason": envelope.get("reason"),
                    "source": source.metadata(),
                },
            },
        )
        if not isinstance(raw, dict) or raw.get("status") != "pending_approval":
            raise RadarQueryError("invalid_response")
        return raw

    def resolve_command(
        self, receipt: dict[str, object], *, approve: bool, approval_source: dict[str, object]
    ) -> dict[str, object]:
        raw = self._request(
            "resolve/",
            {
                "command_id": receipt["command_id"],
                "intent_hash": receipt["intent_hash"],
                "idempotency_key": receipt["idempotency_key"],
                "approve": approve,
                "rationale": "Explicit Telegram approval"
                if approve
                else "Explicit Telegram rejection",
                "source": approval_source,
            },
        )
        if not isinstance(raw, dict):
            raise RadarQueryError("persistence_failure")
        return raw

    def prepare(self, *_: object, **__: object) -> None:
        """Capability marker; preparation is invoked through prepare_operation."""
        raise RadarQueryError("invalid_request")

    def prepare_operation(
        self, operation: str, parameters: dict[str, object], *, context: str, target_id: str | None
    ) -> dict[str, object]:
        source, correlation = radar_source_context(), correlation_fields()
        if (
            context != self.context
            or source is None
            or not correlation.get("run_id")
            or not correlation.get("thread_id")
        ):
            raise RadarQueryError("radar_source_unavailable")
        key = f"radar:{uuid4()}"
        raw = self._request(
            "prepare/",
            {
                "operation": operation,
                "parameters": parameters,
                "target_id": target_id,
                "idempotency_key": key,
                "provenance": {
                    "run_id": correlation_uuid(correlation["run_id"], "run"),
                    "correlation_id": correlation_uuid(correlation["thread_id"], "thread"),
                    "reason": f"Telegram request: {operation}",
                    "source": source.metadata(),
                },
            },
        )
        if (
            not isinstance(raw, dict)
            or raw.get("status") != "pending_approval"
            or not isinstance(raw.get("execution_context"), dict)
            or raw["execution_context"].get("idempotency_key") != key
            or raw["execution_context"].get("parameters_hash") != parameters_hash(parameters)
        ):
            raise RadarQueryError("invalid_response")
        return raw

    def execute_operation(
        self,
        operation: str,
        *,
        context: str,
        target_id: str | None,
        expected_revision: int,
        parameters: dict[str, object],
        idempotency_key: str,
        execution_context: dict[str, object] | None = None,
        approval_source: dict[str, object] | None = None,
        approve: bool = True,
    ) -> dict[str, object]:
        receipt = execution_context or {}
        if (
            context != self.context
            or receipt.get("backend") != self.backend
            or receipt.get("contract_version") != "1.0"
            or receipt.get("operation") != operation
            or receipt.get("target_id") != target_id
            or receipt.get("idempotency_key") != idempotency_key
            or receipt.get("parameters_hash") != parameters_hash(parameters)
            or receipt.get("expected_revision") != expected_revision
            or approval_source is None
        ):
            raise RadarQueryError("idempotency_conflict")
        raw = self._request(
            "resolve/",
            {
                "command_id": receipt["command_id"],
                "intent_hash": receipt["intent_hash"],
                "idempotency_key": idempotency_key,
                "approve": approve,
                "rationale": "Explicit Telegram approval"
                if approve
                else "Explicit Telegram rejection",
                "source": approval_source,
            },
        )
        if not isinstance(raw, dict):
            raise RadarQueryError("persistence_failure")
        return raw

    def _query(self, method: str, parameters: dict[str, object]) -> Any:
        if parameters.get("context", self.context) != self.context:
            raise RadarQueryError("entity_unavailable")
        return self._request("query/", {"method": method, "parameters": parameters})

    def search_entities(self, **parameters: object) -> Any:
        return self._query("search_entities", parameters)

    def read_entity(self, entity_id: str, **parameters: object) -> Any:
        return self._query("read_entity", {"entity_id": entity_id, **parameters})

    def get_entity_context(self, entity_id: str, **parameters: object) -> Any:
        return self._query("get_entity_context", {"entity_id": entity_id, **parameters})

    def list_action_types(self) -> Any:
        return self._query("list_action_types", {})

    def validate_vault(self, **parameters: object) -> Any:
        return self._query("validate_vault", parameters)
