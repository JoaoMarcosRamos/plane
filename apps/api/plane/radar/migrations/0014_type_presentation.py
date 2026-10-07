from django.db import migrations

# Frozen Core U1 C21 package presentation; never import mutable application rules here.
PRESENTATIONS = {
    "action": {
        "narrative": "description",
        "sections": [
            {
                "key": "execution",
                "label": "Execution",
                "properties": ["status", "next_step", "priority", "due_date", "completed_at"],
            }
        ],
    },
    "case": {"narrative": "description", "sections": [{"key": "status", "label": "Status", "properties": ["status"]}]},
    "commitment": {
        "narrative": "description",
        "sections": [{"key": "status", "label": "Status", "properties": ["status"]}],
    },
    "decision": {
        "narrative": "decision",
        "sections": [
            {"key": "reasoning", "label": "Reasoning", "properties": ["context", "rationale", "consequences"]},
            {"key": "status", "label": "Status", "properties": ["status", "decided_at"]},
        ],
    },
    "document": {
        "narrative": "content",
        "sections": [
            {
                "key": "source",
                "label": "Source",
                "properties": ["status", "document_type", "summary", "uri", "source_system"],
            }
        ],
    },
    "indicator": {
        "narrative": "description",
        "sections": [
            {"key": "measure", "label": "Measure", "properties": ["status", "unit", "direction", "cadence", "formula"]},
            {"key": "values", "label": "Values", "properties": ["baseline", "current", "target", "measured_at"]},
        ],
    },
    "management_item": {
        "narrative": "description",
        "sections": [
            {
                "key": "triage",
                "label": "Triage",
                "properties": ["status", "kind", "priority", "context", "due_date", "next_review"],
            }
        ],
    },
    "objective": {
        "narrative": "description",
        "sections": [
            {"key": "outcome", "label": "Outcome", "properties": ["outcome", "progress"]},
            {
                "key": "planning",
                "label": "Planning",
                "properties": ["status", "priority", "timeframe", "start_date", "due_date"],
            },
        ],
    },
    "person": {
        "narrative": "content",
        "sections": [
            {"key": "profile", "label": "Profile", "properties": ["status", "role", "team", "email", "timezone"]}
        ],
    },
    "project": {
        "narrative": "description",
        "sections": [{"key": "planning", "label": "Planning", "properties": ["status", "due_date"]}],
    },
    "risk": {
        "narrative": "description",
        "sections": [
            {"key": "assessment", "label": "Assessment", "properties": ["likelihood", "impact", "score"]},
            {"key": "response", "label": "Response", "properties": ["status", "response_strategy", "review_date"]},
        ],
    },
}


def install_presentations(apps, schema_editor):
    db = schema_editor.connection.alias
    object_type = apps.get_model("radar", "ObjectType")
    state_model = apps.get_model("radar", "WorkspaceSchemaState")
    installed = {}
    for row in object_type.objects.using(db).filter(key__in=PRESENTATIONS):
        rules = dict(row.rules or {})
        if "presentation" in rules:
            continue
        rules["presentation"] = PRESENTATIONS[row.key]
        object_type.objects.using(db).filter(pk=row.pk).update(rules=rules)
        installed.setdefault(row.workspace_id, {})[str(row.pk)] = row.key
    for state in state_model.objects.using(db).filter(workspace_id__in=installed):
        base = dict(state.installed_base or {})
        definitions = dict(base.get("definitions", {}))
        for pk, key in installed[state.workspace_id].items():
            record = f"types:{key}"
            if base.get("ids", {}).get(record) == pk and record in definitions:
                spec = dict(definitions[record])
                spec["rules"] = {**spec.get("rules", {}), "presentation": PRESENTATIONS[key]}
                definitions[record] = spec
        base["definitions"] = definitions
        # Layout metadata changed outside a command: refresh open pages and caches.
        state_model.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


def remove_presentations(apps, schema_editor):
    """Pre-C21 code refuses this section; downgrade drops it, including local layouts."""
    db = schema_editor.connection.alias
    object_type = apps.get_model("radar", "ObjectType")
    state_model = apps.get_model("radar", "WorkspaceSchemaState")
    workspaces = set()
    for row in object_type.objects.using(db).all():
        rules = dict(row.rules or {})
        if "presentation" in rules:
            rules.pop("presentation")
            object_type.objects.using(db).filter(pk=row.pk).update(rules=rules)
            workspaces.add(row.workspace_id)
    for state in state_model.objects.using(db).filter(workspace_id__in=workspaces):
        base = dict(state.installed_base or {})
        definitions = {}
        for record, spec in base.get("definitions", {}).items():
            if record.startswith("types:") and isinstance(spec.get("rules"), dict):
                spec = {**spec, "rules": {k: v for k, v in spec["rules"].items() if k != "presentation"}}
            definitions[record] = spec
        base["definitions"] = definitions
        state_model.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


class Migration(migrations.Migration):
    dependencies = [("radar", "0013_type_descriptors")]
    operations = [migrations.RunPython(install_presentations, remove_presentations)]
