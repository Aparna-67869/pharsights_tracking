"""Real-time alert management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, func, select

from app.alerts.engine import alert_summary
from app.api.deps import PrincipalDep, SessionDep, audit, require_scope
from app.api.schemas import AlertOut, AlertUpdate, Page
from app.core.errors import NotFoundError
from app.db.base import utcnow
from app.db.models import Alert, NotificationLog

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(require_scope("read:data"))])


@router.get("", response_model=Page[AlertOut], summary="List alerts")
def list_alerts(
    session: SessionDep,
    module: str | None = None,
    priority_label: str | None = None,
    status: str | None = Query("open", description="open | acknowledged | resolved | dismissed"),
    min_score: int | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[AlertOut]:
    stmt = select(Alert)
    if module:
        stmt = stmt.where(Alert.module == module)
    if priority_label:
        stmt = stmt.where(Alert.priority_label == priority_label)
    if status and status != "all":
        stmt = stmt.where(Alert.status == status)
    if min_score is not None:
        stmt = stmt.where(Alert.priority_score >= min_score)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(Alert.priority_score), desc(Alert.created_at))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return Page.build([AlertOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/summary", summary="Alert counts by priority")
def summary(session: SessionDep) -> dict:
    return alert_summary(session)


@router.get("/{alert_id}", response_model=AlertOut, summary="Get one alert")
def get_alert(alert_id: str, session: SessionDep) -> AlertOut:
    row = session.get(Alert, alert_id)
    if row is None:
        raise NotFoundError("Alert not found")
    return AlertOut.model_validate(row)


@router.patch(
    "/{alert_id}",
    response_model=AlertOut,
    summary="Update an alert (acknowledge, resolve, dismiss)",
    dependencies=[__import__("fastapi").Depends(require_scope("write:alerts"))],
)
def update_alert(
    alert_id: str,
    payload: AlertUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> AlertOut:
    row = session.get(Alert, alert_id)
    if row is None:
        raise NotFoundError("Alert not found")
    changes = payload.model_dump(exclude_unset=True)
    if payload.status:
        row.status = payload.status
        if payload.status in {"acknowledged", "resolved", "dismissed"}:
            row.resolved_at = utcnow()
            row.acknowledged_by = payload.acknowledged_by or principal.username
    if payload.acknowledged_by:
        row.acknowledged_by = payload.acknowledged_by
    audit(
        session,
        actor=principal.username,
        action="update_alert",
        resource_type="alert",
        resource_id=row.id,
        detail=changes,
        request=request,
    )
    session.commit()
    return AlertOut.model_validate(row)


@router.get("/{alert_id}/notifications", summary="Delivery attempts for an alert")
def alert_notifications(alert_id: str, session: SessionDep) -> list[dict]:
    rows = session.scalars(
        select(NotificationLog).where(NotificationLog.alert_id == alert_id).order_by(desc(NotificationLog.created_at))
    )
    return [
        {
            "channel": r.channel,
            "status": r.status,
            "recipient": r.recipient,
            "attempts": r.attempts,
            "error": r.error,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]
