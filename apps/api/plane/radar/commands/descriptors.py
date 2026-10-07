"""Closed creation/lifecycle/presentation descriptors persisted in ObjectType.rules.

Metadata only selects capabilities and guards registered in application code.
A transition is never inferred from a property name: types without a lifecycle
keep their enums as ordinary properties, and a declared lifecycle refuses every
pair of states it does not list explicitly.
"""

import re

from rest_framework.exceptions import PermissionDenied, ValidationError

CONTENT = "content"
DEFAULT_CREATION = "CreateObject"
DEFAULT_TRANSITION = "UpdateObject"
LIFECYCLE_KEYS = frozenset({"property", "initial", "transitions"})
TRANSITION_KEYS = frozenset({"from", "to", "capability", "guard", "parameter", "stamp"})
KEY = re.compile(r"[-a-zA-Z0-9_]{1,64}")
PRESENTATION_KEYS = frozenset({"narrative", "sections"})
SECTION_KEYS = frozenset({"key", "label", "properties"})


def _key(value) -> bool:
    return isinstance(value, str) and bool(KEY.fullmatch(value))


def validate_creation(creation, type_key=None) -> dict:
    from .capabilities import CAPABILITIES

    if not isinstance(creation, dict) or set(creation) != {"capability"}:
        raise ValidationError({"creation": "Declare only the registered creation capability."})
    capability = CAPABILITIES.get(creation["capability"]) if isinstance(creation["capability"], str) else None
    if capability is None or capability.creation is None:
        raise ValidationError({"creation": "Select a registered creation capability."})
    if type_key is not None and not capability.creation.allows(type_key):
        raise ValidationError({"creation": f"{capability.name} does not create this Object type."})
    return creation


def validate_lifecycle(lifecycle, type_key=None) -> dict:
    """Structural and registry checks; definitions are checked by effective_lifecycle."""
    from .capabilities import CAPABILITIES, GUARDS

    if not isinstance(lifecycle, dict) or set(lifecycle) != LIFECYCLE_KEYS:
        raise ValidationError({"lifecycle": "Declare property, initial and transitions only."})
    if not _key(lifecycle["property"]) or not _key(lifecycle["initial"]):
        raise ValidationError({"lifecycle": "Use property and state keys of 1–64 characters."})
    transitions = lifecycle["transitions"]
    if not isinstance(transitions, list) or len(transitions) > 64:
        raise ValidationError({"lifecycle": "Use at most 64 explicit transitions."})
    pairs, selectors = set(), set()
    for transition in transitions:
        if not isinstance(transition, dict) or not {"from", "to"} <= set(transition) <= TRANSITION_KEYS:
            raise ValidationError({"lifecycle": "Each transition declares from/to and registered references only."})
        sources, target = transition["from"], transition["to"]
        if (
            not isinstance(sources, list)
            or not sources
            or not all(_key(state) for state in sources)
            or len(set(sources)) != len(sources)
            or not _key(target)
        ):
            raise ValidationError({"lifecycle": "Use explicit, unique source states and one target state."})
        if target in sources:
            raise ValidationError({"lifecycle": "A transition cannot loop to its own state."})
        name = transition.get("capability", DEFAULT_TRANSITION)
        capability = CAPABILITIES.get(name) if isinstance(name, str) else None
        if capability is None or not capability.lifecycle_types:
            raise ValidationError({"lifecycle": "Transitions reference registered lifecycle capabilities."})
        if type_key is not None and not capability.performs_transitions(type_key):
            raise ValidationError({"lifecycle": f"{name} does not perform transitions for this Object type."})
        parameter = transition.get("parameter")
        if (parameter is None) != (capability.transition_parameter is None) or (
            parameter is not None and parameter not in capability.transition_choices()
        ):
            raise ValidationError({"lifecycle": f"{name} transitions need its declared selector value only."})
        if "guard" in transition:
            guard = GUARDS.get(transition["guard"]) if isinstance(transition["guard"], str) else None
            if guard is None or guard.capability != name or type_key is not None and not guard.allows(type_key):
                raise ValidationError({"lifecycle": "Guards must be registered for this capability and type."})
        if "stamp" in transition and (not _key(transition["stamp"]) or transition["stamp"] == lifecycle["property"]):
            raise ValidationError({"lifecycle": "A stamp names another datetime property."})
        for source in sources:
            pair = (source, target, name)
            # Specialized capabilities choose their target, so the selector must be deterministic.
            selector = (source, name, parameter)
            if pair in pairs or name != DEFAULT_TRANSITION and selector in selectors:
                raise ValidationError({"lifecycle": "Transitions must be unique and deterministic."})
            pairs.add(pair)
            selectors.add(selector)
    return lifecycle


def validate_presentation(presentation) -> dict:
    """Layout only: a presentation never grants writes, hides guards or removes properties."""
    if not isinstance(presentation, dict) or set(presentation) != PRESENTATION_KEYS:
        raise ValidationError({"presentation": "Declare narrative and sections only."})
    if not _key(presentation["narrative"]):
        raise ValidationError({"presentation": "The narrative is content or a property key."})
    sections = presentation["sections"]
    if not isinstance(sections, list) or len(sections) > 16:
        raise ValidationError({"presentation": "Use at most 16 sections."})
    keys, properties = set(), set()
    for section in sections:
        if not isinstance(section, dict) or set(section) != SECTION_KEYS:
            raise ValidationError({"presentation": "Each section declares key, label and properties."})
        label, listed = section["label"], section["properties"]
        if (
            not _key(section["key"])
            or section["key"] in keys
            or not isinstance(label, str)
            or not 1 <= len(label.strip()) <= 64
            or not isinstance(listed, list)
            or len(listed) > 64
            or not all(_key(key) for key in listed)
            or properties.intersection(listed)
            or len(set(listed)) != len(listed)
        ):
            raise ValidationError({"presentation": "Sections need unique keys, labels and properties."})
        keys.add(section["key"])
        properties.update(listed)
    if presentation["narrative"] in properties:
        raise ValidationError({"presentation": "The narrative property is not repeated in a section."})
    return presentation


def effective_presentation(object_type, definitions: dict, *, strict=True) -> dict | None:
    """Strict when the presentation itself is edited; retiring a definition never depends on layout."""
    from .rules import effective_invariants, validate_type_rules

    presentation = validate_type_rules(object_type.rules, object_type.key, full=True)["presentation"]
    if presentation is None:
        return None
    narrative = presentation["narrative"]
    missing = [key for section in presentation["sections"] for key in section["properties"] if key not in definitions]
    if narrative != CONTENT:
        definition = definitions.get(narrative)
        derived = {r["result"] for r in effective_invariants(object_type, definitions) if r["kind"] == "product"}
        if definition is None:
            missing.append(narrative)
        elif definition.value_type != "string" or narrative in derived:
            raise ValidationError({"presentation": "The narrative is content or an active, editable text property."})
    if missing and strict:
        raise ValidationError({"presentation": f"Presentation references inactive properties: {', '.join(missing)}."})
    return presentation


def layout(object_type, definitions: dict) -> dict:
    """Effective Object Page layout. Without a presentation, the documented fallback applies."""
    try:
        presentation, diagnostic = effective_presentation(object_type, definitions, strict=False), None
    except ValidationError as exc:
        presentation, diagnostic = None, error_detail(exc)
    keys = list(definitions)
    if presentation is None:
        return {
            "source": "fallback" if diagnostic is None else "invalid_metadata",
            "diagnostic": diagnostic,
            "retired_references": [],
            "narrative": {"field": CONTENT, "label": "Content"},
            "content": {"role": "narrative", "label": "Content"},
            "sections": [{"key": "properties", "label": "Properties", "properties": keys}] if keys else [],
        }
    declared = [key for section in presentation["sections"] for key in section["properties"]]
    narrative = presentation["narrative"]
    retired = [key for key in [*declared, narrative] if key != CONTENT and key not in definitions]
    if narrative not in definitions:
        narrative = CONTENT
    sections = []
    for section in presentation["sections"]:
        present = [key for key in section["properties"] if key in definitions]
        if present:
            sections.append({**section, "properties": present})
    rest = [key for key in keys if key not in declared and key != narrative]
    if rest:
        sections.append({"key": "other", "label": "Other properties", "properties": rest})
    is_content = narrative == CONTENT
    return {
        "source": "presentation",
        "diagnostic": None,
        "retired_references": retired,
        "narrative": {"field": narrative, "label": "Content" if is_content else definitions[narrative].name},
        "content": {"role": "narrative" if is_content else "notes", "label": "Content" if is_content else "Notes"},
        "sections": sections,
    }


def error_detail(exc) -> str:
    def flatten(value):
        if isinstance(value, dict):
            return [item for part in value.values() for item in flatten(part)]
        if isinstance(value, list):
            return [item for part in value for item in flatten(part)]
        return [str(value)]

    return " ".join(flatten(exc.detail))


def creation_capability_name(object_type) -> str:
    return (object_type.rules or {}).get("creation", {}).get("capability", DEFAULT_CREATION)


def effective_lifecycle(object_type, definitions: dict) -> dict | None:
    from .rules import validate_type_rules

    lifecycle = validate_type_rules(object_type.rules, object_type.key, full=True)["lifecycle"]
    if lifecycle is None:
        return None
    definition = definitions.get(lifecycle["property"])
    if definition is None or definition.value_type != "enum":
        raise ValidationError({"lifecycle": "The lifecycle property must be an active enum definition."})
    states = set(definition.config.get("choices", []))
    terminal = set(definition.config.get("terminal", []))
    if lifecycle["initial"] not in states or lifecycle["initial"] in terminal:
        raise ValidationError({"lifecycle": "The initial state must be a declared nonterminal choice."})
    stamps = set()
    for transition in lifecycle["transitions"]:
        if not states.issuperset([*transition["from"], transition["to"]]):
            raise ValidationError({"lifecycle": "Transitions reference undeclared states."})
        if "stamp" in transition:
            stamp = definitions.get(transition["stamp"])
            if stamp is None or stamp.value_type != "datetime" or stamp.is_required:
                raise ValidationError({"lifecycle": "Stamps reference optional active datetime definitions."})
            stamps.add(transition["stamp"])
    from .rules import effective_invariants

    derived = {rule["result"] for rule in effective_invariants(object_type, definitions) if rule["kind"] == "product"}
    if {lifecycle["property"], *stamps} & derived:
        raise ValidationError({"lifecycle": "Lifecycle fields cannot be derived properties."})
    return lifecycle


def validate_effective_descriptors(object_type, definitions: dict) -> None:
    """Configuration-time check of the selected creation contract against the type schema."""
    from .capabilities import get_capability

    lifecycle = effective_lifecycle(object_type, definitions)
    profile = get_capability(creation_capability_name(object_type)).creation
    missing = {key for key in (*profile.property_fields, *profile.required_properties) if key not in definitions}
    if missing:
        raise ValidationError({"creation": f"Creation needs active definitions: {', '.join(sorted(missing))}."})
    if profile.initial_states and (lifecycle is None or lifecycle["initial"] not in profile.initial_states):
        raise ValidationError({"creation": "The selected creation capability does not accept this initial state."})
    effective_presentation(object_type, definitions, strict=False)


def _definitions(obj):
    from .primitives_semantic import property_definitions

    return property_definitions(obj)


def lifecycle_for(obj) -> dict | None:
    return effective_lifecycle(obj.object_type, _definitions(obj))


def state_property(obj) -> str:
    """The lifecycle field; legacy cardinality checks keep `status` for undeclared types."""
    lifecycle = lifecycle_for(obj)
    return lifecycle["property"] if lifecycle else "status"


def initial_state(object_type, definitions: dict) -> tuple[str, str] | None:
    lifecycle = effective_lifecycle(object_type, definitions)
    return (lifecycle["property"], lifecycle["initial"]) if lifecycle else None


def is_terminal(obj) -> bool:
    lifecycle = lifecycle_for(obj)
    if lifecycle is None:
        raise ValidationError({"lifecycle": "This Object type declares no lifecycle."})
    from .primitives_semantic import effective_values

    definition = _definitions(obj)[lifecycle["property"]]
    return effective_values(obj).get(lifecycle["property"]) in definition.config.get("terminal", [])


def find_transition(lifecycle: dict, current, target, capability: str) -> dict:
    candidates = [t for t in lifecycle["transitions"] if current in t["from"] and t["to"] == target]
    if not candidates:
        raise ValidationError({lifecycle["property"]: "This transition requires a dedicated workflow."})
    for transition in candidates:
        if transition.get("capability", DEFAULT_TRANSITION) == capability:
            return transition
    required = candidates[0].get("capability", DEFAULT_TRANSITION)
    raise ValidationError({lifecycle["property"]: f"Use {required} for this transition."})


def requested_transition(obj, values: dict, capability: str) -> dict | None:
    """The declared transition requested by an explicit patch, if the state changes."""
    from .primitives_semantic import effective_values

    lifecycle = lifecycle_for(obj)
    if lifecycle is None or lifecycle["property"] not in values:
        return None
    current = effective_values(obj).get(lifecycle["property"])
    if values[lifecycle["property"]] == current:
        return None
    return find_transition(lifecycle, current, values[lifecycle["property"]], capability)


def guarded_target(obj, values: dict, capability: str) -> str | None:
    """Guard of a requested target, independent of the current state.

    Planning observes the policy before and after the handler ran under its savepoint;
    a target reachable through a guarded transition keeps that guard's policy in both.
    """
    try:
        lifecycle = lifecycle_for(obj)
    except ValidationError:
        return None
    if lifecycle is None or lifecycle["property"] not in values:
        return None
    for transition in lifecycle["transitions"]:
        if (
            transition["to"] == values[lifecycle["property"]]
            and transition.get("capability", DEFAULT_TRANSITION) == capability
            and "guard" in transition
        ):
            return transition["guard"]
    return None


def declared_target(obj, capability: str, parameter=None, *, required=True) -> dict | None:
    """Specialized capabilities select the declared target from the current state."""
    from .primitives_semantic import effective_values

    lifecycle = lifecycle_for(obj)
    if lifecycle is not None:
        current = effective_values(obj).get(lifecycle["property"])
        declared = [
            transition
            for transition in lifecycle["transitions"]
            if transition.get("capability", DEFAULT_TRANSITION) == capability
            and transition.get("parameter") == parameter
        ]
        for transition in declared:
            if current in transition["from"]:
                return transition
        # Reapplying a nonterminal outcome is idempotent; terminal states need a declared exit.
        terminal = _definitions(obj)[lifecycle["property"]].config.get("terminal", [])
        for transition in declared:
            if transition["to"] == current and current not in terminal:
                return transition
    if required:
        raise ValidationError({"lifecycle": f"{capability} has no declared transition from the current state."})
    return None


def authorize_transition(obj, transition: dict) -> None:
    """Record that the handler executed the registered guard of this transition."""
    from .context import command_context

    command_context().authorized_transitions.add((obj.pk, tuple(transition["from"]), transition["to"]))


def governed_patch(obj, values: dict, remove=()) -> dict:
    """Shared by every property writer: no API, runtime or internal path escapes it."""
    from .context import command_context, command_now
    from .primitives_semantic import effective_values

    lifecycle = lifecycle_for(obj)
    if lifecycle is None:
        return values
    context = command_context()
    prop = lifecycle["property"]
    stamps = {t["stamp"] for t in lifecycle["transitions"] if "stamp" in t}
    if prop in remove or stamps.intersection(remove):
        raise ValidationError({prop: "Lifecycle fields cannot be removed."})
    for key in stamps.intersection(values):
        if context.lifecycle_stamps.get((obj.pk, key)) != values[key]:
            raise ValidationError({key: f"{key} is recorded by its lifecycle transition."})
    current = effective_values(obj).get(prop)
    if prop not in values or values[prop] == current:
        return values
    transition = find_transition(lifecycle, current, values[prop], context.command_name)
    if "guard" in transition and (obj.pk, tuple(transition["from"]), transition["to"]) not in (
        context.authorized_transitions
    ):
        raise PermissionDenied("This transition requires its registered guard.")
    if "stamp" in transition and transition["stamp"] not in values:
        stamp = command_now().isoformat()
        context.lifecycle_stamps[(obj.pk, transition["stamp"])] = stamp
        values = {**values, transition["stamp"]: stamp}
    return values
