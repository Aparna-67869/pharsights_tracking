"""Email delivery.

Addressed to the recipient list supplied by the caller. When the alert engine
runs for a subscribed user, that list is the user's authenticated email address,
so no per-user SMTP setup is needed. Returns a structured result instead of
raising so callers can log a skipped/failed delivery without breaking the flow.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _opens_implicit_tls() -> bool:
    if settings.smtp_use_ssl is not None:
        return settings.smtp_use_ssl
    return settings.smtp_port == 465


def deliver(message: EmailMessage) -> None:
    """Send one prepared message over the configured SMTP relay.

    Chooses implicit TLS (port 465) vs. STARTTLS (587) so any relay —
    corporate Exchange/Graph front-end or a mailbox provider — works without
    code changes. Raises on failure; callers record the error.
    """
    host = settings.smtp_host
    port = settings.smtp_port
    if _opens_implicit_tls():
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return
    with smtplib.SMTP(host, port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


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
        deliver(message)
        return EmailResult(status="sent", recipients=recipients)
    except Exception as exc:
        log.warning("email delivery failed: %s", exc)
        return EmailResult(status="failed", recipients=recipients, error=str(exc)[:500])


def _md_cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def build_change_digest(changes: list[Any], *, run_id: str | None = None) -> tuple[str, str, str]:
    """Render a sweep's detected changes as a plain-text and HTML email.

    Every change carries the field-level diff the analyst would otherwise read
    on the source page, so the message is a self-contained record of what moved.
    Returns ``(subject, text, html)``.
    """
    added = sum(1 for c in changes if c.change_type == "added")
    removed = sum(1 for c in changes if c.change_type == "removed")
    updated = sum(1 for c in changes if c.change_type == "updated")
    modules = sorted({(c.module or "").upper() for c in changes if c.module})
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    subject = (
        f"[Pharma Intel] {len(changes)} change(s) detected"
        + (f" — {', '.join(modules)}" if modules else "")
    )

    text_lines = [
        "Pharma Intelligence Platform — change digest",
        f"Run {run_id or 'n/a'} · {stamp}",
        f"{len(changes)} change(s): {added} added, {updated} updated, {removed} removed",
        "",
    ]
    html_rows: list[str] = []
    for index, change in enumerate(changes, start=1):
        fields = change.field_changes or []
        diff = "; ".join(
            f"{f.get('field')}: {f.get('before')} -> {f.get('after')}"
            for f in fields
            if isinstance(f, dict)
        )
        summary = change.summary or ""
        text_lines.append(
            f"{index}. [{(change.module or '').upper()}] {change.change_type.upper()} "
            f"{change.entity_type} · {change.source_key}"
        )
        if summary:
            text_lines.append(f"   {summary}")
        if diff:
            text_lines.append(f"   Fields: {diff}")
        text_lines.append(f"   significance {change.significance}/100 · detected {change.detected_at}")
        text_lines.append("")
        detail_html = _md_cell(summary)
        if diff:
            detail_html += f"<br><span style='color:#475569'>{_md_cell(diff)}</span>"
        html_rows.append(
            "<tr>"
            f"<td>{_md_cell((change.module or '').upper())}</td>"
            f"<td>{_md_cell(change.change_type)}</td>"
            f"<td>{_md_cell(change.entity_type)}</td>"
            f"<td>{_md_cell(change.source_key)}</td>"
            f"<td>{detail_html}</td>"
            f"<td>{_md_cell(change.significance)}</td>"
            "</tr>"
        )

    html = (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#0f172a'>"
        "<h2 style='margin:0 0 4px'>Pharma Intelligence Platform — change digest</h2>"
        f"<p style='color:#475569;margin:0 0 12px'>Run {_md_cell(run_id or 'n/a')} · {stamp}<br>"
        f"{len(changes)} change(s): {added} added, {updated} updated, {removed} removed</p>"
        "<table border='1' cellspacing='0' cellpadding='6' "
        "style='border-collapse:collapse;font-size:12px'>"
        "<thead style='background:#f1f5f9'><tr>"
        "<th>Module</th><th>Change</th><th>Entity</th><th>Source key</th>"
        "<th>Detail</th><th>Score</th></tr></thead><tbody>"
        + "".join(html_rows)
        + "</tbody></table>"
        "<p style='color:#94a3b8;font-size:11px;margin-top:12px'>"
        "Derived from public FDA and USPTO sources. Not legal advice.</p>"
        "</body></html>"
    )
    return subject, "\n".join(text_lines), html


def send_change_digest(changes: list[Any], *, run_id: str | None = None) -> EmailResult:
    """Email the sweep's changes to the configured recipients.

    This is separate from alert delivery: an alert only fires above the
    notification priority floor, while the digest records every detected change
    (including low-priority ones) so the mailbox is a complete audit trail.
    """
    if not changes:
        return EmailResult(status="skipped", recipients=list(settings.alert_email_recipients), error="no changes")
    subject, text, html = build_change_digest(changes, run_id=run_id)
    return send_email(
        subject=subject,
        body=text,
        recipients=list(settings.alert_email_recipients),
        html=html,
    )
