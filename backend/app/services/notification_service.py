"""Notification orchestration.

Given an alert and a recipient context, decides which channels fire and records
each attempt. Recipients are resolved from the authenticated identity:
``context.email`` is the user's Entra ID / platform sign-in address, so email and
Teams are addressed automatically with no per-user configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import NotificationLog
from app.services import email_service, teams_service

log = get_logger(__name__)


@dataclass
class RecipientContext:
    email: str | None = None
    teams_id: str | None = None
    graph_token: str | None = None
    channels: list[str] = field(default_factory=lambda: ["dashboard", "email", "teams"])


@dataclass
class DeliveryOutcome:
    channel: str
    status: str
    recipient: str | None = None
    error: str | None = None


def _subject(alert: dict[str, Any]) -> str:
    return f"[Pharma Intel][{str(alert.get('priority_label', '')).upper()}] {alert.get('title', '')}"


def _body(alert: dict[str, Any]) -> str:
    lines = [alert.get("title", ""), "", alert.get("message", "")]
    details = []
    for label, key in (("Drug", "drug_name"), ("Sponsor", "sponsor_name"), ("Patent", "patent_number")):
        if alert.get(key):
            details.append(f"{label}: {alert[key]}")
    if details:
        lines.extend(["", " | ".join(details)])
    lines.append("")
    lines.append(f"Priority score: {alert.get('priority_score', 'n/a')}/100")
    return "\n".join(lines)


def notify(
    session: Session,
    alert: dict[str, Any],
    context: RecipientContext | None = None,
) -> list[DeliveryOutcome]:
    """Send an alert over the requested channels and log every attempt."""
    context = context or RecipientContext()
    outcomes: list[DeliveryOutcome] = []
    channels_sent: list[str] = []

    for channel in context.channels:
        outcome = _deliver(channel, alert, context)
        outcomes.append(outcome)
        if outcome.status == "sent":
            channels_sent.append(channel)
        session.add(
            NotificationLog(
                alert_id=alert.get("id"),
                channel=outcome.channel,
                recipient=outcome.recipient,
                status=outcome.status,
                attempts=1 if outcome.status != "skipped" else 0,
                error=outcome.error,
                payload={"priority": alert.get("priority_label")},
            )
        )

    alert["channels_sent"] = channels_sent
    session.flush()
    return outcomes


def _deliver(channel: str, alert: dict[str, Any], context: RecipientContext) -> DeliveryOutcome:
    if channel == "dashboard":
        return DeliveryOutcome(channel="dashboard", status="sent", recipient="dashboard")

    if channel == "email":
        recipients = [context.email] if context.email else list(settings.alert_email_recipients)
        result = email_service.send_email(subject=_subject(alert), body=_body(alert), recipients=recipients)
        return DeliveryOutcome(channel="email", status=result.status, recipient=",".join(result.recipients), error=result.error)

    if channel == "teams":
        result = teams_service.send_teams(
            alert, user_email=context.email, graph_token=context.graph_token
        )
        return DeliveryOutcome(channel="teams", status=result.status, recipient=result.target, error=result.error)

    return DeliveryOutcome(channel=channel, status="skipped", error="unknown channel")
