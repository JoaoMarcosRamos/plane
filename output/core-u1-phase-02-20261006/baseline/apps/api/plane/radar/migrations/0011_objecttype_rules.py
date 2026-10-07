from django.db import migrations, models


def seed_rules(apps, schema_editor):
    object_type = apps.get_model("radar", "ObjectType")
    # Frozen metadata from Core 3.2.0; never import mutable application rules here.
    rules = {
        "objective": [{"kind": "ordered_dates", "first": "start_date", "second": "due_date"}],
        "risk": [{"kind": "product", "result": "score", "factors": ["likelihood", "impact"]}],
    }
    for key, invariants in rules.items():
        object_type.objects.using(schema_editor.connection.alias).filter(key=key).update(
            rules={"invariants": invariants}
        )


class Migration(migrations.Migration):
    dependencies = [("radar", "0010_object_collaboration")]
    operations = [
        migrations.AddField(model_name="objecttype", name="rules", field=models.JSONField(default=dict)),
        migrations.RunPython(seed_rules, migrations.RunPython.noop),
    ]
