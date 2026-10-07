"""Static checks for the official container runtime contract.

These tests deliberately avoid requiring a running Docker daemon. The full
``docker compose up`` smoke test remains a separate operational check.
"""

from pathlib import Path

from pydantic import AliasChoices

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_compose_passes_every_supported_agent_provider() -> None:
    compose = _read("docker-compose.yml")

    for variable in (
        "AGENT_MODEL",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    ):
        assert f"{variable}: ${{{variable}:-}}" in compose


def test_compose_enables_operational_info_logs_by_default() -> None:
    compose = _read("docker-compose.yml")

    assert "LOG_LEVEL: ${LOG_LEVEL:-INFO}" in compose


def test_container_receives_and_build_checks_the_default_timezone() -> None:
    compose = _read("docker-compose.yml")
    dockerfile = _read("Dockerfile")

    assert "APP_TIMEZONE: ${APP_TIMEZONE:-America/Bahia}" in compose
    assert "ZoneInfo('America/Bahia')" in dockerfile


def test_compose_passes_every_notion_id_the_settings_accept() -> None:
    """Every name ``Settings`` reads must be forwarded into the container.

    The list is derived from the settings instead of written out here, because
    a hardcoded copy is exactly what let ``NOTION_PEOPLE_DATA_SOURCE_ID`` reach
    production without being passed through: the code was right, the ``.env``
    was right, and the process still saw nothing.
    """

    compose = _read("docker-compose.yml")

    for variable in _notion_environment_names():
        # The feature flag defaults to ``false`` rather than to empty, for the
        # same reason the two Google flags do: an unset variable must leave the
        # integration off, and an empty string is not a boolean.
        default = "false" if variable == "NOTION_ENABLED" else ""
        assert f"{variable}: ${{{variable}:-{default}}}" in compose, (
            f"{variable} is missing from compose"
        )


def test_compose_and_example_forward_every_google_setting() -> None:
    compose = _read("docker-compose.yml")
    example = _read(".env.example")
    variables = {
        field_name.upper()
        for field_name in Settings.model_fields
        if field_name.startswith("google_") or field_name == "gmail_enabled"
    }

    for variable in variables:
        default = "false" if variable in {"GOOGLE_CALENDAR_ENABLED", "GMAIL_ENABLED"} else ""
        assert f"{variable}: ${{{variable}:-{default}}}" in compose
        assert f"{variable}=" in example


def test_compose_and_example_forward_every_radar_setting() -> None:
    compose = _read("docker-compose.yml")
    example = _read(".env.example")
    variables = {
        field_name.upper()
        for field_name in Settings.model_fields
        if field_name.startswith("radar_")
    }

    for variable in variables:
        if variable in {"RADAR_ENABLED", "RADAR_WRITES_ENABLED"}:
            default = "false"
        elif variable == "RADAR_BACKEND":
            default = "vault"
        elif variable == "RADAR_VAULT_PATH":
            default = "/data/radar-vault"
        elif variable == "RADAR_ALLOWED_TBOX_VERSIONS":
            default = "3.2.0"
        elif variable == "RADAR_WRITE_OPERATIONS":
            default = "capture_issue,delegate,review,record_measurement"
        elif variable in {"RADAR_APPROVAL_TTL_SECONDS", "RADAR_INTENT_DEDUP_WINDOW_SECONDS"}:
            default = "900" if variable == "RADAR_APPROVAL_TTL_SECONDS" else "86400"
        else:
            default = ""
        assert f"{variable}: ${{{variable}:-{default}}}" in compose
        assert f"{variable}=" in example


def test_radar_abox_is_a_persistent_volume_owned_by_the_runtime_user() -> None:
    compose = _read("docker-compose.yml")
    dockerfile = _read("Dockerfile")

    assert "- radar_abox:/data/radar-vault" in compose
    assert "radar_abox:" in compose
    assert "mkdir -p /home/appuser /data/radar-vault" in dockerfile
    assert "chown appuser:appgroup /home/appuser /data/radar-vault" in dockerfile


def test_private_radar_dependency_uses_a_build_secret_not_runtime_environment() -> None:
    compose = _read("docker-compose.yml")
    dockerfile = _read("Dockerfile")

    assert "--mount=type=secret,id=github_token,required=true" in dockerfile
    assert "environment: GITHUB_TOKEN" in compose
    assert "GITHUB_TOKEN:" not in compose.split("environment:", 1)[1].split("ports:", 1)[0]
    assert "ENV GITHUB_TOKEN" not in dockerfile


def test_image_loads_packaged_radar_resources_without_copying_an_abox() -> None:
    dockerfile = _read("Dockerfile")
    image_inputs = dockerfile + _read("requirements.txt")

    assert "from radar_vault import get_ontology_resources, load_packaged_ontology" in dockerfile
    assert "COPY ontology" not in dockerfile
    assert "COPY vault" not in dockerfile
    assert "COPY . " not in dockerfile
    assert "/Users/" not in image_inputs


def _notion_environment_names() -> set[str]:
    """Collect the environment names of every ``notion_*`` setting."""

    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        if not field_name.startswith("notion_"):
            continue
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            names.update(str(choice) for choice in alias.choices)
        elif isinstance(alias, str):
            names.add(alias)
        else:
            names.add(field_name.upper())
    return names


def test_supported_provider_adapters_are_direct_pinned_dependencies() -> None:
    requirements = _read("requirements.txt")

    assert "langchain-anthropic==" in requirements
    assert "langchain-openai==" in requirements
    assert "deepagents==" in requirements


def test_every_direct_dependency_is_pinned() -> None:
    dependencies = [
        line.strip()
        for line in _read("requirements.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert dependencies
    assert all("==" in dependency or " @ " in dependency for dependency in dependencies)


def test_radar_dependency_is_fixed_to_an_immutable_commit() -> None:
    requirement = next(
        line.strip()
        for line in _read("requirements.txt").splitlines()
        if line.strip().startswith("radar-vault @ ")
    )

    assert "5f8526425def048804c6a3836d2aaf861f71a49e" in requirement
    assert "@main" not in requirement


def test_build_context_excludes_local_secrets_and_developer_state() -> None:
    dockerignore = _read(".dockerignore").splitlines()

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "!.env.example" in dockerignore
    assert ".git" in dockerignore
    assert ".venv" in dockerignore


def test_published_ports_are_bound_to_loopback_by_default() -> None:
    compose = _read("docker-compose.yml")

    assert '"${APP_BIND_ADDRESS:-127.0.0.1}:${APP_PORT:-8000}:8000"' in compose
    assert '"127.0.0.1:${POSTGRES_EXPOSED_PORT:-5432}:5432"' in compose


def test_postgres_has_no_usable_password_default() -> None:
    compose = _read("docker-compose.yml")

    assert "POSTGRES_PASSWORD:?" in compose
    assert "change-me" not in compose
