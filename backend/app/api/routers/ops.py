"""Enterprise operations endpoints: audit trail, opportunities, comparisons and
per-user alert subscriptions."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas import (
    AlertSubscriptionIn,
    AlertSubscriptionOut,
    AuditLogEntryOut,
)
from app.core.errors import NotFoundError
from app.db.models import AlertSubscription
from app.services import audit_service, comparison_service, opportunity_engine

router = APIRouter(tags=["operations"])


@router.get("/audit", response_model=list[AuditLogEntryOut], summary="Recent audit trail")
def list_audit(
    session: SessionDep,
    principal: PrincipalDep,
    limit: int = Query(50, ge=1, le=500),
    actor: str | None = None,
) -> list[dict]:
    return audit_service.recent(session, limit=limit, actor=actor)


@router.get("/opportunities", summary="Generic-opportunity watchlist")
def opportunities(session: SessionDep, limit: int = Query(25, ge=1, le=200)) -> dict:
    return opportunity_engine.opportunity_summary(session)


@router.get("/comparison/documents/{before_id}/{after_id}", summary="Diff two source document versions")
def compare_documents(before_id: str, after_id: str, session: SessionDep) -> dict:
    return comparison_service.diff_between_documents(session, before_id, after_id)


# ---- Alert subscriptions (per authenticated user) ----


@router.get("/subscriptions", response_model=list[AlertSubscriptionOut], summary="My alert subscriptions")
def list_subscriptions(session: SessionDep, principal: PrincipalDep) -> list[AlertSubscription]:
    return list(
        session.scalars(
            select(AlertSubscription)
            .where(AlertSubscription.user_email == principal.username)
            .order_by(AlertSubscription.created_at.desc())
        )
    )


@router.post(
    "/subscriptions",
    response_model=AlertSubscriptionOut,
    status_code=201,
    summary="Create an alert subscription",
)
def create_subscription(
    payload: AlertSubscriptionIn,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> AlertSubscription:
    subscription = AlertSubscription(
        user_id=principal.user_id or principal.username,
        user_email=principal.username,
        name=payload.name,
        modules=payload.modules,
        sponsors=payload.sponsors,
        drugs=payload.drugs,
        patents=payload.patents,
        therapy_areas=payload.therapy_areas,
        min_priority=payload.min_priority,
        channels=payload.channels,
        is_active=payload.is_active,
    )
    session.add(subscription)
    session.flush()
    audit_service.record(
        session,
        actor=principal.username,
        action="create_subscription",
        resource_type="alert_subscription",
        resource_id=subscription.id,
        detail={"modules": payload.modules},
        request=request,
    )
    session.commit()
    return subscription


@router.delete("/subscriptions/{subscription_id}", summary="Delete an alert subscription")
def delete_subscription(
    subscription_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> dict:
    subscription = session.get(AlertSubscription, subscription_id)
    if subscription is None or subscription.user_email != principal.username:
        raise NotFoundError("Subscription not found")
    session.delete(subscription)
    audit_service.record(
        session,
        actor=principal.username,
        action="delete_subscription",
        resource_type="alert_subscription",
        resource_id=subscription_id,
        request=request,
    )
    session.commit()
    return {"deleted": True}
