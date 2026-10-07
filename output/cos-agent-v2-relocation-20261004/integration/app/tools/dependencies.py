"""Thread-safe lifecycle for the services used by agent tools.

The model can only see plain tool arguments, so infrastructure dependencies
cannot be injected through function parameters.  This module provides that
composition seam while retaining explicit ownership: production constructs
one Notion client shared by both services, and the application lifespan closes
the client. Tests may install deterministic services without transferring
ownership of their fake client.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

from app.config import settings
from app.database.radar_operations import RadarOperationRepository
from app.database.scheduled_jobs import ScheduledJobRepository
from app.errors import ConfigurationError
from app.integrations.gmail import GMAIL_BASE_URL, GmailClient
from app.integrations.google_api import GoogleAPIClient
from app.integrations.google_calendar import GOOGLE_CALENDAR_BASE_URL, GoogleCalendarClient
from app.integrations.google_oauth import GoogleOAuthTokenProvider
from app.integrations.notion_client import create_notion_client
from app.integrations.web_page import WebPageClient, create_web_page_client
from app.services.calendar_service import CalendarService
from app.services.email_service import EmailService
from app.services.memory_service import MemoryService, create_memory_service
from app.services.project_service import ProjectService, create_project_service
from app.services.reference_service import ReferenceService, create_reference_service
from app.services.task_service import TaskService, create_task_service

if TYPE_CHECKING:
    from app.services.radar_service import RadarService

from app.schemas.radar import RadarPreflightReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolServices:
    """The immutable dependency set consumed by every tool."""

    tasks: TaskService
    projects: ProjectService
    # Optional because its data source is created *for* this application
    # (ADR-013) and may not exist yet. ``None`` means the reference library is
    # not configured, and ``save_reference`` is left off the agent's tools
    # rather than failing at call time.
    references: ReferenceService | None = None
    close: Callable[[], None] | None = None


_services: ToolServices | None = None
_services_lock = RLock()

_scheduled_jobs: ScheduledJobRepository | None = None
_scheduled_jobs_lock = RLock()

_web_page_client: WebPageClient | None = None
_web_page_client_lock = RLock()

_memory_service: MemoryService | None = None
_memory_service_lock = RLock()

_calendar_service: CalendarService | None = None
_calendar_close: Callable[[], None] | None = None
_calendar_service_lock = RLock()

_email_service: EmailService | None = None
_email_close: Callable[[], None] | None = None
_email_service_lock = RLock()

_radar_service: RadarService | None = None
_radar_report = RadarPreflightReport(state="not_started")
_radar_initialized = False
_radar_service_lock = RLock()

_radar_operation_repository: RadarOperationRepository | None = None
_radar_operation_repository_lock = RLock()


def radar_configured() -> bool:
    """Whether every trusted RADAR startup input is present."""

    return settings.radar_configured


def initialize_radar() -> RadarPreflightReport:
    """Run the optional RADAR preflight once without affecting application startup."""

    global _radar_initialized, _radar_report, _radar_service
    with _radar_service_lock:
        if _radar_initialized:
            return _radar_report

        _radar_initialized = True
        if not settings.radar_enabled:
            _radar_report = RadarPreflightReport(state="disabled")
            _log_radar_report(_radar_report)
            return _radar_report

        if not radar_configured():
            _radar_report = RadarPreflightReport(
                state="degraded",
                context=settings.radar_context or None,
                error_code="incomplete_configuration",
            )
            _log_radar_report(_radar_report)
            return _radar_report

        try:
            service = _create_radar_service()
        except Exception as exc:  # noqa: BLE001 - optional startup must remain degraded
            # The integration deliberately exports only a stable code. A truly
            # unexpected exception is classified here without logging its
            # message or traceback, either of which could carry ABox content.
            from app.errors import RadarStartupError

            code = exc.code if isinstance(exc, RadarStartupError) else "unexpected_error"
            _radar_report = RadarPreflightReport(
                state="degraded",
                context=settings.radar_context,
                error_code=code,
            )
            _log_radar_report(_radar_report)
            return _radar_report

        _radar_service = service
        _radar_report = service.preflight_report
        _log_radar_report(_radar_report)
        return _radar_report


def radar_service() -> RadarService:
    """Return the lazy validated RADAR service or fail closed."""

    initialize_radar()
    with _radar_service_lock:
        if _radar_service is None:
            raise ConfigurationError("The RADAR integration is unavailable.")
        return _radar_service


def radar_preflight_report() -> RadarPreflightReport:
    """Return current safe state without forcing package import or ABox access."""

    global _radar_report
    with _radar_service_lock:
        if _radar_service is not None:
            _radar_report = _radar_service.preflight_report
        return _radar_report


def radar_operation_repository() -> RadarOperationRepository:
    """Return the durable proposal store, outside model-controlled arguments."""

    global _radar_operation_repository
    with _radar_operation_repository_lock:
        if _radar_operation_repository is None:
            _radar_operation_repository = RadarOperationRepository()
        return _radar_operation_repository


def configure_radar_operation_repository(repository: RadarOperationRepository) -> None:
    """Install an isolated proposal store for deterministic tests."""

    global _radar_operation_repository
    with _radar_operation_repository_lock:
        previous = _radar_operation_repository
        _radar_operation_repository = repository
    if previous is not None and previous is not repository:
        previous.close()


def close_radar_operation_repository() -> None:
    """Release the RADAR proposal store with the other optional services."""

    global _radar_operation_repository
    with _radar_operation_repository_lock:
        previous = _radar_operation_repository
        _radar_operation_repository = None
    if previous is not None:
        previous.close()


def configure_radar_service(
    service: RadarService,
    *,
    report: RadarPreflightReport | None = None,
) -> None:
    """Install a deterministic RADAR service for tests."""

    global _radar_initialized, _radar_report, _radar_service
    with _radar_service_lock:
        previous = _radar_service
        _radar_service = service
        _radar_report = report or service.preflight_report
        _radar_initialized = True
    if previous is not None and previous is not service:
        previous.close()


def close_radar_service() -> None:
    """Release the RADAR runtime and reset lazy startup state."""

    global _radar_initialized, _radar_report, _radar_service
    with _radar_service_lock:
        previous = _radar_service
        _radar_service = None
        _radar_report = RadarPreflightReport(state="not_started")
        _radar_initialized = False
    if previous is not None:
        previous.close()


def _create_radar_service() -> RadarService:
    # Imported only after RADAR_ENABLED and the complete configuration gate.
    # Keeping this seam local is what lets an ordinary install run without
    # importing radar_vault at all.
    from app.services.radar_service import create_radar_service

    if settings.radar_backend == "command-layer":
        from app.integrations.radar_commands import RadarCommandRuntime
        from app.services.radar_service import RadarService

        assert settings.radar_command_url and settings.radar_command_token
        runtime = RadarCommandRuntime(
            base_url=settings.radar_command_url,
            token=settings.radar_command_token.get_secret_value(),
            context=settings.radar_context or "",
            person_id=settings.radar_person_id or "",
            allowed_tbox_versions=settings.radar_allowed_tbox_version_set,
        )
        return RadarService(
            runtime=runtime,
            context=settings.radar_context or "",
            person_id=settings.radar_person_id or "",
            telegram_user_id=settings.telegram_allowed_user_id or 0,
            write_operations=settings.radar_write_operation_set
            if settings.radar_writes_enabled
            else frozenset(),
        )
    assert settings.radar_vault_path is not None
    assert settings.radar_context is not None
    assert settings.radar_person_id is not None
    assert settings.telegram_allowed_user_id is not None
    return create_radar_service(
        vault_path=settings.radar_vault_path,
        context=settings.radar_context,
        person_id=settings.radar_person_id,
        telegram_user_id=settings.telegram_allowed_user_id,
        allowed_tbox_versions=settings.radar_allowed_tbox_version_set,
        write_operations=(
            settings.radar_write_operation_set if settings.radar_writes_enabled else frozenset()
        ),
        manager_contexts=settings.radar_manager_context_set,
    )


def _log_radar_report(report: RadarPreflightReport) -> None:
    fields = {
        "radar_state": report.state,
        "radar_context": report.context,
        "package_version": report.package_version,
        "tbox_version": report.tbox_version,
        "abox_schema_version": report.abox_schema_version,
        "entity_count": report.entity_count,
        "validation_error_count": report.validation_error_count,
        "error_code": report.error_code,
    }
    if report.state == "degraded":
        logger.warning("radar.preflight.degraded", extra=fields)
    else:
        logger.info(f"radar.preflight.{report.state}", extra=fields)


def scheduled_jobs() -> ScheduledJobRepository:
    """Return the shared scheduled-job store, building it on first use.

    Separate from :class:`ToolServices` because it has a different lifetime and
    a different owner: the reminder tools read it, and so does the dispatcher
    in the application lifespan, which runs with no tool call in sight.
    """

    global _scheduled_jobs
    with _scheduled_jobs_lock:
        if _scheduled_jobs is None:
            _scheduled_jobs = ScheduledJobRepository()
        return _scheduled_jobs


def configure_scheduled_jobs(repository: ScheduledJobRepository) -> None:
    """Install a store for tests, without transferring lifecycle ownership."""

    global _scheduled_jobs
    with _scheduled_jobs_lock:
        _scheduled_jobs = repository


def close_scheduled_jobs() -> None:
    """Release the scheduled-job connection pool."""

    global _scheduled_jobs
    with _scheduled_jobs_lock:
        previous = _scheduled_jobs
        _scheduled_jobs = None
    if previous is not None:
        previous.close()


def memory_service() -> MemoryService:
    """Return the shared memory service, building it on first use.

    Separate from :class:`ToolServices` for the same reason as the job store:
    it is backed by this application's own database rather than by Notion, and
    the application layer reads it too — once per run, to build the block the
    model sees, with no tool call in sight.
    """

    global _memory_service
    with _memory_service_lock:
        if _memory_service is None:
            _memory_service = create_memory_service()
        return _memory_service


def configure_memory_service(service: MemoryService) -> None:
    """Install a service for tests, without transferring lifecycle ownership."""

    global _memory_service
    with _memory_service_lock:
        _memory_service = service


def close_memory_service() -> None:
    """Release the memory store's connection pool."""

    global _memory_service
    with _memory_service_lock:
        previous = _memory_service
        _memory_service = None
    if previous is not None:
        previous.close()


def calendar_service() -> CalendarService:
    """Return the Calendar service when its feature and OAuth grant are configured."""

    global _calendar_service, _calendar_close
    with _calendar_service_lock:
        if _calendar_service is None:
            if not settings.google_calendar_configured:
                raise ConfigurationError("Google Calendar is disabled or not fully configured.")
            tokens = GoogleOAuthTokenProvider(
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                refresh_token=settings.google_calendar_refresh_token,
                service="calendar",
            )
            try:
                api = GoogleAPIClient(
                    base_url=GOOGLE_CALENDAR_BASE_URL,
                    service="calendar",
                    token_provider=tokens,
                )
                client = GoogleCalendarClient(api)
                _calendar_service = CalendarService(client, timezone=settings.app_timezone)
                _calendar_close = lambda: (client.close(), tokens.close())
            except BaseException:
                tokens.close()
                raise
        return _calendar_service


def configure_calendar_service(service: CalendarService) -> None:
    """Install a deterministic Calendar service for tests."""

    global _calendar_service, _calendar_close
    with _calendar_service_lock:
        previous_close = _calendar_close
        _calendar_service = service
        _calendar_close = None
    if previous_close is not None:
        previous_close()


def close_calendar_service() -> None:
    """Release Calendar HTTP pools and clear the lazy service."""

    global _calendar_service, _calendar_close
    with _calendar_service_lock:
        close = _calendar_close
        _calendar_service = None
        _calendar_close = None
    if close is not None:
        close()


def email_service() -> EmailService:
    """Return the Gmail service when its feature and OAuth grant are configured."""

    global _email_service, _email_close
    with _email_service_lock:
        if _email_service is None:
            if not settings.gmail_configured:
                raise ConfigurationError("Gmail is disabled or not fully configured.")
            tokens = GoogleOAuthTokenProvider(
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                refresh_token=settings.google_gmail_refresh_token,
                service="gmail",
            )
            try:
                api = GoogleAPIClient(
                    base_url=GMAIL_BASE_URL,
                    service="gmail",
                    token_provider=tokens,
                )
                client = GmailClient(api)
                _email_service = EmailService(client, timezone=settings.app_timezone)
                _email_close = lambda: (client.close(), tokens.close())
            except BaseException:
                tokens.close()
                raise
        return _email_service


def configure_email_service(service: EmailService) -> None:
    """Install a deterministic Gmail service for tests."""

    global _email_service, _email_close
    with _email_service_lock:
        previous_close = _email_close
        _email_service = service
        _email_close = None
    if previous_close is not None:
        previous_close()


def close_email_service() -> None:
    """Release Gmail HTTP pools and clear the lazy service."""

    global _email_service, _email_close
    with _email_service_lock:
        close = _email_close
        _email_service = None
        _email_close = None
    if close is not None:
        close()


def web_page_client() -> WebPageClient:
    """Return the shared web reader, building it on first use.

    Kept apart from :class:`ToolServices` for the same reason as the job
    store: it reaches an entirely different network — arbitrary public sites
    rather than one authenticated API — and shares no credential with Notion.
    Nothing here is configured, so there is no unconfigured state to degrade
    to: the client either fetches or raises a ``WebFetchError`` the tool
    envelope reports.
    """

    global _web_page_client
    with _web_page_client_lock:
        if _web_page_client is None:
            _web_page_client = create_web_page_client()
        return _web_page_client


def configure_web_page_client(client: WebPageClient) -> None:
    """Install a reader for tests, without transferring lifecycle ownership."""

    global _web_page_client
    with _web_page_client_lock:
        _web_page_client = client


def close_web_page_client() -> None:
    """Release the reader's connection pool."""

    global _web_page_client
    with _web_page_client_lock:
        previous = _web_page_client
        _web_page_client = None
    if previous is not None:
        previous.close()


def task_service() -> TaskService:
    """Return the shared ``TaskService``, building the full set on first use."""

    return _get_or_create_services().tasks


def project_service() -> ProjectService:
    """Return the shared ``ProjectService``, building the full set on first use."""

    return _get_or_create_services().projects


def reference_service() -> ReferenceService:
    """Return the shared ``ReferenceService``, or fail if it is not configured.

    Reaching this with no reference library configured means ``save_reference``
    was published when it should not have been; the error names the setting
    rather than pretending the save is merely unavailable.
    """

    service = _get_or_create_services().references
    if service is None:
        raise ConfigurationError("The Notion reference data source id is not configured.")
    return service


def reference_library_configured() -> bool:
    """Whether the reference library exists, without building any service.

    Read while the agent's tool list is assembled, which happens before any
    Notion call — so this deliberately consults the settings rather than
    forcing the whole dependency graph into existence.

    The library lives inside the Notion workspace, so it is configured only
    when Notion itself is: an id left in ``.env`` from an earlier install must
    not resurrect ``save_reference`` after the integration was turned off.
    """

    return settings.notion_configured and bool(settings.notion_reference_data_source_id)


def configure_services(
    *,
    tasks: TaskService,
    projects: ProjectService,
    references: ReferenceService | None = None,
    close: Callable[[], None] | None = None,
) -> None:
    """Atomically install a complete service set.

    The task and project services are mandatory so no concurrent tool call can
    observe a half-configured dependency graph. ``references`` is optional for
    the same reason it is optional on :class:`ToolServices`: the library may
    not exist yet. ``close`` transfers lifecycle ownership to this module;
    tests normally omit it for fakes owned by their fixture.
    """

    replacement = ToolServices(tasks=tasks, projects=projects, references=references, close=close)
    previous: ToolServices | None
    with _services_lock:
        global _services
        previous = _services
        _services = replacement
    _close_container(previous)


def close_services() -> None:
    """Close the owned client, if any, and clear the dependency set."""

    previous: ToolServices | None
    with _services_lock:
        global _services
        previous = _services
        _services = None
    _close_container(previous)


def reset_services() -> None:
    """Reset dependencies and release resources before a future lazy rebuild."""

    close_services()
    close_radar_operation_repository()


def _get_or_create_services() -> ToolServices:
    global _services
    with _services_lock:
        if _services is None:
            _services = _build_services()
        return _services


def _build_services() -> ToolServices:
    # Reached only by a Notion tool that was published, so an unconfigured
    # integration here is a wiring bug rather than a user mistake: the tool
    # should have been withheld by ``app.agent.agent._available_tools``. The
    # error names the setting instead of letting ``create_notion_client``
    # fail later on a missing token, which reads as an outage.
    if not settings.notion_configured:
        raise ConfigurationError(
            "The Notion integration is disabled or not fully configured "
            "(NOTION_ENABLED, NOTION_TOKEN, NOTION_TASK_DATA_SOURCE_ID, "
            "NOTION_PROJECT_DATA_SOURCE_ID)."
        )
    client = create_notion_client()
    try:
        tasks = create_task_service(client)
        projects = create_project_service(client)
        # Built only when configured, and on the same client as the other two:
        # an unconfigured library must not stop the task tools from working.
        references = create_reference_service(client) if reference_library_configured() else None
    except BaseException:
        client.close()
        raise
    return ToolServices(tasks=tasks, projects=projects, references=references, close=client.close)


def _close_container(container: ToolServices | None) -> None:
    if container is not None and container.close is not None:
        container.close()


__all__ = [
    "ToolServices",
    "calendar_service",
    "close_calendar_service",
    "close_email_service",
    "close_memory_service",
    "close_radar_operation_repository",
    "close_radar_service",
    "close_scheduled_jobs",
    "close_services",
    "close_web_page_client",
    "configure_calendar_service",
    "configure_email_service",
    "configure_memory_service",
    "configure_radar_operation_repository",
    "configure_radar_service",
    "configure_scheduled_jobs",
    "configure_services",
    "configure_web_page_client",
    "email_service",
    "initialize_radar",
    "memory_service",
    "project_service",
    "radar_configured",
    "radar_operation_repository",
    "radar_preflight_report",
    "radar_service",
    "reset_services",
    "scheduled_jobs",
    "task_service",
    "web_page_client",
]
