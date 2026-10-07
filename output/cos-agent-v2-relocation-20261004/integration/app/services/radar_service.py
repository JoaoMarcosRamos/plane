"""Deterministic, read-only host boundary for the optional RADAR runtime."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.errors import RadarQueryError
from app.integrations.radar_vault import RadarVaultRuntime, build_principal, open_radar_vault
from app.schemas.radar import (
    MAX_RADAR_ACTION_TYPES,
    MAX_RADAR_BATCH_REFERENCES,
    MAX_RADAR_COMPOSITE_ITEMS,
    MAX_RADAR_CONTEXT_ENTITIES,
    MAX_RADAR_CONTEXT_RELATIONS,
    MAX_RADAR_OPERATIONAL_BRIEF_ITEMS,
    MAX_RADAR_RESULT_LIMIT,
    MAX_RADAR_SEARCH_PAGES,
    MAX_RADAR_VALIDATION_ISSUES,
    RadarActionAttentionItem,
    RadarActionAttentionReport,
    RadarActionParameter,
    RadarActionType,
    RadarBatchReferenceInput,
    RadarBatchResolution,
    RadarCommitmentItem,
    RadarContextResult,
    RadarDecisionEvidenceReport,
    RadarEntity,
    RadarEntityResolutionResult,
    RadarEntitySummary,
    RadarOperationalAction,
    RadarOperationalBrief,
    RadarOperationalCommitment,
    RadarPersonCommitmentsReport,
    RadarPreflightReport,
    RadarRelation,
    RadarRiskItem,
    RadarRiskReport,
    RadarSearchResult,
    RadarValidationIssue,
    RadarValidationResult,
)
from app.utils.datetime import application_timezone, current_local_date

_ENTITY_ID = re.compile(r"^[A-Z]{3}-\d{8}-[A-Z0-9]{6}$")
_ENTITY_ID_IN_REFERENCE = re.compile(r"\b[A-Z]{3}-\d{8}-[A-Z0-9]{6}\b")
_FILTER = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")

# These are deliberately an allowlist rather than "all frontmatter except a
# few keys".  An ontology update must make a deliberate host decision before a
# new attribute can cross into an LLM context.
_VISIBLE_FIELDS = frozenset(
    {
        "baseline",
        "agenda",
        "cadence",
        "completed_at",
        "consequences",
        "context",
        "current",
        "decision",
        "decided_at",
        "description",
        "document_type",
        "direction",
        "due_date",
        "ends_at",
        "formula",
        "impact",
        "kind",
        "likelihood",
        "location",
        "measured_at",
        "next_review",
        "next_step",
        "outcome",
        "priority",
        "progress",
        "purpose",
        "rationale",
        "response_strategy",
        "review_date",
        "role",
        "score",
        "start_date",
        "starts_at",
        "summary",
        "target",
        "team",
        "timeframe",
        "unit",
    }
)
_MAX_TEXT_LENGTH = 1200
_MAX_FIELD_TEXT_LENGTH = 800
_MAX_RELATIONS_PER_ENTITY = 20
_MAX_ACTION_PARAMETERS = 24
_MAX_ACTION_TARGET_TYPES = 12
_TERMINAL_MANAGEMENT_STATUSES = frozenset({"done", "archived", "closed", "cancelled"})
_TERMINAL_ACTION_STATUSES = frozenset({"done", "completed", "cancelled", "closed"})
_TERMINAL_RISK_STATUSES = frozenset({"accepted", "closed", "resolved", "retired"})
_ACCEPTED_COMMITMENT_STATES = frozenset(
    {"accepted", "confirmed", "executed", "rejected", "superseded"}
)
_EVIDENCE_TYPES = frozenset({"document", "feedback", "learning", "meeting"})
_SAFE_PACKAGE_MUTATION_CODES = frozenset(
    {
        "ok",
        "persistence_failure",
        "not_authorized",
        "actor_is_not_executor",
        "not_found",
        "revision_conflict",
        "idempotency_conflict",
        "rule_violation",
        "invalid_parameters",
        "evidence_source_conflict",
        "evidence_required",
        "executor_inactive",
        "commitment_already_accepted",
        "measurement_in_future",
        "measurement_out_of_order",
    }
)


@dataclass(frozen=True, slots=True)
class RadarService:
    """Own trusted identity and an already validated RADAR runtime.

    The service owns the trusted context and projects every package result
    before it reaches a tool.  It deliberately exposes no mutation method in
    this phase and never returns package objects, paths, frontmatter history or
    an unconstrained ABox dictionary to the model.
    """

    runtime: RadarVaultRuntime
    context: str
    person_id: str = ""
    telegram_user_id: int = 0
    write_operations: frozenset[str] = frozenset()
    manager_contexts: frozenset[str] = frozenset()

    @property
    def preflight_report(self) -> RadarPreflightReport:
        """Project the safe fields allowed in health and startup telemetry."""

        return RadarPreflightReport(
            state=self.runtime.state,
            context=self.context,
            package_version=self.runtime.package_version,
            tbox_version=self.runtime.tbox_version,
            abox_schema_version=self.runtime.abox_schema_version,
            entity_count=self.runtime.entity_count,
            validation_error_count=self.runtime.validation_error_count,
            error_code=self.runtime.error_code,
        )

    @property
    def write_ready(self) -> bool:
        """Whether at least one configured write has a compatible package contract."""

        return any(self.supports_write_operation(name) for name in self.write_operations)

    def supports_write_operation(self, operation: str) -> bool:
        """Fail closed unless the installed operation exposes every host-owned field."""

        prepare = getattr(self.runtime.operation_runtime, "prepare", None)
        definitions = getattr(self.runtime.operation_runtime, "definitions", None)
        if not callable(prepare) or not isinstance(definitions, dict):
            return False
        definition = definitions.get(operation)
        if not isinstance(definition, dict) or operation not in self.write_operations:
            return False
        parameters = definition.get("parameters")
        target_types = definition.get("target_types")
        if not isinstance(parameters, dict) or not isinstance(target_types, list):
            return False
        required_contract = {
            "capture_issue": {
                "title",
                "case_title",
                "evidence_title",
                "source",
                "priority",
                "owner_id",
            },
            "delegate": {"executor_id", "due_at", "next_review_at"},
            "review": {"assessment", "evidence_id", "next_review_at", "disposition"},
            "record_measurement": {
                "value",
                "measured_at",
                "evidence_id",
                "evidence_title",
                "evidence_source",
                "evidence_text",
            },
        }.get(operation)
        if required_contract is None or not required_contract.issubset(parameters):
            return False
        return operation != "record_measurement" or "indicator" in target_types

    def close(self) -> None:
        """Release integration resources owned by this service."""

        self.runtime.close()

    def search_entities(
        self,
        *,
        query: str | None,
        entity_type: str | None,
        status: str | None,
        limit: int,
        page: int,
    ) -> RadarSearchResult:
        """Return one bounded summary page from the configured context only."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_RADAR_RESULT_LIMIT
            or isinstance(page, bool)
            or not isinstance(page, int)
            or not 1 <= page <= MAX_RADAR_SEARCH_PAGES
        ):
            raise RadarQueryError("invalid_request")
        # Request one sentinel after this page. The package caps searches at
        # 100; the host limits keep this request at 81 or less.
        end = page * limit

        raw = self._observe(
            "search_entities",
            query=query or "",
            entity_type=entity_type,
            status=status,
            limit=end + 1,
            context=self.context,
        )
        if not isinstance(raw, list):
            raise RadarQueryError("invalid_response")
        if query:
            # ``radar-vault`` 0.3.0 performs a case-insensitive literal
            # search.  Human references should not fail merely because a
            # person omitted an accent, so merge title/id matches from one
            # authorized bounded scan.  The public AgentTools boundary still
            # owns context filtering and query audit; the host never opens the
            # vault or reconstructs package authorization rules.
            authorized = self._observe(
                "search_entities",
                query="",
                entity_type=entity_type,
                status=status,
                limit=100,
                context=self.context,
            )
            if not isinstance(authorized, list):
                raise RadarQueryError("invalid_response")
            raw = _merge_human_search_matches(raw, authorized, query=query)
        start = end - limit
        return RadarSearchResult(
            page=page,
            entities=[_project_summary(item) for item in raw[start:end]],
            has_more=len(raw) > end,
        )

    def resolve_entities(
        self,
        *,
        references: list[RadarBatchReferenceInput],
    ) -> RadarEntityResolutionResult:
        """Resolve several independent references without choosing one for the caller.

        A batch is intentionally a read-only convenience.  Each group retains
        all bounded candidates so a later mutation still needs the normal,
        explicit read/selection path enforced by the tool middleware.
        """

        if not 1 <= len(references) <= MAX_RADAR_BATCH_REFERENCES or not all(
            isinstance(reference, RadarBatchReferenceInput) for reference in references
        ):
            raise RadarQueryError("invalid_request")
        return RadarEntityResolutionResult(
            resolutions=[
                RadarBatchResolution(
                    reference_index=index,
                    entities=(
                        result := self.search_entities(
                            query=reference.query,
                            entity_type=reference.entity_type,
                            status=reference.status,
                            limit=reference.limit,
                            page=1,
                        )
                    ).entities,
                    has_more=result.has_more,
                )
                for index, reference in enumerate(references)
            ]
        )

    def read_entity(self, *, entity_id: str) -> RadarEntity:
        """Read one authorized entity with a stable, bounded detail view."""

        raw = self._observe("read_entity", entity_id, context=self.context)
        return _project_entity(raw)

    def get_context(self, *, entity_id: str, depth: int) -> RadarContextResult:
        """Read a small authorized relationship neighbourhood."""

        return _project_context(
            self._context_graph(entity_id=entity_id, depth=depth),
            depth=depth,
        )

    def risk_report(self, *, subject_id: str, limit: int) -> RadarRiskReport:
        """Assemble risks for one objective/project and their mitigating actions."""

        _require_composite_limit(limit)
        raw = self._context_graph(entity_id=subject_id, depth=2)
        entities, edges = _raw_graph_parts(raw)
        projected = {_raw_entity_id(item): _project_entity(item) for item in entities}
        subject = projected.get(subject_id)
        if subject is None:
            raise RadarQueryError("invalid_response")
        if subject.type not in {"objective", "project"}:
            raise RadarQueryError("invalid_request")

        risk_ids: set[str] = set()
        for edge in edges:
            relation = _project_relation(edge, include_source=True)
            source = projected.get(relation.source_id or "")
            target = projected.get(relation.target_id)
            if (
                relation.type == "threatens"
                and relation.target_id == subject_id
                and source is not None
                and source.type == "risk"
            ):
                risk_ids.add(source.id)
            elif (
                relation.type == "contains"
                and relation.source_id == subject_id
                and target is not None
                and target.type == "risk"
            ):
                risk_ids.add(target.id)

        ordered_risks = sorted(
            (projected[risk_id] for risk_id in risk_ids),
            key=lambda item: (-_numeric_field(item, "score"), item.title.casefold(), item.id),
        )
        items: list[RadarRiskItem] = []
        for risk in ordered_risks[:limit]:
            actions = sorted(
                (
                    projected[relation.source_id]
                    for edge in edges
                    if (relation := _project_relation(edge, include_source=True)).type
                    == "mitigates"
                    and relation.target_id == risk.id
                    and relation.source_id in projected
                    and projected[relation.source_id].type == "action"
                ),
                key=lambda item: (item.title.casefold(), item.id),
            )
            items.append(
                RadarRiskItem(
                    risk=risk,
                    mitigating_actions=[_summary(item) for item in actions[:limit]],
                )
            )
        return RadarRiskReport(
            subject=_summary(subject),
            risks=items,
            truncated=_graph_is_truncated(entities, edges) or len(ordered_risks) > limit,
        )

    def action_attention(
        self,
        *,
        as_of: date | None,
        limit: int,
    ) -> RadarActionAttentionReport:
        """Calculate non-terminal actions whose due date or review date has arrived."""

        _require_composite_limit(limit)
        selected_date = as_of or current_local_date()
        raw_summaries = self._observe(
            "search_entities",
            query="",
            entity_type="action",
            status=None,
            limit=100,
            context=self.context,
        )
        if not isinstance(raw_summaries, list):
            raise RadarQueryError("invalid_response")

        attention: list[RadarActionAttentionItem] = []
        for raw_summary in raw_summaries:
            entity_id = _project_summary(raw_summary).id
            raw_entity = self._observe("read_entity", entity_id, context=self.context)
            metadata = _raw_metadata(raw_entity)
            entity = _project_entity(raw_entity)
            if entity.status in {"done", "cancelled"}:
                continue
            due_date = _optional_date(metadata.get("due_date"))
            next_review_at = _assignment_value(metadata, "next_review_at")
            review_date = _optional_timestamp_date(next_review_at)
            reasons = []
            if due_date is not None and due_date < selected_date:
                reasons.append("overdue")
            if review_date is not None and review_date <= selected_date:
                reasons.append("review_due")
            if reasons:
                attention.append(
                    RadarActionAttentionItem(
                        action=entity,
                        reasons=reasons,
                        due_date=due_date,
                        next_review_at=_optional_timestamp(next_review_at),
                    )
                )

        attention.sort(key=_attention_sort_key)
        return RadarActionAttentionReport(
            as_of=selected_date,
            actions=attention[:limit],
            scanned_count=len(raw_summaries),
            truncated=len(raw_summaries) == 100 or len(attention) > limit,
        )

    def decision_evidence(
        self,
        *,
        subject_id: str,
        limit: int,
    ) -> RadarDecisionEvidenceReport:
        """Assemble decisions directly related to a record and their evidence."""

        _require_composite_limit(limit)
        raw = self._context_graph(entity_id=subject_id, depth=2)
        entities, edges = _raw_graph_parts(raw)
        projected = {_raw_entity_id(item): _project_entity(item) for item in entities}
        subject = projected.get(subject_id)
        if subject is None:
            raise RadarQueryError("invalid_response")

        decision_ids = {subject_id} if subject.type == "decision" else set()
        projected_edges = [_project_relation(edge, include_source=True) for edge in edges]
        for relation in projected_edges:
            source = projected.get(relation.source_id or "")
            target = projected.get(relation.target_id)
            if (
                relation.source_id == subject_id
                and target is not None
                and target.type == "decision"
            ):
                decision_ids.add(target.id)
            if (
                relation.target_id == subject_id
                and source is not None
                and source.type == "decision"
            ):
                decision_ids.add(source.id)

        evidence_types = {"document", "feedback", "indicator", "meeting", "learning"}
        evidence_ids: set[str] = set()
        for relation in projected_edges:
            source = projected.get(relation.source_id or "")
            target = projected.get(relation.target_id)
            if (
                relation.source_id in decision_ids
                and target is not None
                and target.type in evidence_types
            ):
                evidence_ids.add(target.id)
            if (
                relation.target_id in decision_ids
                and source is not None
                and source.type in evidence_types
            ):
                evidence_ids.add(source.id)

        decisions = sorted(
            (projected[item] for item in decision_ids),
            key=lambda item: (item.title.casefold(), item.id),
        )
        evidence = sorted(
            (projected[item] for item in evidence_ids),
            key=lambda item: (item.type, item.title.casefold(), item.id),
        )
        kept_ids = {subject_id}
        kept_ids.update(item.id for item in decisions[:limit])
        kept_ids.update(item.id for item in evidence[:limit])
        relations = [
            item
            for item in projected_edges
            if item.source_id in kept_ids and item.target_id in kept_ids
        ][:MAX_RADAR_CONTEXT_RELATIONS]
        return RadarDecisionEvidenceReport(
            subject=_summary(subject),
            decisions=decisions[:limit],
            evidence=evidence[:limit],
            relations=relations,
            truncated=(
                _graph_is_truncated(entities, edges)
                or len(decisions) > limit
                or len(evidence) > limit
            ),
        )

    def person_commitments(
        self,
        *,
        person_id: str,
        include_superseded: bool,
        limit: int,
    ) -> RadarPersonCommitmentsReport:
        """Assemble commitments whose accepted terms name one person."""

        _require_composite_limit(limit)
        raw = self._context_graph(entity_id=person_id, depth=2)
        entities, edges = _raw_graph_parts(raw)
        raw_by_id = {_raw_entity_id(item): item for item in entities}
        projected = {entity_id: _project_entity(item) for entity_id, item in raw_by_id.items()}
        person = projected.get(person_id)
        if person is None:
            raise RadarQueryError("invalid_response")
        if person.type != "person":
            raise RadarQueryError("invalid_request")

        assigned_actions = {
            relation.source_id
            for edge in edges
            if (relation := _project_relation(edge, include_source=True)).type == "assigned_to"
            and relation.target_id == person_id
            and relation.source_id in projected
            and projected[relation.source_id].type == "action"
        }
        items: list[RadarCommitmentItem] = []
        for edge in edges:
            relation = _project_relation(edge, include_source=True)
            if relation.type != "commits_to" or relation.target_id not in assigned_actions:
                continue
            commitment = projected.get(relation.source_id or "")
            action = projected.get(relation.target_id)
            raw_commitment = raw_by_id.get(relation.source_id or "")
            if commitment is None or action is None or raw_commitment is None:
                raise RadarQueryError("invalid_response")
            if commitment.type != "commitment" or action.type != "action":
                continue
            if commitment.status == "superseded" and not include_superseded:
                continue
            terms = _operation_terms(_raw_metadata(raw_commitment))
            executors = terms.get("executor_ids")
            executor = terms.get("executor_id")
            if (
                (executor is not None or executors is not None)
                and executor != person_id
                and not (isinstance(executors, list) and person_id in executors)
            ):
                continue
            items.append(
                RadarCommitmentItem(
                    commitment=_summary(commitment),
                    action=action,
                    state=_optional_filter(terms.get("state")),
                    due_at=_optional_timestamp(terms.get("due_at")),
                    next_review_at=_optional_timestamp(terms.get("next_review_at")),
                )
            )

        items.sort(
            key=lambda item: (
                item.next_review_at or "9999",
                item.due_at or "9999",
                item.action.title.casefold(),
            )
        )
        return RadarPersonCommitmentsReport(
            person=_summary(person),
            commitments=items[:limit],
            truncated=_graph_is_truncated(entities, edges) or len(items) > limit,
        )

    def management_context(self, *, entity_id: str) -> RadarContextResult:
        """Return a bounded two-hop context for one meeting or case."""

        raw = self._context_graph(entity_id=entity_id, depth=2)
        projected = _project_context(raw, depth=2)
        root = next((item for item in projected.entities if item.id == entity_id), None)
        if root is None:
            raise RadarQueryError("invalid_response")
        if root.type not in {"meeting", "case"}:
            raise RadarQueryError("invalid_request")
        return projected

    def operational_brief(self, *, entity_id: str, limit: int) -> RadarOperationalBrief:
        """Project one bounded operational view from a single authorized graph read."""

        _require_operational_brief_limit(limit)
        raw = self._context_graph(entity_id=entity_id, depth=3)
        entities, edges = _raw_graph_parts(raw)
        raw_by_id = {_raw_entity_id(item): item for item in entities}
        projected = {entity_id: _project_entity(item) for entity_id, item in raw_by_id.items()}
        subject = projected.get(entity_id)
        if subject is None:
            raise RadarQueryError("invalid_response")
        if subject.type not in {"routine", "project", "objective", "case"}:
            raise RadarQueryError("invalid_request")

        relations = [_project_relation(edge, include_source=True) for edge in edges]
        management_items = _sorted_entities(
            item
            for item in projected.values()
            if item.type == "management_item" and item.status not in _TERMINAL_MANAGEMENT_STATUSES
        )
        decisions = _sorted_entities(
            item
            for item in projected.values()
            if item.type == "decision" and item.status != "superseded"
        )
        superseded_decisions = _sorted_entities(
            item
            for item in projected.values()
            if item.type == "decision" and item.status == "superseded"
        )
        risks = sorted(
            (
                item
                for item in projected.values()
                if item.type == "risk" and item.status not in _TERMINAL_RISK_STATUSES
            ),
            key=lambda item: (-_numeric_field(item, "score"), item.title.casefold(), item.id),
        )
        open_actions = _sorted_entities(
            item
            for item in projected.values()
            if item.type == "action" and item.status not in _TERMINAL_ACTION_STATUSES
        )
        action_items = [
            _operational_action(
                action=action,
                raw_action=raw_by_id[action.id],
                relations=relations,
                projected=projected,
            )
            for action in open_actions
        ]
        commitments = _operational_commitments(
            raw_by_id=raw_by_id,
            projected=projected,
            relations=relations,
        )
        indicators = _sorted_entities(
            item
            for item in projected.values()
            if item.type == "indicator" and item.status == "active"
        )
        evidence = _operational_evidence(
            decisions=decisions,
            actions=open_actions,
            relations=relations,
            projected=projected,
        )

        sections = (
            management_items,
            decisions,
            superseded_decisions,
            risks,
            action_items,
            commitments,
            indicators,
            evidence,
        )
        return RadarOperationalBrief(
            subject=_summary(subject),
            management_items=management_items[:limit],
            decisions=decisions[:limit],
            superseded_decisions=superseded_decisions[:limit],
            risks=risks[:limit],
            actions=action_items[:limit],
            commitments=commitments[:limit],
            indicators=indicators[:limit],
            evidence=evidence[:limit],
            scanned_count=len(projected),
            truncated=_graph_is_truncated(entities, edges)
            or any(len(section) > limit for section in sections),
        )

    def list_action_types(self) -> tuple[RadarActionType, ...]:
        """Describe installed action types without exposing executable payloads."""

        raw = self._observe("list_action_types")
        if not isinstance(raw, dict):
            raise RadarQueryError("invalid_response")
        projected: list[RadarActionType] = []
        for name, definition in sorted(raw.items())[:MAX_RADAR_ACTION_TYPES]:
            projected.append(_project_action_type(name, definition))
        return tuple(projected)

    def validate_context(self) -> RadarValidationResult:
        """Return only scoped diagnostic codes, never validator prose or paths."""

        raw = self._observe("validate_vault", context=self.context)
        if not isinstance(raw, dict):
            raise RadarQueryError("invalid_response")
        raw_issues = raw.get("issues")
        if not isinstance(raw_issues, list):
            raise RadarQueryError("invalid_response")
        return RadarValidationResult(
            valid=_bool(raw.get("valid")),
            error_count=_count(raw.get("error_count")),
            warning_count=_count(raw.get("warning_count")),
            finding_count=_count(raw.get("finding_count")),
            issues=[
                _project_validation_issue(item) for item in raw_issues[:MAX_RADAR_VALIDATION_ISSUES]
            ],
            truncated=len(raw_issues) > MAX_RADAR_VALIDATION_ISSUES,
        )

    def prepare_operation(
        self,
        *,
        operation: str,
        parameters: dict[str, object],
        target_id: str | None,
    ) -> dict[str, object]:
        """Validate a configured pilot operation and return its immutable payload.

        This is deliberately not an executor.  It rebuilds the host-owned
        principal with the small write allowlist, invokes the package's public
        no-effect preparation API, and returns only the normalized data the
        application may durably propose to the authenticated human.
        """

        self._ensure_integrity()
        if operation not in self.write_operations:
            raise RadarQueryError("operation_not_exposed")
        if not self.supports_write_operation(operation):
            raise RadarQueryError("write_package_incompatible")
        tools = self._write_agent_tools()
        try:
            prepared = tools.prepare_operation(
                operation,
                parameters,
                context=self.context,
                target_id=target_id,
            )
        except Exception as exc:  # noqa: BLE001 - package diagnostics may expose ABox data
            raise _mutation_error(exc) from None
        normalized_operation = _mutation_operation(prepared.get("operation"))
        normalized_target = _mutation_target(prepared.get("target_id"))
        normalized_parameters = _mutation_parameters(prepared.get("parameters"))
        return {
            "operation": normalized_operation,
            "context": self.context,
            "target_id": normalized_target,
            "expected_revision": _mutation_revision(prepared.get("expected_revision")),
            "parameters": normalized_parameters,
            **(
                {"execution_context": prepared["execution_context"]}
                if prepared.get("execution_context")
                else {}
            ),
            # This is a display-only snapshot.  Execution ignores it and
            # consumes only the canonical fields above, while Telegram can
            # ask an informed question without exposing ids or revisions.
            "presentation": self._operation_presentation(
                operation=normalized_operation,
                target_id=normalized_target,
                parameters=normalized_parameters,
            ),
        }

    def _operation_presentation(
        self,
        *,
        operation: str,
        target_id: str | None,
        parameters: dict[str, object],
    ) -> dict[str, object]:
        """Resolve authorized human names for an immutable proposal snapshot."""

        presentation: dict[str, object] = {"version": 2, "operation": operation}
        if operation == "capture_issue":
            for name in ("title", "case_title", "evidence_title", "priority"):
                value = parameters.get(name)
                if isinstance(value, str):
                    presentation[name] = value
            owner_id = parameters.get("owner_id")
            if isinstance(owner_id, str):
                presentation["owner"] = self._display_reference(owner_id)
            return presentation

        if target_id is not None:
            presentation["target"] = self._display_reference(target_id)
        if operation == "delegate":
            executor_id = parameters.get("executor_id")
            if isinstance(executor_id, str):
                presentation["executor"] = self._display_reference(executor_id)
            for name in ("due_at", "next_review_at"):
                value = parameters.get(name)
                if isinstance(value, str):
                    presentation[name] = value
        elif operation == "review":
            evidence_id = parameters.get("evidence_id")
            if isinstance(evidence_id, str):
                presentation["evidence"] = self._display_reference(evidence_id)
            for name in ("assessment", "next_review_at", "disposition"):
                value = parameters.get(name)
                if isinstance(value, str):
                    presentation[name] = value
        elif operation == "record_measurement" and target_id is not None:
            indicator = _project_entity(
                self._observe("read_entity", target_id, context=self.context)
            )
            presentation["indicator"] = {
                "title": indicator.title,
                "type": indicator.type,
                "status": indicator.status,
                **{
                    name: indicator.fields[name]
                    for name in (
                        "baseline",
                        "current",
                        "target",
                        "formula",
                        "cadence",
                        "unit",
                        "direction",
                    )
                    if name in indicator.fields
                },
            }
            for name in ("value", "measured_at", "evidence_title"):
                value = parameters.get(name)
                if isinstance(value, str | int | float) and not isinstance(value, bool):
                    presentation[name] = value
        return presentation

    def _display_reference(self, entity_id: str) -> dict[str, str]:
        """Return a minimal authorized label with no canonical identifier."""

        entity = _project_entity(self._observe("read_entity", entity_id, context=self.context))
        return {"title": entity.title, "type": entity.type, "status": entity.status}

    def execute_saved_operation(
        self,
        *,
        operation: str,
        target_id: str | None,
        expected_revision: int,
        parameters: dict[str, object],
        idempotency_key: str,
        execution_context: dict[str, object] | None = None,
        approval_source: dict[str, object] | None = None,
        approve: bool = True,
    ) -> dict[str, object]:
        """Execute exactly one stored proposal after current reauthorization."""

        if (getattr(self.runtime, "backend", None) == "command-layer") != (
            execution_context is not None
        ):
            return _safe_mutation_result("rejected", "write_package_incompatible")
        try:
            self._ensure_integrity()
        except RadarQueryError as exc:
            return _safe_mutation_result("rejected", exc.code)
        if operation not in self.write_operations:
            return _safe_mutation_result("rejected", "operation_not_exposed")
        if not self.supports_write_operation(operation):
            return _safe_mutation_result("rejected", "write_package_incompatible")
        tools = self._write_agent_tools()
        try:
            raw = tools.execute_operation(
                operation,
                context=self.context,
                target_id=target_id,
                expected_revision=expected_revision,
                parameters=parameters,
                idempotency_key=idempotency_key,
                **(
                    {
                        "execution_context": execution_context,
                        "approval_source": approval_source,
                        "approve": approve,
                    }
                    if getattr(self.runtime, "backend", None) == "command-layer"
                    else {}
                ),
            )
        except RadarQueryError as exc:
            return _safe_mutation_result(
                "failed"
                if exc.code == "persistence_failure"
                else "conflict"
                if exc.code in {"revision_conflict", "idempotency_conflict", "approval_stale"}
                else "rejected",
                exc.code,
            )
        except Exception as exc:  # noqa: BLE001 - no raw package message crosses to Telegram/audit
            error = _mutation_error(exc)
            return _safe_mutation_result("rejected", error.code)
        if not isinstance(raw, dict):
            return _safe_mutation_result("failed", "invalid_response")
        projected = _safe_result_projection(raw)
        if (
            getattr(self.runtime, "backend", None) == "command-layer"
            and projected["code"] == "invalid_response"
        ):
            return _safe_mutation_result("failed", "persistence_failure")
        return projected

    def _write_agent_tools(self) -> object:
        """Build a fresh non-agent principal for each prepare/approval step."""

        if getattr(self.runtime, "backend", None) == "command-layer":
            return self.runtime
        principal = build_principal(
            telegram_user_id=self.telegram_user_id,
            person_id=self.person_id,
            context=self.context,
            grants=self.write_operations,
            manager_contexts=self.manager_contexts,
            is_agent=False,
        )
        tools_type = type(self.runtime.agent_tools)
        return tools_type(self.runtime.vault, principal, self.context)

    def _context_graph(self, *, entity_id: str, depth: int) -> dict[str, Any]:
        raw = self._observe(
            "get_entity_context",
            entity_id,
            depth=depth,
            context=self.context,
        )
        if not isinstance(raw, dict):
            raise RadarQueryError("invalid_response")
        return raw

    def _observe(self, method: str, /, *args: Any, **kwargs: Any) -> Any:
        """Call the package boundary without allowing its exception text through."""

        self._ensure_integrity()
        operation = getattr(self.runtime.agent_tools, method, None)
        if not callable(operation):
            raise RadarQueryError("package_contract_invalid")
        try:
            return operation(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - package messages may contain ABox content
            # The library has a distinct authorization exception, but importing
            # it here would unnecessarily tie the host to its private error
            # hierarchy.  Its stable public class name is enough to select a
            # safe response without serializing the exception.
            if type(exc).__name__ == "AuthorizationError":
                raise RadarQueryError("entity_unavailable") from None
            if isinstance(exc, ValueError):
                raise RadarQueryError("invalid_request") from None
            raise RadarQueryError("query_failed") from None

    def _ensure_integrity(self) -> None:
        """Translate a changed invalid generation into one safe host code."""

        try:
            self.runtime.ensure_current()
        except RadarQueryError:
            if getattr(self.runtime, "backend", None) == "command-layer":
                raise
            raise RadarQueryError("vault_changed_invalid") from None
        except Exception:  # noqa: BLE001 - the adapter already discarded private diagnostics
            raise RadarQueryError("vault_changed_invalid") from None


def _mutation_error(exc: Exception) -> RadarQueryError:
    """Classify package preparation failures without retaining their prose."""

    if isinstance(exc, RadarQueryError):
        return exc
    if type(exc).__name__ == "AuthorizationError":
        return RadarQueryError(_safe_package_mutation_code(exc, fallback="not_authorized"))
    if isinstance(exc, ValueError):
        return RadarQueryError("invalid_request")
    if type(exc).__name__ in {"ConflictError"}:
        return RadarQueryError("revision_conflict")
    if type(exc).__name__ == "OperationRejected":
        return RadarQueryError(_safe_package_mutation_code(exc, fallback="rule_violation"))
    if type(exc).__name__ == "RadarVaultError":
        return RadarQueryError("rule_violation")
    return RadarQueryError("mutation_failed")


def _safe_package_mutation_code(exc: Exception, *, fallback: str) -> str:
    """Accept only the enumerated code attribute, never package exception prose."""

    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code in _SAFE_PACKAGE_MUTATION_CODES else fallback


def _mutation_operation(value: object) -> str:
    if not isinstance(value, str) or value not in {
        "capture_issue",
        "delegate",
        "review",
        "record_measurement",
    }:
        raise RadarQueryError("invalid_response")
    return value


def _mutation_target(value: object) -> str | None:
    return None if value is None else _entity_id(value)


def _mutation_revision(value: object) -> int:
    return _count(value)


def _mutation_parameters(value: object) -> dict[str, object]:
    """Keep the exact bounded, JSON-shaped business payload for later execution."""

    if not isinstance(value, dict):
        raise RadarQueryError("invalid_response")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _FILTER.fullmatch(key):
            raise RadarQueryError("invalid_response")
        if isinstance(item, str):
            if not item or len(item) > _MAX_TEXT_LENGTH:
                raise RadarQueryError("invalid_response")
            normalized[key] = item
        elif isinstance(item, bool) or isinstance(item, int | float) and math.isfinite(float(item)):
            normalized[key] = item
        elif isinstance(item, list) and all(
            isinstance(element, str) and len(element) <= 80 for element in item
        ):
            normalized[key] = list(item)
        else:
            raise RadarQueryError("invalid_response")
    return normalized


def _safe_mutation_result(status: str, code: str) -> dict[str, object]:
    return {
        "status": status,
        "code": code,
        "target_id": None,
        "revision": None,
        "created_ids": [],
        "operation_id": None,
    }


def _safe_result_projection(raw: dict[str, object]) -> dict[str, object]:
    """Persist only ids/revisions/codes; package prose never becomes application state."""

    status = raw.get("status")
    code = raw.get("code")
    if (
        status not in {"executed", "rejected", "conflict", "failed"}
        or not isinstance(code, str)
        or code not in _SAFE_PACKAGE_MUTATION_CODES
    ):
        return _safe_mutation_result("failed", "invalid_response")
    created = raw.get("created_ids")
    if not isinstance(created, list) or not all(
        isinstance(item, str) and _ENTITY_ID.fullmatch(item) for item in created
    ):
        return _safe_mutation_result("failed", "invalid_response")
    target_id = raw.get("target_id")
    revision = raw.get("revision")
    operation_id = raw.get("operation_id")
    return {
        "status": status,
        "code": code[:80],
        "target_id": target_id
        if isinstance(target_id, str) and _ENTITY_ID.fullmatch(target_id)
        else None,
        "revision": revision if type(revision) is int and revision >= 0 else None,
        "created_ids": list(created),
        "operation_id": operation_id
        if isinstance(operation_id, str) and len(operation_id) <= 64
        else None,
    }


def create_radar_service(
    *,
    vault_path: str,
    context: str,
    person_id: str,
    telegram_user_id: int,
    allowed_tbox_versions: frozenset[str],
    write_operations: frozenset[str] = frozenset(),
    manager_contexts: frozenset[str] = frozenset(),
) -> RadarService:
    """Build RADAR using only trusted configuration supplied by the host."""

    principal = build_principal(
        telegram_user_id=telegram_user_id,
        person_id=person_id,
        context=context,
    )
    runtime = open_radar_vault(
        vault_path=vault_path,
        context=context,
        principal=principal,
        allowed_tbox_versions=allowed_tbox_versions,
    )
    return RadarService(
        runtime=runtime,
        context=context,
        person_id=person_id,
        telegram_user_id=telegram_user_id,
        write_operations=write_operations,
        manager_contexts=manager_contexts,
    )


def _project_summary(raw: object) -> RadarEntitySummary:
    if not isinstance(raw, dict):
        raise RadarQueryError("invalid_response")
    return RadarEntitySummary(
        id=_entity_id(raw.get("id")),
        type=_filter(raw.get("type")),
        title=_text(raw.get("title"), maximum=240),
        status=_filter(raw.get("status")),
        revision=_count(raw.get("revision")),
    )


def _merge_human_search_matches(
    literal_matches: list[object],
    authorized: list[object],
    *,
    query: str,
) -> list[object]:
    """Add accent-insensitive title/id matches without weakening authorization."""

    needle = _human_search_key(query)
    merged = list(literal_matches)
    known_ids = {_project_summary(item).id for item in literal_matches}
    for item in authorized:
        summary = _project_summary(item)
        if summary.id in known_ids:
            continue
        haystack = _human_search_key(f"{summary.title} {summary.id}")
        if needle in haystack:
            merged.append(item)
            known_ids.add(summary.id)
    return merged


def _human_search_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def _project_entity(raw: object) -> RadarEntity:
    if not isinstance(raw, dict):
        raise RadarQueryError("invalid_response")
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        raise RadarQueryError("invalid_response")
    relations = metadata.get("relations", [])
    if not isinstance(relations, list):
        raise RadarQueryError("invalid_response")
    return RadarEntity(
        id=_entity_id(metadata.get("id")),
        type=_filter(metadata.get("type")),
        title=_text(metadata.get("title"), maximum=240),
        status=_filter(metadata.get("status")),
        revision=_count(metadata.get("revision")),
        fields={
            name: value
            for name in sorted(_VISIBLE_FIELDS & metadata.keys())
            if (value := _field_value(metadata[name])) is not None
        },
        relations=[_project_relation(item) for item in relations[:_MAX_RELATIONS_PER_ENTITY]],
        body=_optional_text(raw.get("body"), maximum=_MAX_TEXT_LENGTH),
    )


def _project_context(raw: object, *, depth: int) -> RadarContextResult:
    if not isinstance(raw, dict):
        raise RadarQueryError("invalid_response")
    root_id = _entity_id(raw.get("root_id"))
    raw_entities, raw_relations = _raw_graph_parts(raw)
    projected = [_project_entity(item) for item in raw_entities]
    projected.sort(key=lambda item: (item.id != root_id, item.type, item.title.casefold(), item.id))
    entities = projected[:MAX_RADAR_CONTEXT_ENTITIES]
    selected_ids = {item.id for item in entities}
    all_relations = [_project_relation(item, include_source=True) for item in raw_relations]
    visible_relations = [
        item
        for item in all_relations
        if item.source_id in selected_ids and item.target_id in selected_ids
    ]
    return RadarContextResult(
        root_id=root_id,
        depth=depth,
        entities=entities,
        relations=visible_relations[:MAX_RADAR_CONTEXT_RELATIONS],
        truncated=(
            len(projected) > MAX_RADAR_CONTEXT_ENTITIES
            or len(visible_relations) > MAX_RADAR_CONTEXT_RELATIONS
            or len(visible_relations) < len(all_relations)
        ),
    )


def _raw_graph_parts(raw: dict[str, Any]) -> tuple[list[object], list[object]]:
    raw_entities = raw.get("entities")
    raw_relations = raw.get("edges")
    if not isinstance(raw_entities, list) or not isinstance(raw_relations, list):
        raise RadarQueryError("invalid_response")
    return raw_entities, raw_relations


def _raw_metadata(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("metadata"), dict):
        raise RadarQueryError("invalid_response")
    return raw["metadata"]


def _raw_entity_id(raw: object) -> str:
    return _entity_id(_raw_metadata(raw).get("id"))


def _summary(entity: RadarEntity) -> RadarEntitySummary:
    return RadarEntitySummary(
        id=entity.id,
        type=entity.type,
        title=entity.title,
        status=entity.status,
        revision=entity.revision,
    )


def _numeric_field(entity: RadarEntity, name: str) -> float:
    value = entity.fields.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return float(value)


def _graph_is_truncated(entities: list[object], relations: list[object]) -> bool:
    return (
        len(entities) > MAX_RADAR_CONTEXT_ENTITIES or len(relations) > MAX_RADAR_CONTEXT_RELATIONS
    )


def _require_composite_limit(limit: int) -> None:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_RADAR_COMPOSITE_ITEMS
    ):
        raise RadarQueryError("invalid_request")


def _require_operational_brief_limit(limit: int) -> None:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_RADAR_OPERATIONAL_BRIEF_ITEMS
    ):
        raise RadarQueryError("invalid_request")


def _sorted_entities(entities: Iterable[RadarEntity]) -> list[RadarEntity]:
    """Keep briefing sections deterministic regardless of vault traversal order."""

    return sorted(entities, key=lambda item: (item.title.casefold(), item.id))


def _operational_action(
    *,
    action: RadarEntity,
    raw_action: object,
    relations: list[RadarRelation],
    projected: dict[str, RadarEntity],
) -> RadarOperationalAction:
    owner_ids = {
        relation.target_id
        for relation in relations
        if relation.source_id == action.id
        and relation.type in {"assigned_to", "owned_by"}
        and projected.get(relation.target_id, action).type == "person"
    }
    blocker_ids = {
        relation.target_id
        for relation in relations
        if relation.source_id == action.id
        and relation.type == "depends_on"
        and relation.target_id in projected
    }
    blocker_ids.update(
        relation.source_id
        for relation in relations
        if relation.target_id == action.id
        and relation.type == "blocks"
        and relation.source_id in projected
    )
    metadata = _raw_metadata(raw_action)
    return RadarOperationalAction(
        action=action,
        owners=[_summary(projected[item]) for item in sorted(owner_ids)],
        blockers=[_summary(projected[item]) for item in sorted(blocker_ids)],
        due_at=_brief_due_at(action, metadata),
        next_review_at=_brief_next_review_at(metadata),
    )


def _operational_commitments(
    *,
    raw_by_id: dict[str, object],
    projected: dict[str, RadarEntity],
    relations: list[RadarRelation],
) -> list[RadarOperationalCommitment]:
    action_by_commitment = {
        relation.source_id: relation.target_id
        for relation in relations
        if relation.type == "commits_to"
        and relation.source_id in projected
        and relation.target_id in projected
        and projected[relation.source_id].type == "commitment"
        and projected[relation.target_id].type == "action"
    }
    items: list[RadarOperationalCommitment] = []
    for commitment in projected.values():
        if commitment.type != "commitment":
            continue
        terms = _operation_terms(_raw_metadata(raw_by_id[commitment.id]))
        state = _optional_filter(terms.get("state"))
        if commitment.status != "proposed" and state in _ACCEPTED_COMMITMENT_STATES:
            continue
        action_id = action_by_commitment.get(commitment.id)
        executor_ids = _term_entity_ids(terms)
        items.append(
            RadarOperationalCommitment(
                commitment=commitment,
                action=_summary(projected[action_id]) if action_id is not None else None,
                executors=[
                    _summary(projected[entity_id])
                    for entity_id in executor_ids
                    if entity_id in projected and projected[entity_id].type == "person"
                ],
                state=state,
                due_at=_optional_timestamp(terms.get("due_at")),
                next_review_at=_optional_timestamp(terms.get("next_review_at")),
            )
        )
    return sorted(
        items,
        key=lambda item: (
            item.next_review_at or "9999",
            item.due_at or "9999",
            item.commitment.title.casefold(),
            item.commitment.id,
        ),
    )


def _operational_evidence(
    *,
    decisions: list[RadarEntity],
    actions: list[RadarEntity],
    relations: list[RadarRelation],
    projected: dict[str, RadarEntity],
) -> list[RadarEntitySummary]:
    anchors = {item.id for item in decisions}
    anchors.update(item.id for item in actions)
    evidence_ids = {
        related_id
        for relation in relations
        if relation.source_id in anchors or relation.target_id in anchors
        for related_id in (
            relation.target_id if relation.source_id in anchors else relation.source_id,
        )
        if related_id is not None
        and related_id in projected
        and projected[related_id].type in _EVIDENCE_TYPES
    }
    return [_summary(projected[item]) for item in sorted(evidence_ids)]


def _brief_due_at(action: RadarEntity, metadata: dict[str, Any]) -> str | None:
    assigned_due_at = _assignment_value(metadata, "due_at")
    if assigned_due_at is not None:
        return _optional_timestamp(assigned_due_at)
    due_date = action.fields.get("due_date")
    if due_date is None:
        return None
    if not isinstance(due_date, str):
        raise RadarQueryError("invalid_response")
    return _optional_date(due_date).isoformat()


def _brief_next_review_at(metadata: dict[str, Any]) -> str | None:
    return _optional_timestamp(_assignment_value(metadata, "next_review_at"))


def _term_entity_ids(terms: dict[str, Any]) -> list[str]:
    values: list[object] = []
    executor_id = terms.get("executor_id")
    executor_ids = terms.get("executor_ids")
    if executor_id is not None:
        values.append(executor_id)
    if executor_ids is not None:
        if not isinstance(executor_ids, list) or len(executor_ids) > 12:
            raise RadarQueryError("invalid_response")
        values.extend(executor_ids)
    normalized: list[str] = []
    for value in values:
        entity_id = _entity_id(value)
        if entity_id not in normalized:
            normalized.append(entity_id)
    return normalized


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RadarQueryError("invalid_response")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise RadarQueryError("invalid_response") from None


def _assignment_value(metadata: dict[str, Any], name: str) -> object:
    operation_data = metadata.get("operation_data")
    if operation_data is None:
        return None
    if not isinstance(operation_data, dict):
        raise RadarQueryError("invalid_response")
    assignment = operation_data.get("assignment")
    if assignment is None:
        return None
    if not isinstance(assignment, dict):
        raise RadarQueryError("invalid_response")
    return assignment.get(name)


def _operation_terms(metadata: dict[str, Any]) -> dict[str, Any]:
    operation_data = metadata.get("operation_data")
    if operation_data is None:
        return {}
    if not isinstance(operation_data, dict):
        raise RadarQueryError("invalid_response")
    terms = operation_data.get("terms")
    if terms is None:
        return {}
    if not isinstance(terms, dict):
        raise RadarQueryError("invalid_response")
    return terms


def _optional_filter(value: object) -> str | None:
    return None if value is None else _filter(value)


def _optional_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise RadarQueryError("invalid_response")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise RadarQueryError("invalid_response") from None
    return value


def _optional_timestamp_date(value: object) -> date | None:
    normalized = _optional_timestamp(value)
    if normalized is None:
        return None
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        parsed = parsed.astimezone(application_timezone())
    return parsed.date()


def _attention_sort_key(item: RadarActionAttentionItem) -> tuple[str, str, str]:
    attention_at = item.next_review_at or (item.due_date.isoformat() if item.due_date else "9999")
    return attention_at, item.action.title.casefold(), item.action.id


def _project_relation(raw: object, *, include_source: bool = False) -> RadarRelation:
    if not isinstance(raw, dict):
        raise RadarQueryError("invalid_response")
    raw_target = raw.get("target_id", raw.get("target"))
    target_id = _entity_id_from_reference(raw_target)
    source_id = _entity_id(raw.get("source_id")) if include_source else None
    return RadarRelation(source_id=source_id, type=_filter(raw.get("type")), target_id=target_id)


def _project_action_type(name: object, definition: object) -> RadarActionType:
    if not isinstance(definition, dict):
        raise RadarQueryError("invalid_response")
    parameters = definition.get("parameters", {})
    target_types = definition.get("target_types", [])
    if not isinstance(parameters, dict) or not isinstance(target_types, list):
        raise RadarQueryError("invalid_response")
    return RadarActionType(
        name=_filter(name),
        label=_text(definition.get("label", name), maximum=160),
        target_types=[_symbol(value) for value in target_types[:_MAX_ACTION_TARGET_TYPES]],
        parameters=[
            RadarActionParameter(
                name=_filter(parameter_name),
                type=_symbol(config.get("type")),
                required=_bool(config.get("required", False)),
            )
            for parameter_name, config in sorted(parameters.items())[:_MAX_ACTION_PARAMETERS]
            if isinstance(config, dict)
        ],
    )


def _project_validation_issue(raw: object) -> RadarValidationIssue:
    if not isinstance(raw, dict):
        raise RadarQueryError("invalid_response")
    entity_id = raw.get("entity_id")
    severity = raw.get("severity")
    if severity not in {"error", "warning", "finding"}:
        raise RadarQueryError("invalid_response")
    return RadarValidationIssue(
        entity_id=_entity_id(entity_id) if entity_id is not None else None,
        severity=severity,
        code=_symbol(raw.get("code")),
    )


def _entity_id(value: object) -> str:
    if not isinstance(value, str) or _ENTITY_ID.fullmatch(value) is None:
        raise RadarQueryError("invalid_response")
    return value


def _entity_id_from_reference(value: object) -> str:
    if not isinstance(value, str):
        raise RadarQueryError("invalid_response")
    found = _ENTITY_ID_IN_REFERENCE.search(value)
    if found is None:
        raise RadarQueryError("invalid_response")
    return found.group(0)


def _filter(value: object) -> str:
    if not isinstance(value, str) or _FILTER.fullmatch(value) is None:
        raise RadarQueryError("invalid_response")
    return value


def _symbol(value: object) -> str:
    if not isinstance(value, str) or _SYMBOL.fullmatch(value) is None:
        raise RadarQueryError("invalid_response")
    return value


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise RadarQueryError("invalid_response")
    normalized = " ".join(value.split())
    if not normalized:
        raise RadarQueryError("invalid_response")
    return normalized[:maximum]


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RadarQueryError("invalid_response")
    normalized = " ".join(value.split())
    return normalized[:maximum] or None


def _field_value(value: object) -> str | int | float | bool | list[str] | None:
    if isinstance(value, str):
        return _optional_text(value, maximum=_MAX_FIELD_TEXT_LENGTH)
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if (
        isinstance(value, list)
        and len(value) <= 12
        and all(isinstance(item, str) for item in value)
    ):
        return [_optional_text(item, maximum=200) or "" for item in value]
    return None


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RadarQueryError("invalid_response")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise RadarQueryError("invalid_response")
    return value


__all__ = ["RadarService", "create_radar_service"]
