"""Regression coverage for the historical Alembic chain."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app import config as app_config


def test_fresh_database_upgrades_to_head_without_live_schema_import(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A future schema change must not leak backwards into revision 0001."""

    database_path = tmp_path / "fresh.sqlite"
    database_url = f"sqlite:///{database_path}"
    # test_config reloads the settings module while exercising .env
    # precedence.  Address the module's current singleton rather than a stale
    # object imported during collection.
    monkeypatch.setattr(app_config.settings, "database_url_override", database_url)

    config = Config("alembic.ini")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    schema = inspect(engine)
    try:
        agent_run_columns = {column["name"] for column in schema.get_columns("agent_runs")}
        assert {"origin", "metrics"} <= agent_run_columns
        assert {
            "agent_memories",
            "agent_runs",
            "agent_thread_files",
            "pending_radar_selections",
            "radar_thread_referents",
            "radar_api_messages",
            "radar_api_sessions",
            "scheduled_jobs",
        } <= set(schema.get_table_names())
    finally:
        engine.dispose()


def test_historical_revisions_do_not_import_the_live_schema() -> None:
    versions = Path("migrations/versions")

    offenders = [
        path.name
        for path in versions.glob("*.py")
        if "from app.database.schema import" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
