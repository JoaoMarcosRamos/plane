from django.db import migrations

# Frozen legacy contracts. Only managed seeded types opt in during migration.
PREFIXES = {
    "objective": "OBJ",
    "project": "PRJ",
    "decision": "DEC",
    "action": "ACT",
    "risk": "RSK",
    "person": "PER",
    "document": "DOC",
    "case": "CAS",
    "management_item": "MIT",
    "indicator": "IND",
    "commitment": "CMT",
}


def install_runtime(apps, schema_editor):
    db = schema_editor.connection.alias
    types = apps.get_model("radar", "ObjectType")
    states = apps.get_model("radar", "WorkspaceSchemaState")
    installed = {}
    changed = set()
    for row in types.objects.using(db).filter(key__in=PREFIXES, is_system=True):
        rules = dict(row.rules or {})
        descriptor = {
            "enabled": True,
            "identity": {"strategy": "dated_token_v1", "prefix": PREFIXES[row.key]},
            "contexts": ["company", "manager"],
        }
        if "runtime" not in rules:
            rules["runtime"] = descriptor
            types.objects.using(db).filter(pk=row.pk).update(rules=rules)
            changed.add(row.workspace_id)
        installed.setdefault(row.workspace_id, {})[str(row.pk)] = (row.key, descriptor)
    for state in states.objects.using(db).filter(workspace_id__in=installed):
        base = dict(state.installed_base or {})
        definitions = dict(base.get("definitions", {}))
        for pk, (key, descriptor) in installed[state.workspace_id].items():
            record = f"types:{key}"
            if base.get("ids", {}).get(record) == pk and record in definitions:
                spec = dict(definitions[record])
                # The package baseline must distinguish a local opt-out from a
                # package conflict. Never replace a previously installed contract.
                spec["rules"] = {"runtime": descriptor, **spec.get("rules", {})}
                definitions[record] = spec
        base["definitions"] = definitions
        if state.workspace_id in changed or base != state.installed_base:
            states.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


def remove_runtime(apps, schema_editor):
    """Old code refuses this section. Export local descriptors before application rollback."""
    db = schema_editor.connection.alias
    types = apps.get_model("radar", "ObjectType")
    states = apps.get_model("radar", "WorkspaceSchemaState")
    changed = set()
    for row in types.objects.using(db).all():
        rules = dict(row.rules or {})
        if "runtime" in rules:
            rules.pop("runtime")
            types.objects.using(db).filter(pk=row.pk).update(rules=rules)
            changed.add(row.workspace_id)
    for state in states.objects.using(db).filter(workspace_id__in=changed):
        base = dict(state.installed_base or {})
        definitions = {}
        for key, spec in base.get("definitions", {}).items():
            if key.startswith("types:") and isinstance(spec.get("rules"), dict):
                spec = {**spec, "rules": {k: v for k, v in spec["rules"].items() if k != "runtime"}}
            definitions[key] = spec
        base["definitions"] = definitions
        states.objects.using(db).filter(pk=state.pk).update(installed_base=base, revision=state.revision + 1)


class Migration(migrations.Migration):
    dependencies = [("radar", "0014_type_presentation")]
    operations = [migrations.RunPython(install_runtime, remove_runtime)]
