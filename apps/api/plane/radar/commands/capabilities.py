"""Closed, executable capability registry shared by transports and execution.

Only application code registers capabilities. Workspace metadata cannot register
handlers or weaken the minimum policy. Imports are lazy to keep adapters out of
the domain contracts and to avoid dispatcher/serializer import cycles.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Callable

from rest_framework import serializers
from rest_framework.exceptions import ValidationError


CAPABILITY_FIELD_TYPES = ("uuid", "datetime", "boolean", "integer", "number", "string", "json", "object", "array")


def resolve(path: str) -> Callable:
    module, name = path.rsplit(".", 1)
    return getattr(import_module(f"plane.radar.commands.{module}"), name)


@dataclass(frozen=True)
class CreationProfile:
    """Creation contract an ObjectType may select through rules.creation.capability."""

    types: tuple[str, ...] = ("*",)
    parameters: str | None = None
    property_fields: tuple[str, ...] = ()
    required_properties: tuple[str, ...] = ()
    initial_states: tuple[str, ...] = ()
    effects: str | None = None

    @property
    def parameter_type(self):
        return resolve(f"inputs.{self.parameters}") if self.parameters else None

    def allows(self, type_key: str) -> bool:
        return "*" in self.types or type_key in self.types

    def contract(self):
        return {
            "types": list(self.types),
            "parameters": (
                {key: field_contract(field) for key, field in self.parameter_type().fields.items()}
                if self.parameters
                else {}
            ),
            "property_fields": list(self.property_fields),
            "required_properties": list(self.required_properties),
            "initial_states": list(self.initial_states),
        }


@dataclass(frozen=True)
class TransitionGuard:
    """Executable guard a lifecycle transition may reference; metadata cannot weaken it."""

    name: str
    capability: str
    check: str
    after: str | None = None
    references: str | None = None
    human_only: bool = False
    types: tuple[str, ...] = ("*",)

    def allows(self, type_key: str) -> bool:
        return "*" in self.types or type_key in self.types

    def contract(self):
        return {
            "capability": self.capability,
            "human_only": self.human_only,
            "types": list(self.types),
            "dynamic_references": self.references is not None,
        }


@dataclass(frozen=True)
class Capability:
    name: str
    input_name: str
    handler: str
    object_refs: tuple[str, ...] = ()
    reference_resolver: str | None = None
    human_only: bool = False
    human_policy: str | None = None
    review_policy: str | None = None
    requested_fields: tuple[str, ...] = ()
    composed_capability: str | None = None
    runtime_operation: str | None = None
    target_field: str | None = None
    target_types: tuple[str, ...] = ()
    runtime_required_types: tuple[str, ...] = ()
    source_parameter: str | None = None
    evidence_text_parameter: str | None = None
    transport: str = "command_envelope"
    guard: str | None = None
    planner: str = "effects.plan_handler"
    creation: CreationProfile | None = None
    lifecycle_types: tuple[str, ...] = ()
    transition_parameter: str | None = None
    # Input field that targets the current Object when offered as an Object Page action, and an
    # optional resolver of actor-specific inputs (it raises when the actor cannot perform it).
    object_action: str | None = None
    action_prefill: str | None = None

    def performs_transitions(self, type_key: str) -> bool:
        return "*" in self.lifecycle_types or type_key in self.lifecycle_types

    def action_types(self) -> tuple[str, ...]:
        if self.object_action is None:
            return ()
        return getattr(self.input_type().fields[self.object_action], "object_types", ("*",))

    def transition_choices(self):
        if self.transition_parameter is None:
            return ()
        return tuple(self.input_type().fields[self.transition_parameter].choices)

    @property
    def input_type(self):
        return resolve(f"inputs.{self.input_name}")

    def references(self, workspace, data):
        refs = set()
        for path in self.object_refs:
            value = data
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value is not None:
                refs.update(value if isinstance(value, list) else [value])
        if self.reference_resolver:
            refs.update(resolve(self.reference_resolver)(workspace, self.name, data))
        return refs

    def is_human_only(self, workspace, data):
        return self.human_only or bool(self.human_policy and resolve(self.human_policy)(workspace, self.name, data))

    def field_scope(self, data):
        fields = set()
        for key in self.requested_fields:
            fields.update(data.get(key, ()))
        return fields

    def execute(self, workspace, data):
        if self.guard:
            resolve(self.guard)(workspace, data, self.references(workspace, data))
        if self.handler == "collaboration.dispatch":
            return resolve(self.handler)(workspace, self.name, data)
        return resolve(self.handler)(workspace, data)

    def contract(self):
        return {
            "name": self.name,
            "command_version": 1,
            "input": {key: field_contract(field) for key, field in self.input_type().fields.items()},
            "object_references": list(self.object_refs),
            "dynamic_references": self.reference_resolver is not None,
            "target_field": self.target_field,
            "target_types": list(self.target_types),
            "policy": {
                "human_only": self.human_only,
                "conditional_human_only": self.human_policy is not None,
                "agent_review_required": True,
                "independent_reviewer": True,
                "conditional_review": self.review_policy is not None,
                "guards": "executable_handler",
            },
            "planner": "transactional_effects_v1",
            "transport": self.transport,
            "creation": self.creation.contract() if self.creation else None,
            "object_action": self.object_action,
            "lifecycle": (
                {
                    "types": list(self.lifecycle_types),
                    "parameter": self.transition_parameter,
                    "parameter_choices": list(self.transition_choices()),
                }
                if self.lifecycle_types
                else None
            ),
        }


def field_contract(field):
    result = {"required": field.required, "nullable": field.allow_null}
    if isinstance(field, serializers.Serializer):
        result.update(type="object", fields={key: field_contract(value) for key, value in field.fields.items()})
    elif isinstance(field, serializers.ListField):
        result.update(type="array", items=field_contract(field.child))
    elif isinstance(field, serializers.DictField):
        result.update(type="object", additional_properties=field_contract(field.child))
    else:
        result["type"] = next(
            (
                kind
                for cls, kind in (
                    (serializers.UUIDField, "uuid"),
                    (serializers.DateTimeField, "datetime"),
                    (serializers.BooleanField, "boolean"),
                    (serializers.IntegerField, "integer"),
                    (serializers.FloatField, "number"),
                    (serializers.CharField, "string"),
                    (serializers.ChoiceField, "string"),
                )
                if isinstance(field, cls)
            ),
            "json",
        )
    if hasattr(field, "contract_type"):
        result["type"] = field.contract_type
    if result["type"] not in CAPABILITY_FIELD_TYPES:
        raise ValueError(f"Unsupported capability field contract: {result['type']}")
    if isinstance(field, serializers.ChoiceField):
        result["choices"] = list(field.choices)
    if getattr(field, "object_types", None):
        result["object_types"] = list(field.object_types)
    for attr in ("min_value", "max_value", "min_length", "max_length", "allow_blank", "allow_empty"):
        value = getattr(field, attr, None)
        if value is not None:
            result[attr] = value
    if field.default is not serializers.empty and not callable(field.default):
        result["default"] = field.default
    elif field.default in (list, dict):
        result["default"] = field.default()
    return result


CAPABILITIES: dict[str, Capability] = {}


def register(capability: Capability):
    if capability.name in CAPABILITIES:
        raise ValueError(f"Capability already registered: {capability.name}")
    CAPABILITIES[capability.name] = capability
    return capability


def get_capability(name: str) -> Capability:
    try:
        return CAPABILITIES[name]
    except KeyError as exc:
        raise ValidationError({"command_name": "Unknown command."}) from exc


class RuntimeOperations(Mapping):
    def __getitem__(self, operation):
        return next(c.name for c in CAPABILITIES.values() if c.runtime_operation == operation)

    def __iter__(self):
        return (c.runtime_operation for c in CAPABILITIES.values() if c.runtime_operation)

    def __len__(self):
        return sum(c.runtime_operation is not None for c in CAPABILITIES.values())


class InputContracts(Mapping):
    """Compatibility view, never a second list of command names."""

    def __getitem__(self, name):
        return CAPABILITIES[name].input_type

    def __iter__(self):
        return iter(CAPABILITIES)

    def __len__(self):
        return len(CAPABILITIES)


GUARDS: dict[str, TransitionGuard] = {}


def register_guard(guard: TransitionGuard):
    if guard.name in GUARDS:
        raise ValueError(f"Transition guard already registered: {guard.name}")
    GUARDS[guard.name] = guard
    return guard


def get_guard(name: str) -> TransitionGuard:
    try:
        return GUARDS[name]
    except KeyError as exc:
        raise ValidationError({"lifecycle": f"Unknown transition guard: {name}."}) from exc


def guard_contracts():
    return {name: guard.contract() for name, guard in GUARDS.items()}


def command_contracts(*, nonhuman=False):
    return {name: c.contract() for name, c in CAPABILITIES.items() if not nonhuman or not c.human_only}


def runtime_definitions(workspace, *, context=None, object_types=None):
    from plane.radar.runtime_identity import runtime_types

    known = set(runtime_types(workspace, context=context).values_list("key", flat=True))
    if object_types is not None and "*" not in object_types:
        known.intersection_update(object_types)
    result = {}
    for capability in CAPABILITIES.values():
        operation = capability.runtime_operation
        if operation is None or capability.human_only or not known.issuperset(capability.runtime_required_types):
            continue
        parameters = {}
        for key, field in capability.input_type().fields.items():
            if key in {"context", capability.target_field}:
                continue
            contract = field_contract(field)
            kind = contract["type"]
            kind = "string_list" if kind == "array" else "string" if kind == "uuid" else kind
            parameters[key] = {"type": kind, "required": field.required}
        targets = (
            known - {"person"} if capability.target_types == ("*",) else known.intersection(capability.target_types)
        )
        if capability.target_field and not targets:
            continue
        result[operation] = {
            "id": operation,
            "description": operation,
            "target_types": sorted(targets),
            "parameters": parameters,
        }
    return result


register(
    Capability(
        "CreateObject",
        "CreateObjectInput",
        "handlers._create_object",
        reference_resolver="handlers.creation_references",
        composed_capability="handlers.creation_capability",
        creation=CreationProfile(),
    )
)
register(
    Capability(
        "UpdateObject",
        "UpdateObjectInput",
        "handlers._update",
        ("object_id",),
        "handlers.update_references",
        human_policy="handlers.human_only_policy",
        requested_fields=("changes", "set_properties", "remove_properties"),
        lifecycle_types=("*",),
    )
)
register(
    Capability(
        "InitializeObjectProperties",
        "InitializeObjectPropertiesInput",
        "handlers._initialize_properties",
        ("object_id",),
        human_only=True,
    )
)
register(
    Capability(
        "LinkObjects",
        "LinkObjectsInput",
        "handlers._link",
        ("source_id", "target_id"),
        review_policy="handlers.relation_review",
    )
)
register(
    Capability(
        "UnlinkObjects",
        "UnlinkObjectsInput",
        "handlers._unlink",
        reference_resolver="handlers.unlink_references",
        review_policy="handlers.relation_review",
    )
)
register(
    Capability(
        "CreateAction",
        "CreateActionInput",
        "handlers._create_action",
        ("origin_decision_id", "owner_person_id", "executor_person_ids", "mitigates_risk_ids"),
        creation=CreationProfile(
            types=("action",),
            parameters="CreateActionParameters",
            property_fields=("description", "next_step", "priority", "due_date"),
            required_properties=("description",),
            initial_states=("todo",),
            effects="handlers.action_effects",
        ),
    )
)
register(
    Capability(
        "RegisterRisk",
        "RegisterRiskInput",
        "handlers._register_risk",
        ("owner_person_id", "threatens_object_ids"),
        creation=CreationProfile(
            types=("risk",),
            parameters="RegisterRiskParameters",
            property_fields=("description", "likelihood", "impact", "response_strategy", "review_date"),
            required_properties=("description",),
            initial_states=("identified",),
            effects="handlers.risk_effects",
        ),
    )
)
register(
    Capability(
        "CreateDecision",
        "CreateDecisionInput",
        "handlers._create_decision",
        ("project_id", "evidence_ids", "consultation_person_ids", "notification_person_ids"),
        creation=CreationProfile(
            types=("decision",),
            parameters="CreateDecisionParameters",
            property_fields=("context", "decision", "rationale", "consequences"),
            required_properties=("context", "decision", "rationale"),
            initial_states=("proposed",),
            effects="handlers.decision_effects",
        ),
    )
)
register(
    Capability(
        "ApproveDecision",
        "ApproveDecisionInput",
        "handlers._approve_decision",
        ("decision_id", "approver_person_id"),
        "handlers.approval_references",
        human_only=True,
        object_action="decision_id",
        action_prefill="handlers.approver_prefill",
    )
)
register(
    Capability(
        "CompleteAction",
        "CompleteActionInput",
        "handlers._complete_action",
        ("action_id", "evidence_id"),
        lifecycle_types=("action",),
        object_action="action_id",
    )
)
register(Capability("AddEvidence", "AddEvidenceInput", "handlers._add_evidence", ("target_id", "document.existing_id")))
register(
    Capability(
        "CaptureIssue",
        "CaptureIssueInput",
        "operations._capture",
        ("owner_id",),
        guard="operations.check_context",
        runtime_operation="capture_issue",
        runtime_required_types=("case", "management_item", "document"),
        source_parameter="source",
    )
)
register(
    Capability(
        "DelegateAction",
        "DelegateActionInput",
        "operations._delegate",
        ("action_id", "executor_id", "executor_ids"),
        guard="operations.check_context",
        reference_resolver="operations.delegation_references",
        runtime_operation="delegate",
        runtime_required_types=("person",),
        target_field="action_id",
        target_types=("action",),
        lifecycle_types=("commitment",),
    )
)
register(
    Capability(
        "ReviewObject",
        "ReviewObjectInput",
        "operations._review",
        ("target_id", "evidence_id"),
        guard="operations.check_context",
        runtime_operation="review",
        runtime_required_types=("document",),
        target_field="target_id",
        target_types=("*",),
        lifecycle_types=("*",),
        transition_parameter="disposition",
    )
)
register(
    Capability(
        "RecordMeasurement",
        "RecordMeasurementInput",
        "operations._measure",
        ("indicator_id", "evidence_id"),
        guard="operations.check_context",
        runtime_operation="record_measurement",
        runtime_required_types=("document",),
        target_field="indicator_id",
        target_types=("indicator",),
        source_parameter="evidence_source",
        evidence_text_parameter="evidence_text",
    )
)
for name, input_name in (
    ("AddComment", "AddCommentInput"),
    ("EditComment", "EditCommentInput"),
    ("DeleteComment", "CollaborationItemInput"),
    ("AddAttachment", "AddAttachmentInput"),
    ("RenameAttachment", "RenameAttachmentInput"),
    ("DeleteAttachment", "CollaborationItemInput"),
):
    register(
        Capability(
            name,
            input_name,
            "collaboration.dispatch",
            ("object_id",),
            human_only=True,
            transport="multipart_upload" if name == "AddAttachment" else "command_envelope",
        )
    )

register_guard(
    TransitionGuard(
        "decision_approval",
        "UpdateObject",
        "handlers.decision_approval_guard",
        after="handlers.decision_taken",
        references="handlers.decision_approval_references",
        human_only=True,
        types=("decision",),
    )
)
