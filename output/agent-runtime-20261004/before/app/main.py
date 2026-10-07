"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.radar import radar_api_repository
from app.api.radar import router as radar_api_router
from app.api.telegram import router as telegram_router
from app.application.scheduling import SchedulerDependencies, run_scheduler
from app.application.telegram import run_repository, thread_repository, update_repository
from app.config import settings
from app.observability import configure_logging
from app.tools.dependencies import (
    close_calendar_service,
    close_email_service,
    close_memory_service,
    close_radar_operation_repository,
    close_radar_service,
    close_scheduled_jobs,
    close_services,
    close_web_page_client,
    initialize_radar,
    scheduled_jobs,
)

logger = logging.getLogger(__name__)

#: How long shutdown waits for an in-flight dispatch to finish on its own. A
#: job that is mid-delivery should be allowed to complete; one that hangs must
#: not hold the container open, and its slot is recovered as ``unknown`` by the
#: next process to start.
SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS = 10.0


@asynccontextmanager
async def application_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Run the scheduler alongside the API and release clients on shutdown."""

    stop = asyncio.Event()
    scheduler: asyncio.Task[None] | None = None
    initialize_radar()
    if settings.scheduler_enabled:
        scheduler = asyncio.create_task(
            run_scheduler(
                SchedulerDependencies(
                    jobs=scheduled_jobs(),
                    threads=thread_repository,
                    runs=run_repository,
                ),
                stop=stop,
            ),
            name="scheduled-jobs",
        )
    else:
        logger.info("schedule.loop.disabled")
    try:
        yield
    finally:
        if scheduler is not None:
            stop.set()
            try:
                await asyncio.wait_for(scheduler, timeout=SCHEDULER_SHUTDOWN_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("schedule.loop.shutdown_timeout")
                scheduler.cancel()
                with suppress(asyncio.CancelledError):
                    await scheduler
        close_services()
        close_calendar_service()
        close_email_service()
        close_web_page_client()
        update_repository.close()
        run_repository.close()
        thread_repository.close()
        close_scheduled_jobs()
        close_memory_service()
        radar_api_repository.close()
        close_radar_operation_repository()
        close_radar_service()


def create_app() -> FastAPI:
    """Build and configure the HTTP application."""

    configure_logging(settings.log_level)
    application = FastAPI(
        title="Personal Chief of Staff",
        version="0.1.0",
        description="Operational personal assistant foundation.",
        lifespan=application_lifespan,
    )
    application.include_router(health_router)
    application.include_router(telegram_router)
    application.include_router(radar_api_router)
    return application


app = create_app()
