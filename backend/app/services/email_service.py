"""Email delivery.

Addressed to the recipient list supplied by the caller. When the alert engine
runs for a subscribed user, that list is the user's authenticated email address,
so no per-user SMTP setup is needed. Returns a structured result instead of
raising so callers can log a skipped/failed delivery without breaking the flow.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class EmailResult:
    status: str  # sent | skipped | failed
    recipients: list[str]
    error: str | None = None


def send_email(
    *,
    subject: str,
    body: str,
    recipients: list[str],
    html: str | None = None,
) -> EmailResult:
    recipients = [r for r in recipients if r]
    if not settings.smtp_host or not recipients:
        return EmailResult(status="skipped", recipients=recipients, error="SMTP not configured")

    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from
        message["To"] = ", ".join(recipients)
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return EmailResult(status="sent", recipients=recipients)
    except Exception as exc:
        log.warning("email delivery failed: %s", exc)
        return EmailResult(status="failed", recipients=recipients, error=str(exc)[:500])
