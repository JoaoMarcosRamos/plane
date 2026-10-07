"""Observe conservative workspace coordination without changing its authority guarantees."""

from contextvars import ContextVar
from functools import wraps
import logging
from time import perf_counter
from django.db import transaction
from plane.db.models import Workspace

logger = logging.getLogger("plane.radar.locks")
_sample = ContextVar("radar_lock_sample", default=None)


def lock_workspace(workspace, *, operation):
    started = perf_counter()
    result = Workspace.objects.select_for_update().get(pk=workspace.pk)
    acquired = perf_counter()
    sample = _sample.get()
    if sample is not None and sample["acquired"] is None:
        sample.update(acquired=acquired, wait_ms=(acquired - started) * 1000, operation=operation)
    logger.info("radar_workspace_lock_acquired", extra={"operation": operation, "wait_ms": (acquired - started) * 1000})
    return result


def observed_atomic(function):
    """Measure through commit/rollback for outer commands; nested calls share the outer sample."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        if _sample.get() is not None:
            with transaction.atomic():
                return function(*args, **kwargs)
        sample = {"acquired": None, "wait_ms": 0, "operation": function.__name__}
        token = _sample.set(sample)
        outcome = "rollback"
        try:
            with transaction.atomic():
                result = function(*args, **kwargs)
            outcome = "committed"
            return result
        finally:
            _sample.reset(token)
            if sample["acquired"] is not None:
                logger.info(
                    "radar_workspace_lock_finished",
                    extra={
                        "operation": sample["operation"],
                        "wait_ms": sample["wait_ms"],
                        "held_ms": (perf_counter() - sample["acquired"]) * 1000,
                        "outcome": outcome,
                        "outermost": not transaction.get_connection().in_atomic_block,
                    },
                )

    return wrapped
