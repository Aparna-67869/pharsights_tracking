"""Alert channels: dashboard, email, Microsoft Teams, Slack.

Every channel is optional. When it is not configured the send is recorded as
``skipped`` rather than failing, so the alert pipeline never breaks because a
webhook is missing. The dashboard channel is always available.
"""

from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.text import clean_text

log = get_logger(__name__)


@dataclass
class DeliveryResult:
    channel: str
    status: str  # sent | skipped | failed
    recipient: str | None = None
    error: str | None = None


class Channel(Protocol):
    name: str

    def configured(self) -> bool: ...

    def send(self, alert: dict[str, Any]) -> DeliveryResult: ...


def _priority_emoji(label: str) -> str:
    return {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "⚪",
    }.get(label, "⚪")


def _format_text(alert: dict[str, Any]) -> str:
    lines = [
        f"{_priority_emoji(alert.get('priority_label', ''))} "
        f"[{str(alert.get('priority_label', '')).upper()}] {alert.get('title', '')}",
        "",
        alert.get("message", ""),
    ]
    details = []
    if alert.get("drug_name"):
        details.append(f"Drug: {alert['drug_name']}")
    if alert.get("sponsor_name"):
        details.append(f"Sponsor: {alert['sponsor_name']}")
    if alert.get("patent_number"):
        details.append(f"Patent: {alert['patent_number']}")
    if alert.get("module"):
        details.append(f"Module: {alert['module'].upper()}")
    if details:
        lines.extend(["", " | ".join(details)])
    lines.append("")
    lines.append(f"Priority score: {alert.get('priority_score', 'n/a')}/100")
    return "\n".join(lines)


class DashboardChannel:
    """Always-on channel. Delivery is implicit: the alert row is the notification."""

    name = "dashboard"

    def configured(self) -> bool:
        return True

    def send(self, alert: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(channel=self.name, status="sent", recipient="dashboard")


class EmailChannel:
    name = "email"

    def configured(self) -> bool:
        return bool(settings.smtp_host and settings.alert_email_recipients)

    def send(self, alert: dict[str, Any]) -> DeliveryResult:
        if not self.configured():
            return DeliveryResult(channel=self.name, status="skipped", error="SMTP not configured")
        try:
            message = EmailMessage()
            message["Subject"] = (
                f"[Pharma Intel][{str(alert.get('priority_label', '')).upper()}] "
                f"{alert.get('title', '')}"
            )
            message["From"] = settings.smtp_from
            message["To"] = ", ".join(settings.alert_email_recipients)
            message.set_content(_format_text(alert))
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
            return DeliveryResult(
                channel=self.name,
                status="sent",
                recipient=",".join(settings.alert_email_recipients),
            )
        except Exception as exc:
            log.warning("email delivery failed: %s", exc)
            return DeliveryResult(channel=self.name, status="failed", error=str(exc)[:500])


class TeamsChannel:
    """Microsoft Teams incoming webhook (Adaptive Card payload)."""

    name = "teams"

    def configured(self) -> bool:
        return bool(settings.teams_webhook_url)

    def send(self, alert: dict[str, Any]) -> DeliveryResult:
        if not self.configured():
            return DeliveryResult(channel=self.name, status="skipped", error="webhook not configured")
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Medium",
                                "weight": "Bolder",
                                "text": f"{_priority_emoji(alert.get('priority_label', ''))} "
                                f"{alert.get('title', '')}",
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Priority", "value": f"{alert.get('priority_label')} "
                                     f"({alert.get('priority_score')}/100)"},
                                    {"title": "Module", "value": str(alert.get("module", "")).upper()},
                                    {"title": "Drug", "value": clean_text(alert.get("drug_name")) or "—"},
                                    {"title": "Sponsor", "value": clean_text(alert.get("sponsor_name")) or "—"},
                                    {"title": "Patent", "value": clean_text(alert.get("patent_number")) or "—"},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": alert.get("message", ""),
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }
        return self._post(payload)

    def _post(self, payload: dict[str, Any]) -> DeliveryResult:
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(settings.teams_webhook_url, json=payload)
                response.raise_for_status()
            return DeliveryResult(channel=self.name, status="sent", recipient="teams-webhook")
        except Exception as exc:
            log.warning("teams delivery failed: %s", exc)
            return DeliveryResult(channel=self.name, status="failed", error=str(exc)[:500])


class SlackChannel:
    name = "slack"

    def configured(self) -> bool:
        return bool(settings.slack_webhook_url)

    def send(self, alert: dict[str, Any]) -> DeliveryResult:
        if not self.configured():
            return DeliveryResult(channel=self.name, status="skipped", error="webhook not configured")
        payload = {
            "text": _format_text(alert),
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{_priority_emoji(alert.get('priority_label', ''))} "
                        f"{alert.get('title', '')}"[:150],
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Priority:* {alert.get('priority_label')} "
                         f"({alert.get('priority_score')}/100)"},
                        {"type": "mrkdwn", "text": f"*Module:* {str(alert.get('module', '')).upper()}"},
                        {"type": "mrkdwn", "text": f"*Drug:* {clean_text(alert.get('drug_name')) or '—'}"},
                        {"type": "mrkdwn", "text": f"*Sponsor:* {clean_text(alert.get('sponsor_name')) or '—'}"},
                    ],
                },
                {"type": "section", "text": {"type": "mrkdwn", "text": alert.get("message", "")[:2900]}},
            ],
        }
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    settings.slack_webhook_url,
                    content=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            return DeliveryResult(channel=self.name, status="sent", recipient="slack-webhook")
        except Exception as exc:
            log.warning("slack delivery failed: %s", exc)
            return DeliveryResult(channel=self.name, status="failed", error=str(exc)[:500])


def all_channels() -> list[Channel]:
    return [DashboardChannel(), EmailChannel(), TeamsChannel(), SlackChannel()]
