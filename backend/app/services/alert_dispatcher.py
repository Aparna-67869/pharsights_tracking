"""Alert dispatch coordinator.

Bridges the alert engine to the notification service. For each open alert it
resolves the matching subscriptions, and for every subscriber sends email +
Teams to the subscriber's authenticated address, plus the always-on dashboard
notification.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Alert, AlertSubscription, User
from app.services import notification_service

log = get_logger(__name__)


def _matches(subscription: AlertSubscription, alert: Alert) -> bool:
    if not subscription.is_active:
        return False
    if alert.priority_score < subscription.min_priority:
        return False

    def ok(values: list[str] | None, candidate: str | None) -> bool:
        if not values:
            return True
        if not candidate:
            return False
        lowered = candidate.casefold()
        return any(value.casefold() in lowered or lowered in value.casefold() for value in values)

    return (
        ok(subscription.modules, alert.module)
        and ok(subscription.sponsors, alert.sponsor_name)
        and ok(subscription.drugs, alert.drug_name)
        and ok(subscription.therapy_areas, None)  # reserved for therapy-area tagging
    )


def dispatch_to_subscribers(session: Session, alert: Alert) -> dict[str, Any]:
    """Notify every subscription that matches the alert."""
    payload = {
        "id": alert.id,
        "title": alert.title,
        "message": alert.message,
        "module": alert.module,
        "event_type": alert.event_type,
        "priority_label": alert.priority_label,
        "priority_score": alert.priority_score,
        "drug_name": alert.drug_name,
        "sponsor_name": alert.sponsor_name,
        "patent_number": alert.patent_number,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    subscriptions = list(session.scalars(select(AlertSubscription).where(AlertSubscription.is_active.is_(True))))
    notified = 0
    for subscription in subscriptions:
        if not _matches(subscription, alert):
            continue
        user = session.scalars(select(User).where(User.id == subscription.user_id)).first()
        email = subscription.user_email or (user.email if user else None)
        context = notification_service.RecipientContext(
            email=email,
            channels=list(subscription.channels or ["dashboard"]),
        )
        notification_service.notify(session, payload, context)
        notified += 1

    log.info("alert dispatcher: notified %d subscriber(s) for alert %s", notified, alert.id)
    return {"subscribers_notified": notified, "channels_sent": payload.get("channels_sent", [])}
