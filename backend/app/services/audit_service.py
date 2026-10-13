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
