"""Centralized application configuration.

Settings are read from environment variables and, during local development,
from a repository-level ``.env`` file. Secrets are intentionally not defined
with usable defaults.

``Settings`` is not the only reader of that file. Provider SDKs — the chat
model, and any client added later — look their credential up in
``os.environ`` directly, and they have no idea a ``.env`` exists. Loading the
file into the process environment here is what makes the two agree, and it is
what keeps the model layer provider-agnostic: the application never has to
name ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY`` or any other key to pass it on.

``override=False`` keeps a real environment variable winning over the file, so
Docker and the VPS are unaffected by a ``.env`` left in the image.
"""

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = ".env"

load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    """Runtime configuration shared by the application layers."""

    app_env: str = "development"
    app_timezone: str = "America/Bahia"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    telegram_bot_token: str | None = None
    telegram_allowed_user_id: int | None = None
    telegram_webhook_secret: str | None = None

    # Shared secret for the RADAR-compatible API used by cos-mariana. The
    # routes stay unavailable until an operator configures the same key on both
    # applications.
    radar_api_key: str | None = None

    # Voice messages are rejected before any download when they announce more
    # than this. Both limits exist because a long recording is a bad way to
    # brief an assistant, and because the bytes are held in memory.
    telegram_audio_max_bytes: int = 10 * 1024 * 1024
    telegram_audio_max_duration_seconds: int = 120

    # Documents, photos and other files the user sends. The bytes are held in
    # memory while they are stored, and an attachment is kept base64-encoded in
    # the thread's workspace, so this ceiling bounds both. Telegram's own
    # ``getFile`` refuses to serve anything above 20 MB regardless.
    telegram_attachments_enabled: bool = True
    telegram_document_max_bytes: int = 5 * 1024 * 1024

    # Rich Messages (Bot API 10.1) carry headings, real lists, tables and
    # collapsible sections, and stream a draft while the agent runs. Turning
    # this off returns the assistant to plain sendMessage with parse_mode,
    # which remains the fallback whenever a rich message is refused.
    telegram_rich_messages_enabled: bool = True

    # Speech-to-text. STT_BASE_URL points at any provider implementing the
    # OpenAI-compatible /audio/transcriptions contract. STT_API_KEY falls back
    # to OPENAI_API_KEY so the same secret is not written twice.
    stt_api_key: str | None = None
    stt_base_url: str = "https://api.openai.com/v1"
    stt_model: str = "gpt-4o-mini-transcribe"
    stt_language: str = "pt"
    stt_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("STT_TIMEOUT_SECONDS", "STT_TIMEOUT_S"),
    )
    stt_max_bytes: int = 25 * 1024 * 1024

    @property
    def speech_to_text_enabled(self) -> bool:
        """Answer whether a transcription credential is available at all.

        Checked before downloading a voice message so the user is told that
        audio is off instead of waiting for a call that cannot be made.
        """

        return bool((self.stt_api_key or self.openai_api_key or "").strip())

    # Scheduled jobs. The dispatcher runs inside the API process, so turning it
    # off is how a second replica avoids competing for the same slots — and how
    # a test or a one-off container avoids firing real notifications.
    scheduler_enabled: bool = True
    scheduler_interval_seconds: float = 30.0

    # The graph recursion ceiling and the independent tool budget are separate
    # controls: one limits model/tool turns, the other prevents a long burst of
    # calls inside fewer graph steps.  Both remain intentionally bounded.
    agent_tool_call_budget: int = Field(default=16, ge=1, le=64)
    agent_identical_tool_call_budget: int = Field(default=2, ge=1, le=8)

    # RADAR is an optional domain runtime. Phase 1 deliberately exposes no
    # model tools: the flag only asks the application lifespan to load the
    # packaged normative resources, open the configured ABox and run the
    # compatibility preflight. Every value participates in the gate so a
    # half-configured install degrades without touching the package or vault.
    radar_enabled: bool = False
    radar_vault_path: str | None = None
    radar_context: str | None = None
    radar_person_id: str | None = None
    radar_allowed_tbox_versions: str = "3.2.0"
    # Phase 4 starts disabled even on an otherwise healthy RADAR integration.
    # This separate kill switch ensures a read deployment cannot begin mutating
    # its vault merely because the package exposes an operation type.
    radar_writes_enabled: bool = False
    radar_write_operations: str = "capture_issue,delegate,review,record_measurement"
    radar_manager_contexts: str = ""
    radar_approval_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    radar_intent_dedup_window_seconds: int = Field(default=86_400, ge=60, le=2_592_000)

    @property
    def radar_allowed_tbox_version_set(self) -> frozenset[str]:
        """Return the normalized, non-empty TBox compatibility allowlist."""

        return frozenset(
            version.strip()
            for version in self.radar_allowed_tbox_versions.split(",")
            if version.strip()
        )

    @property
    def radar_write_operation_set(self) -> frozenset[str]:
        """Return the small, explicit Phase 4 mutation allowlist."""

        return frozenset(
            operation.strip()
            for operation in self.radar_write_operations.split(",")
            if operation.strip()
        )

    @property
    def radar_manager_context_set(self) -> frozenset[str]:
        """Return trusted manager contexts; empty retains owner-only delegation."""

        return frozenset(
            context.strip() for context in self.radar_manager_contexts.split(",") if context.strip()
        )

    @property
    def radar_configured(self) -> bool:
        """Whether startup has every trusted input required by RADAR.

        ``TELEGRAM_ALLOWED_USER_ID`` is part of the condition because it is
        the authenticated identity from which the host constructs the RADAR
        principal. The model never supplies that identity, person or context.
        """

        return self.radar_enabled and all(
            (
                self.radar_vault_path,
                self.radar_context,
                self.radar_person_id,
                self.telegram_allowed_user_id,
                self.radar_allowed_tbox_version_set,
            )
        )

    # Notion is an optional integration, off by default, on the same terms as
    # Calendar and Gmail: a flag plus complete configuration, checked before
    # any tool is published. It was the first integration this application
    # had and for a long time the only mandatory one; making it optional is
    # what lets this repository serve as the base for a different set of tool
    # connections without carrying a dependency nobody configured.
    #
    # Turning it off removes the five task/project tools, ``save_reference``,
    # the MCP fallback (ADR-012) and the ``task-agent`` child from the
    # surface. It changes no schema and drops no data: flipping the flag back
    # on restores everything, exactly as with the two Google integrations.
    notion_enabled: bool = False
    notion_token: str | None = None

    @property
    def notion_configured(self) -> bool:
        """Whether the Notion tools can be safely published to the agent.

        The two data source ids are part of the condition, not merely the
        token: every deterministic Notion tool queries one of them, so a
        token without them publishes tools that can only fail at call time.
        """

        return self.notion_enabled and all(
            (
                self.notion_token,
                self.notion_task_data_source_id,
                self.notion_project_data_source_id,
            )
        )

    # Google OAuth is shared by Calendar and Gmail, while refresh tokens are
    # intentionally separate: each consent grant carries only the scopes of
    # one integration and can be revoked without disabling the other.
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_calendar_enabled: bool = False
    google_calendar_refresh_token: str | None = None
    gmail_enabled: bool = False
    google_gmail_refresh_token: str | None = None

    @property
    def google_calendar_configured(self) -> bool:
        """Whether Calendar can be safely published to the agent."""

        return self.google_calendar_enabled and all(
            (
                self.google_oauth_client_id,
                self.google_oauth_client_secret,
                self.google_calendar_refresh_token,
            )
        )

    @property
    def gmail_configured(self) -> bool:
        """Whether Gmail can be safely published to the agent."""

        return self.gmail_enabled and all(
            (
                self.google_oauth_client_id,
                self.google_oauth_client_secret,
                self.google_gmail_refresh_token,
            )
        )

    # Since Notion API 2025-09-03 the queryable object is a *data source*, not
    # the database that contains it. The legacy ``*_DATABASE_ID`` names are
    # still accepted so existing ``.env`` files keep working.
    notion_task_data_source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NOTION_TASK_DATA_SOURCE_ID",
            "NOTION_TASK_DATABASE_ID",
        ),
    )
    notion_project_data_source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NOTION_PROJECT_DATA_SOURCE_ID",
            "NOTION_PROJECT_DATABASE_ID",
        ),
    )

    # The people directory the task board's "RESPONSÁVEL" column points at.
    # Optional for the same reason the reference library is: an install
    # without it still runs, only without people on tasks. It is not a board
    # this application owns — the id is discoverable as the relation target
    # reported by ``python scripts/notion_schema.py``.
    notion_people_data_source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NOTION_PEOPLE_DATA_SOURCE_ID",
            "NOTION_PEOPLE_DATABASE_ID",
        ),
    )

    # The reference library (ADR-013). Optional on purpose: unlike the two
    # above, this data source is created *for* this application, so an install
    # that has not created it yet must still start — ``save_reference`` is
    # simply absent from the agent's tools until the id is configured.
    notion_reference_data_source_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "NOTION_REFERENCE_DATA_SOURCE_ID",
            "NOTION_REFERENCE_DATABASE_ID",
        ),
    )

    # Model used by the Deep Agent, as the ``provider:model`` spec understood by
    # ``init_chat_model`` (for example ``anthropic:claude-opus-5`` or
    # ``openai:gpt-5.5``). The provider decides which credential is read from
    # the environment, so no key is duplicated here.
    agent_model: str | None = None

    openai_api_key: str | None = None
    openai_model: str | None = None

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "personal_agent"
    postgres_user: str = "personal_agent"
    postgres_password: str = ""
    database_url_override: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy URL for the application PostgreSQL database."""

        if self.database_url_override:
            from sqlalchemy.engine import make_url

            url = make_url(self.database_url_override)
            if url.drivername in {"postgres", "postgresql"}:
                url = url.set(drivername="postgresql+psycopg")
            if url.database is None:
                url = url.set(database=self.postgres_db)
            return url.render_as_string(hide_password=False)

        from sqlalchemy.engine import URL

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )


settings = Settings()
