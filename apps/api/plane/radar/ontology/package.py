"""Materialized package definitions; deterministic input to install and three-way upgrade."""

from copy import deepcopy
import hashlib
import json
from .schema import load_schema


def _ordinary(*pairs):
    return [{"from": [source], "to": target} for source, target in pairs]


def _lifecycle(initial, transitions, prop="status"):
    return {"property": prop, "initial": initial, "transitions": transitions}


# RADAR package behavior over registered capabilities/guards (Core U1 3B/3C).
# UpdateObject transitions migrate the former ORDINARY_TRANSITIONS table; the other
# entries declare the specialized paths that the handlers previously encoded by type.
PACKAGE_BEHAVIOR = {
    "objective": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle("draft", _ordinary(("draft", "active"), ("active", "on_hold"), ("on_hold", "active"))),
    },
    "project": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle("draft", _ordinary(("draft", "active"), ("active", "on_hold"), ("on_hold", "active"))),
    },
    "decision": {
        "creation": {"capability": "CreateDecision"},
        "lifecycle": _lifecycle(
            "proposed",
            [{"from": ["proposed"], "to": "decided", "guard": "decision_approval", "stamp": "decided_at"}],
        ),
    },
    "action": {
        "creation": {"capability": "CreateAction"},
        "lifecycle": _lifecycle(
            "todo",
            [
                *_ordinary(("todo", "in_progress"), ("in_progress", "waiting"), ("waiting", "in_progress")),
                {
                    "from": ["todo", "in_progress", "waiting"],
                    "to": "done",
                    "capability": "CompleteAction",
                    "stamp": "completed_at",
                },
            ],
        ),
    },
    "risk": {
        "creation": {"capability": "RegisterRisk"},
        "lifecycle": _lifecycle(
            "identified",
            [
                *_ordinary(("identified", "monitoring"), ("monitoring", "mitigating"), ("mitigating", "monitoring")),
                {
                    "from": ["identified", "monitoring", "mitigating", "accepted"],
                    "to": "closed",
                    "capability": "ReviewObject",
                    "parameter": "resolved",
                },
                {
                    "from": ["identified", "monitoring", "mitigating"],
                    "to": "accepted",
                    "capability": "ReviewObject",
                    "parameter": "accepted",
                },
            ],
        ),
    },
    "person": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle("active", _ordinary(("active", "inactive"), ("inactive", "active"))),
    },
    "document": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle("draft", _ordinary(("draft", "active"))),
    },
    "case": {"creation": {"capability": "CreateObject"}, "lifecycle": _lifecycle("open", [])},
    "management_item": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle(
            "inbox",
            [
                {
                    "from": ["inbox", "triaged", "planned", "in_progress", "waiting"],
                    "to": "done",
                    "capability": "ReviewObject",
                    "parameter": "resolved",
                }
            ],
        ),
    },
    "indicator": {"creation": {"capability": "CreateObject"}, "lifecycle": _lifecycle("active", [])},
    "commitment": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": _lifecycle(
            "proposed", [{"from": ["confirmed"], "to": "superseded", "capability": "DelegateAction"}]
        ),
    },
}


def _sections(*sections):
    return [{"key": key, "label": label, "properties": list(properties)} for key, label, properties in sections]


# Core U1 C21: principal narrative and sections per seeded type. Layout only; never authority.
PACKAGE_PRESENTATION = {
    "objective": {
        "narrative": "description",
        "sections": _sections(
            ("outcome", "Outcome", ("outcome", "progress")),
            ("planning", "Planning", ("status", "priority", "timeframe", "start_date", "due_date")),
        ),
    },
    "project": {
        "narrative": "description",
        "sections": _sections(("planning", "Planning", ("status", "due_date"))),
    },
    "decision": {
        "narrative": "decision",
        "sections": _sections(
            ("reasoning", "Reasoning", ("context", "rationale", "consequences")),
            ("status", "Status", ("status", "decided_at")),
        ),
    },
    "action": {
        "narrative": "description",
        "sections": _sections(
            ("execution", "Execution", ("status", "next_step", "priority", "due_date", "completed_at"))
        ),
    },
    "risk": {
        "narrative": "description",
        "sections": _sections(
            ("assessment", "Assessment", ("likelihood", "impact", "score")),
            ("response", "Response", ("status", "response_strategy", "review_date")),
        ),
    },
    "person": {
        "narrative": "content",
        "sections": _sections(("profile", "Profile", ("status", "role", "team", "email", "timezone"))),
    },
    "document": {
        "narrative": "content",
        "sections": _sections(("source", "Source", ("status", "document_type", "summary", "uri", "source_system"))),
    },
    "case": {"narrative": "description", "sections": _sections(("status", "Status", ("status",)))},
    "management_item": {
        "narrative": "description",
        "sections": _sections(
            ("triage", "Triage", ("status", "kind", "priority", "context", "due_date", "next_review")),
        ),
    },
    "indicator": {
        "narrative": "description",
        "sections": _sections(
            ("measure", "Measure", ("status", "unit", "direction", "cadence", "formula")),
            ("values", "Values", ("baseline", "current", "target", "measured_at")),
        ),
    },
    "commitment": {"narrative": "description", "sections": _sections(("status", "Status", ("status",)))},
}


def package_definitions(schema=None):
    schema = schema or load_schema()
    result = {}
    for key, spec in schema["object_types"].items():
        result[f"types:{key}"] = {
            "name": spec["label"],
            "description": "",
            "icon": "",
            "is_active": True,
            "rules": {
                "invariants": [
                    {k: v for k, v in rule.items() if k != "class"}
                    for rule in schema["invariants"]
                    if rule["class"] == key
                ],
                **PACKAGE_BEHAVIOR.get(key, {}),
                **({"presentation": PACKAGE_PRESENTATION[key]} if key in PACKAGE_PRESENTATION else {}),
                "runtime": {
                    "enabled": True,
                    "identity": {"strategy": "dated_token_v1", "prefix": spec["prefix"]},
                    "contexts": ["company", "manager"],
                },
            },
        }
        for prop_key, prop in {"status": {"type": "enum", **spec["status"]}, **spec["attributes"]}.items():
            config = {k: v for k, v in prop.items() if k in {"default", "min", "max", "terminal"}}
            if "vocabulary" in prop:
                config["choices"] = schema["vocabularies"][prop["vocabulary"]]
            result[f"properties:{key}.{prop_key}"] = {
                "name": prop_key,
                "value_type": prop["type"],
                "config": config,
                "is_required": prop.get("required", False),
                "is_active": True,
            }
        if key == "action":
            result["properties:action.due_at"] = {
                "name": "Delegation deadline",
                "value_type": "datetime",
                "config": {},
                "is_required": False,
                "is_active": True,
            }
    for key, spec in schema["link_types"].items():
        result[f"relations:{key}"] = {
            "forward_label": spec["roles"]["source"],
            "reverse_label": spec["roles"]["target"],
            "description": spec["description"],
            "source_types": spec["domain"],
            "target_types": spec["codomain"],
            "allowed_pairs": spec.get("allowed_pairs", []),
            "cardinality": spec["cardinality"],
            "allow_self": spec["constraints"]["self_link"],
            "is_active": True,
        }
    return deepcopy(result)


def package_hash(definitions):
    return hashlib.sha256(json.dumps(definitions, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
