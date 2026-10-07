"""Closed structural registry. Config cannot grant capabilities or execute code."""

import math
import re
from datetime import date, datetime
from uuid import UUID
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email, URLValidator
from rest_framework.exceptions import ValidationError

PROPERTY_KINDS = {
    "string": frozenset({"default"}),
    "string_list": frozenset({"default"}),
    "number": frozenset({"default", "min", "max"}),
    "integer": frozenset({"default", "min", "max"}),
    "boolean": frozenset({"default"}),
    "enum": frozenset({"default", "choices", "terminal"}),
    "date": frozenset({"default"}),
    "datetime": frozenset({"default"}),
    "email": frozenset({"default"}),
    "uri": frozenset({"default"}),
    "user": frozenset({"default"}),
}
# Reserved migration aliases, not additional persisted kinds.
KIND_ALIASES = {"text": "string", "url": "uri"}
# Core package references outside the initial materialized slice remain reserved.
RESERVED_TYPE_REFERENCES = frozenset({"feedback", "meeting", "learning", "routine"})
CARDINALITIES = ("0..1", "0..n", "1..1")


def validate_literal(kind, value, config):
    valid = (
        isinstance(value, str)
        if kind in {"string", "email", "uri", "enum", "date", "datetime", "user"}
        else isinstance(value, list) and all(isinstance(item, str) for item in value)
        if kind == "string_list"
        else type(value) is bool
        if kind == "boolean"
        else type(value) is int
        if kind == "integer"
        else type(value) in (int, float) and math.isfinite(value)
        if kind == "number"
        else False
    )
    if not valid:
        raise ValidationError({"value": f"Expected {kind}; null requires removal."})
    try:
        if kind == "enum" and value not in config.get("choices", []):
            raise ValueError("Select a declared vocabulary value.")
        if kind in {"number", "integer"} and (
            "min" in config and value < config["min"] or "max" in config and value > config["max"]
        ):
            raise ValueError("Value outside the configured range.")
        if kind == "date" and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use YYYY-MM-DD.")
        if kind == "datetime":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or "T" not in value:
                raise ValueError("Use ISO datetime with timezone.")
        if kind == "email":
            validate_email(value)
        if kind == "uri":
            URLValidator(schemes=["https", "http", "ftp", "ftps"])(value)
        if kind == "user":
            UUID(value)
    except (ValueError, TypeError, OverflowError, DjangoValidationError) as exc:
        raise ValidationError({"value": str(exc)}) from exc
    return value


def validate_property_config(kind, config):
    if kind not in PROPERTY_KINDS or not isinstance(config, dict) or set(config) - PROPERTY_KINDS[kind]:
        raise ValidationError({"config": "Unsupported kind or configuration keys."})
    for bound in ("min", "max"):
        if bound in config and (
            type(config[bound]) not in (int, float)
            or not math.isfinite(config[bound])
            or kind == "integer"
            and type(config[bound]) is not int
        ):
            raise ValidationError({"config": "Bounds must be finite numbers of the declared kind."})
    if "min" in config and "max" in config and config["min"] > config["max"]:
        raise ValidationError({"config": "min must not exceed max."})
    if kind == "enum":
        choices = config.get("choices")
        if not isinstance(choices, list) or not choices or any(not isinstance(v, str) or not v for v in choices):
            raise ValidationError({"config": "Enum requires nonempty string choices."})
        if len(set(choices)) != len(choices):
            raise ValidationError({"config": "Choices must be unique."})
        terminal = config.get("terminal", [])
        if (
            not isinstance(terminal, list)
            or any(v not in choices for v in terminal)
            or len(set(terminal)) != len(terminal)
        ):
            raise ValidationError({"config": "Terminal values must be unique declared choices."})
    if "default" in config:
        validate_literal(kind, config["default"], config)


def validate_relation_descriptor(spec, known_types):
    known_types = set(known_types) | RESERVED_TYPE_REFERENCES

    def types(values):
        return (
            isinstance(values, list)
            and bool(values)
            and all(isinstance(v, str) and (v == "*" or re.fullmatch(r"[-a-zA-Z0-9_]{1,64}", v)) for v in values)
            and len(set(values)) == len(values)
            and ("*" not in values or values == ["*"])
            and all(v == "*" or v in known_types for v in values)
        )

    source, target = spec["source_types"], spec["target_types"]
    if (
        not types(source)
        or not types(target)
        or spec["cardinality"] not in CARDINALITIES
        or type(spec["allow_self"]) is not bool
    ):
        raise ValidationError({"relation_type": "Invalid domain, codomain, cardinality or self-link flag."})
    pairs = spec["allowed_pairs"]
    if (
        not isinstance(pairs, list)
        or any(
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(v, str) or v not in known_types for v in pair)
            or ("*" not in source and pair[0] not in source)
            or ("*" not in target and pair[1] not in target)
            for pair in pairs
        )
        or len({tuple(pair) for pair in pairs}) != len(pairs)
    ):
        raise ValidationError({"allowed_pairs": "Use unique declared type pairs within domain/codomain."})
