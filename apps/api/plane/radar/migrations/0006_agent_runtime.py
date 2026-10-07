from uuid import uuid4
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("radar", "0005_remove_relationtype_radar_reltype_cardinality_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimecredential",
            name="channel",
            field=models.CharField(
                choices=[("telegram", "telegram"), ("plane", "plane")], default="telegram", max_length=16
            ),
        ),
        migrations.CreateModel(
            name="AgentRuntimeRun",
            fields=[
                ("id", models.UUIDField(default=uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("input_hash", models.CharField(max_length=64)),
                ("request_data", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "binding",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="radar.runtimecredential"),
                ),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="db.workspace")),
            ],
            options={
                "db_table": "radar_agent_runtime_runs",
                "constraints": [
                    models.UniqueConstraint(fields=("workspace", "user", "idempotency_key"), name="radar_agent_run_key")
                ],
            },
        ),
    ]
