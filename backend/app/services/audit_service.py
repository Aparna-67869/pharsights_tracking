"""Audit trail service.

Wraps :func:`app.api.deps.audit` with higher-level helpers the routers call, so
the recorded action names stay consistent across the platform. All writes are
best-effort: an audit failure must never break the request that triggered it.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.api.deps import audit as _audit
from app.core.logging import get_logger
from app.db.models import AuditLog

log = get_logger(__name__)


def record(
    session: Session,
    *,
    actor: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Write an audit row in the caller's transaction, best-effort.

    Shares the caller's session so the row commits atomically with the action it
    records and never tries to take a second write lock the caller already holds.
    """
    try:
        _audit(
            session,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            request=request,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("audit write failed for %s/%s: %s", resource_type, action, exc)


def build_entry(
    *,
    actor: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Build (but do not persist) an audit row."""
    return AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )


def record_detached(
    *,
    actor: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Write an audit row on a dedicated, retrying session.

    For requests that only read (e.g. login): they hold no write lock, so a
    separate session can write the row without the read-then-write snapshot
    upgrade that SQLite refuses. Best-effort — a lock is retried, never raised.
    """
    from app.db.session import resilient_write

    entry = build_entry(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        request=request,
    )
    resilient_write(lambda s: s.add(entry))


def record_search(session: Session, *, actor: str | None, query: str, total: int, request: Request | None = None) -> None:
    record(
        session,
        actor=actor,
        action="search",
        resource_type="search",
        detail={"query": query, "total": total},
        request=request,
    )


def record_view(session: Session, *, actor: str | None, view: str, request: Request | None = None) -> None:
    record(session, actor=actor, action="view", resource_type=view, request=request)


def record_export(session: Session, *, actor: str | None, dataset: str, row_count: int | None = None, request: Request | None = None) -> None:
    record(
        session,
        actor=actor,
        action="export",
        resource_type=dataset,
        detail={"rows": row_count},
        request=request,
    )


def record_alert_action(session: Session, *, actor: str | None, alert_id: str, status: str, request: Request | None = None) -> None:
    record(
        session,
        actor=actor,
        action="alert_" + status,
        resource_type="alert",
        resource_id=alert_id,
        request=request,
    )


def last_processed_at(session: Session, module: str) -> str | None:
    """When a module's data was last successfully refreshed (pipeline finish)."""
    from sqlalchemy import select

    from app.db.models import PipelineRun

    run = session.scalars(
        select(PipelineRun)
        .where(PipelineRun.status.in_(("completed", "completed_with_errors")))
        .order_by(PipelineRun.finished_at.desc())
    ).first()
    return run.finished_at.isoformat() if run and run.finished_at else None


def recent(session: Session, *, limit: int = 50, actor: str | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.db.models import AuditLog

    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "detail": row.detail,
            "ip_address": row.ip_address,
            "created_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in session.scalars(stmt)
    ]
