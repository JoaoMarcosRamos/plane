"""Versioned, closed rule operators; workspace invariants live on ObjectType.rules."""

import hashlib
import math
from pathlib import Path

from rest_framework.exceptions import ValidationError

RULES_REVISION = "2.1.u0.1"

ORDINARY_TRANSITIONS = {
    "objective": {("draft", "active"), ("active", "on_hold"), ("on_hold", "active")},
    "project": {("draft", "active"), ("active", "on_hold"), ("on_hold", "active")},
    "action": {("todo", "in_progress"), ("in_progress", "waiting"), ("waiting", "in_progress")},
    "risk": {("identified", "monitoring"), ("monitoring", "mitigating"), ("mitigating", "monitoring")},
    "document": {("draft", "active")},
    "person": {("active", "inactive"), ("inactive", "active")},
}


def implementation_contract() -> dict:
    # Include handlers/guards, not only a manually bumped revision. A release that
    # changes semantics cannot consume an approval for the previous implementation.
    root = Path(__file__).resolve().parents[1]
    sources = sorted(
        path
        for path in root.rglob("*.py")
        if not {"tests", "migrations", "management"}.intersection(path.relative_to(root).parts)
    )
    digest = hashlib.sha256()
    for path in sources:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {"revision": RULES_REVISION, "implementation_sha256": digest.hexdigest()}


def validate_type_rules(rules: dict) -> list[dict]:
    if not isinstance(rules, dict) or set(rules) - {"invariants"}:
        raise ValidationError({"rules": "Use the declared invariants contract."})
    invariants = rules.get("invariants", [])
    if not isinstance(invariants, list) or len(invariants) > 32:
        raise ValidationError({"rules": "Use at most 32 typed invariants."})
    results = set()
    for invariant in invariants:
        if not isinstance(invariant, dict):
            raise ValidationError({"rules": "Each invariant must be an object."})
        kind = invariant.get("kind")
        if kind == "ordered_dates" and set(invariant) == {"kind", "first", "second"}:
            fields = [invariant["first"], invariant["second"]]
        elif kind == "product" and set(invariant) == {"kind", "result", "factors"}:
            factors = invariant["factors"]
            if not isinstance(factors, list) or not 2 <= len(factors) <= 16:
                raise ValidationError({"rules": "A product needs 2–16 factors."})
            fields = [invariant["result"], *factors]
            if not isinstance(invariant["result"], str) or invariant["result"] in results:
                raise ValidationError({"rules": "Derived results must be unique."})
            results.add(invariant["result"])
        else:
            raise ValidationError({"rules": "Unknown operator or parameters."})
        if not all(isinstance(key, str) and key and len(key) <= 64 for key in fields):
            raise ValidationError({"rules": "Use property keys of 1–64 characters."})
        if len(fields) != len(set(fields)):
            raise ValidationError({"rules": "An invariant must reference distinct properties."})
    if any(results.intersection(rule["factors"]) for rule in invariants if rule["kind"] == "product"):
        raise ValidationError({"rules": "Chained or cyclic products are not supported."})
    return invariants


def effective_invariants(object_type, definitions: dict) -> list[dict]:
    invariants = validate_type_rules(object_type.rules)
    for rule in invariants:
        fields = (
            [rule["first"], rule["second"]] if rule["kind"] == "ordered_dates" else [rule["result"], *rule["factors"]]
        )
        kinds = {"date"} if rule["kind"] == "ordered_dates" else {"integer", "number"}
        if any(key not in definitions or definitions[key].value_type not in kinds for key in fields):
            raise ValidationError({"rules": "Invariant references missing, inactive or incompatible definitions."})
    return invariants


def derived_fields(object_type, definitions: dict, changed: set[str]) -> set[str]:
    return {
        rule["result"]
        for rule in effective_invariants(object_type, definitions)
        if rule["kind"] == "product" and changed.intersection(rule["factors"])
    }


def evaluate_invariants(invariants: list[dict], effective: dict, explicit: dict) -> dict:
    derived = {}
    for rule in invariants:
        if rule["kind"] == "ordered_dates":
            first, second = effective.get(rule["first"]), effective.get(rule["second"])
            if first is not None and second is not None and first > second:
                raise ValidationError({rule["second"]: f"{rule['second']} cannot precede {rule['first']}."})
        else:
            if not all(key in effective for key in rule["factors"]):
                raise ValidationError({rule["result"]: "Derived factors must have effective values."})
            product = math.prod(effective[key] for key in rule["factors"])
            if rule["result"] in explicit and explicit[rule["result"]] != product:
                raise ValidationError({rule["result"]: "Derived value must equal the product of its factors."})
            derived[rule["result"]] = product
    return derived
