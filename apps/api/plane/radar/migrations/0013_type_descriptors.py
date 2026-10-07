from django.db import migrations

# Frozen Core U1 3B/3C package behavior; never import mutable application rules here.
DESCRIPTORS = {
    "action": {
        "creation": {"capability": "CreateAction"},
        "lifecycle": {
            "initial": "todo",
            "property": "status",
            "transitions": [
                {"from": ["todo"], "to": "in_progress"},
                {"from": ["in_progress"], "to": "waiting"},
                {"from": ["waiting"], "to": "in_progress"},
                {
                    "capability": "CompleteAction",
                    "from": ["todo", "in_progress", "waiting"],
                    "stamp": "completed_at",
                    "to": "done",
                },
            ],
        },
    },
    "case": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {"initial": "open", "property": "status", "transitions": []},
    },
    "commitment": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {
            "initial": "proposed",
            "property": "status",
            "transitions": [{"capability": "DelegateAction", "from": ["confirmed"], "to": "superseded"}],
        },
    },
    "decision": {
        "creation": {"capability": "CreateDecision"},
        "lifecycle": {
            "initial": "proposed",
            "property": "status",
            "transitions": [
                {"from": ["proposed"], "guard": "decision_approval", "stamp": "decided_at", "to": "decided"}
            ],
        },
    },
    "document": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {"initial": "draft", "property": "status", "transitions": [{"from": ["draft"], "to": "active"}]},
    },
    "indicator": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {"initial": "active", "property": "status", "transitions": []},
    },
    "management_item": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {
            "initial": "inbox",
            "property": "status",
            "transitions": [
                {
                    "capability": "ReviewObject",
                    "from": ["inbox", "triaged", "planned", "in_progress", "waiting"],
                    "parameter": "resolved",
                    "to": "done",
                }
            ],
        },
    },
    "objective": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {
            "initial": "draft",
            "property": "status",
            "transitions": [
                {"from": ["draft"], "to": "active"},
                {"from": ["active"], "to": "on_hold"},
                {"from": ["on_hold"], "to": "active"},
            ],
        },
    },
    "person": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {
            "initial": "active",
            "property": "status",
            "transitions": [{"from": ["active"], "to": "inactive"}, {"from": ["inactive"], "to": "active"}],
        },
    },
    "project": {
        "creation": {"capability": "CreateObject"},
        "lifecycle": {
            "initial": "draft",
            "property": "status",
            "transitions": [
                {"from": ["draft"], "to": "active"},
                {"from": ["active"], "to": "on_hold"},
                {"from": ["on_hold"], "to": "active"},
            ],
        },
    },
    "risk": {
        "creation": {"capability": "RegisterRisk"},
        "lifecycle": {
            "initial": "identified",
            "property": "status",
            "transitions": [
                {"from": ["identified"], "to": "monitoring"},
                {"from": ["monitoring"], "to": "mitigating"},
                {"from": ["mitigating"], "to": "monitoring"},
                {
                    "capability": "ReviewObject",
                    "from": ["identified", "monitoring", "mitigating", "accepted"],
                    "parameter": "resolved",
                    "to": "closed",
                },
                {
                    "capability": "ReviewObject",
                    "from": ["identified", "monitoring", "mitigating"],
                    "parameter": "accepted",
                    "to": "accepted",
                },
            ],
        },
    },
}
SECTIONS = ("creation", "lifecycle")


def _base_key(key):
    return f"types:{key}"


def install_descriptors(apps, schema_editor):
    db = schema_editor.connection.alias
    object_type = apps.get_model("radar", "ObjectType")
    state_model = apps.get_model("radar", "WorkspaceSchemaState")
    installed = {}
    for row in object_type.objects.using(db).filter(key__in=DESCRIPTORS):
        rules = dict(row.rules or {})
        if any(section in rules for section in SECTIONS):
            continue
        rules.update(DESCRIPTORS[row.key])
        object_type.objects.using(db).filter(pk=row.pk).update(rules=rules)
        installed.setdefault(row.workspace_id, {})[str(row.pk)] = row.key
    for state in state_model.objects.using(db).filter(workspace_id__in=installed):
        base = dict(state.installed_base or {})
        definitions = dict(base.get("definitions", {}))
        for pk, key in installed[state.workspace_id].items():
            record = _base_key(key)
            if base.get("ids", {}).get(record) == pk and record in definitions:
                spec = dict(definitions[record])
                spec["rules"] = {**spec.get("rules", {}), **DESCRIPTORS[key]}
                definitions[record] = spec
        base["definitions"] = definitions
        # Metadata changed outside a command: invalidate open forms, caches and pending approvals.
        state_model.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


def remove_descriptors(apps, schema_editor):
    """Pre-3B code refuses these sections; downgrade drops them, including local customizations."""
    db = schema_editor.connection.alias
    object_type = apps.get_model("radar", "ObjectType")
    state_model = apps.get_model("radar", "WorkspaceSchemaState")
    workspaces = set()
    for row in object_type.objects.using(db).all():
        rules = dict(row.rules or {})
        if any(section in rules for section in SECTIONS):
            object_type.objects.using(db).filter(pk=row.pk).update(
                rules={key: value for key, value in rules.items() if key not in SECTIONS}
            )
            workspaces.add(row.workspace_id)
    for state in state_model.objects.using(db).filter(workspace_id__in=workspaces):
        base = dict(state.installed_base or {})
        definitions = {}
        for record, spec in base.get("definitions", {}).items():
            if record.startswith("types:") and isinstance(spec.get("rules"), dict):
                spec = {**spec, "rules": {k: v for k, v in spec["rules"].items() if k not in SECTIONS}}
            definitions[record] = spec
        base["definitions"] = definitions
        state_model.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


class Migration(migrations.Migration):
    dependencies = [("radar", "0012_workspace_schema")]
    operations = [migrations.RunPython(install_descriptors, remove_descriptors)]
