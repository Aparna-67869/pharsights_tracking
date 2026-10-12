"""Source registry health tracking.

``_record_source_health`` is what makes "never checked" vs "checked and healthy"
visible on the Sources page. These tests pin that behaviour, including the
additive-column reconcile that lets an existing database pick up the health
columns without a destructive migration.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.collectors.base import BaseCollector, ensure_source_definition
from app.collectors.registry import SourceSpec
from app.db.base import utcnow
from app.db.models import CollectionRun, SourceDefinition
from app.db.session import engine, reconcile_schema

SPEC = SourceSpec(
    code="unit_source",
    name="Unit Test Source",
    module="ftf",
    url="https://example.test/source",
    document_kind="xlsx",
    cadence="daily",
    description="fixture",
    locator={},
)


def _definition(session, code: str = "unit_source") -> SourceDefinition:
    definition = ensure_source_definition(session, SourceSpec(**{**SPEC.__dict__, "code": code}))
    session.flush()
    return definition


class _StubCollector(BaseCollector):
    """A collector with no network behaviour, only the health bookkeeping."""

    def collect(self, session):  # pragma: no cover - not exercised
        raise NotImplementedError


def _collector() -> _StubCollector:
    return _StubCollector(SPEC)


def test_successful_run_sets_success_timestamp_and_clears_error(session):
    definition = _definition(session)
    definition.last_error = "previous failure"
    session.flush()

    run = CollectionRun(
        source_code="unit_source",
        status="success",
        started_at=utcnow(),
        finished_at=utcnow(),
        error=None,
    )
    session.add(run)
    session.flush()

    _collector()._record_source_health(session, run)
    session.flush()

    session.refresh(definition)
    assert definition.last_checked_at is not None
    assert definition.last_success_at is not None
    assert definition.last_error is None


def test_failed_run_records_error_and_leaves_success_untouched(session):
    definition = _definition(session)
    run = CollectionRun(
        source_code="unit_source",
        status="failed",
        started_at=utcnow(),
        finished_at=utcnow(),
        error="HTTP 503 from upstream",
    )
    session.add(run)
    session.flush()

    _collector()._record_source_health(session, run)
    session.flush()

    session.refresh(definition)
    assert definition.last_checked_at is not None
    assert definition.last_error == "HTTP 503 from upstream"
    # A failure must not claim a successful check.
    assert definition.last_success_at is None


def test_reconcile_schema_adds_health_columns(session):
    """The additive reconcile is what upgrades a pre-existing database in place."""
    definition = _definition(session, code="reconcile_probe")
    session.flush()

    reconcile_schema()

    columns = {col["name"] for col in inspect(engine).get_columns("source_definitions")}
    assert {"last_checked_at", "last_success_at", "last_error"} <= columns
    session.refresh(definition)
