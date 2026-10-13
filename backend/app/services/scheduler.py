"""Background monitoring scheduler, running in the API process.

The SOP requires the platform to monitor the sources *automatically* — a
dashboard a user has to prompt is not a monitoring system. This runs the real
collection pipeline on a cadence in a daemon thread, so every source is fetched,
diffed, analysed and alerted on without anyone visiting the site.

Production runs the same pipeline from the Airflow DAGs in ``backend/dags``;
this in-process loop is the local/dev equivalent and is disabled by setting
``SCHEDULER_ENABLED=false``. It deliberately serialises runs (a file lock) so
the API-triggered path and the scheduled path can never overlap.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_lock = threading.Lock()
_last_run_at: datetime | None = None
_next_run_at: datetime | None = None
_last_result: dict | None = None


def status() -> dict:
    """Observability for the Operations page: is auto-monitoring on and when next."""
    return {
        "enabled": settings.scheduler_enabled,
        "interval_minutes": settings.scheduler_interval_minutes,
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "next_run_at": _next_run_at.isoformat() if _next_run_at else None,
        "last_result": _last_result,
    }


def _run_once() -> None:
    global _last_run_at, _last_result
    if not _lock.acquire(blocking=False):
        log.warning("scheduler: previous run still in progress, skipping tick")
        return
    try:
        from app.services.pipeline import run_pipeline

        started = datetime.now(UTC)
        log.info("scheduler: starting automatic source sweep")
        result = run_pipeline(trigger="scheduled")
        _last_run_at = started
        _last_result = {
            "status": result.status,
            "sources_checked": result.sources_checked,
            "sources_changed": result.sources_changed,
            "changes_detected": result.changes_detected,
            "insights_generated": result.insights_generated,
            "alerts_created": result.alerts_created,
            "duration_ms": result.duration_ms,
        }
        log.info(
            "scheduler: sweep complete — %d changed, %d new changes, %d alerts in %d ms",
            result.sources_changed,
            result.changes_detected,
            result.alerts_created,
            result.duration_ms,
        )
    except Exception as exc:  # pragma: no cover - the loop must never die
        log.exception("scheduler: sweep failed: %s", exc)
    finally:
        _lock.release()


def _loop() -> None:
    global _next_run_at
    interval = max(5, settings.scheduler_interval_minutes) * 60
    # Small initial delay so app startup (schema, first requests) settles.
    time.sleep(20)
    while True:
        # Publish the next scheduled sweep up front so an operator sees a live
        # target even while the first sweep is still running (it is set again
        # after the sweep below, when the exact completion time is known).
        _next_run_at = datetime.now(UTC) + timedelta(seconds=interval)
        _run_once()
        _next_run_at = datetime.now(UTC) + timedelta(seconds=interval)
        time.sleep(interval)


def start() -> None:
    """Start the scheduler thread once, if enabled."""
    if not settings.scheduler_enabled:
        log.info("scheduler: disabled (SCHEDULER_ENABLED=false)")
        return
    thread = threading.Thread(target=_loop, name="pharma-scheduler", daemon=True)
    thread.start()
    log.info(
        "scheduler: started — automatic sweep every %d minutes",
        settings.scheduler_interval_minutes,
    )
