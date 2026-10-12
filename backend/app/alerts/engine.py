"""Alert engine: turn insights into deduplicated, prioritized, dispatched alerts.

Design rules:
  * Only insights at or above ``ALERT_MIN_PRIORITY_TO_NOTIFY`` produce alerts —
    the platform is meant to surface signal, not noise.
  * Alerts are deduplicated by a deterministic key so re-running the pipeline
    never spams the same change twice.
  * Every delivery attempt is recorded in ``notification_logs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.channels import all_channels
from app.core.config import settings
from app.core.events import Topics, publish_event
from app.core.logging import get_logger
from app.db.base import stable_hash
from app.db.models import Alert, Insight, NotificationLog

log = get_logger(__name__)

EVENT_TYPE_BY_ENTITY = {
    "ftf_record": "new_ftf",
    "pte_application": "new_pte_application",
    "pte_certificate": "new_pte_certificate",
    "active_moiety": "new_pde_entry",
    "orange_book_product": "orange_book_update",
    "orange_book_patent": "orange_book_update",
    "orange_book_exclusivity": "orange_book_update",
}


@dataclass
class DispatchSummary:
    created: int = 0
    suppressed: int = 0
    notified: int = 0
    channels: dict[str, int] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.channels is None:
            self.channels = {}


def dedupe_key_for(insight: Insight) -> str:
    """Stable identity for an alert: entity + change + module."""
    return stable_hash(
        {
            "module": insight.module,
            "entity_type": insight.entity_type,
            "entity_key": insight.entity_key,
            "title": insight.title,
        }
    )


def _event_type_for(insight: Insight) -> str:
    base = EVENT_TYPE_BY_ENTITY.get(insight.entity_type, "regulatory_change")
    return base


def create_alert_from_insight(session: Session, insight: Insight) -> Alert | None:
    """Create an alert for one insight, or return the existing alert if deduped."""
    if insight.priority_score < settings.alert_min_priority_to_notify:
        return None

    key = dedupe_key_for(insight)
    existing = session.scalars(select(Alert).where(Alert.dedupe_key == key)).first()
    if existing is not None:
        return None

    alert = Alert(
        dedupe_key=key,
        module=insight.module,
        event_type=_event_type_for(insight),
        severity=insight.priority_label,
        title=insight.title,
        message=_build_message(insight),
        priority_score=insight.priority_score,
        priority_label=insight.priority_label,
        status="open",
        entity_type=insight.entity_type,
        entity_key=insight.entity_key,
        drug_name=(insight.affected_products or [None])[0],
        sponsor_name=(insight.affected_companies or [None])[0],
        insight_id=insight.id,
        change_id=insight.change_id,
        metadata_json={"score_breakdown": insight.score_breakdown},
    )
    session.add(alert)
    session.flush()

    publish_event(
        Topics.ALERT_CREATED,
        alert.event_type,
        {
            "alert_id": alert.id,
            "module": alert.module,
            "priority": alert.priority_label,
            "score": alert.priority_score,
            "title": alert.title,
        },
    )
    return alert


def _build_message(insight: Insight) -> str:
    parts = [insight.what_changed]
    if insight.why_it_matters:
        parts.append(f"Why it matters: {insight.why_it_matters}")
    if insight.generic_opportunity:
        parts.append(f"Generic opportunity: {insight.generic_opportunity}")
    if insight.exclusivity_risk:
        parts.append(f"Exclusivity risk: {insight.exclusivity_risk}")
    if insight.recommended_action:
        parts.append(f"Recommended action: {insight.recommended_action}")
    return "\n\n".join(parts)


def dispatch_alert(session: Session, alert: Alert) -> list[NotificationLog]:
    """Send an alert over every configured channel and log the attempts."""
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

    logs: list[NotificationLog] = []
    channels_sent: list[str] = list(alert.channels_sent or [])

    for channel in all_channels():
        if not channel.configured():
            result_status, recipient, error = "skipped", None, "not configured"
        else:
            result = channel.send(payload)
            result_status, recipient, error = result.status, result.recipient, result.error

        entry = NotificationLog(
            alert_id=alert.id,
            channel=channel.name,
            recipient=recipient,
            status=result_status,
            attempts=1 if result_status != "skipped" else 0,
            error=error,
            sent_at=None,
            payload={"priority": alert.priority_label},
        )
        if result_status == "sent":
            from app.db.base import utcnow

            entry.sent_at = utcnow()
            if channel.name not in channels_sent:
                channels_sent.append(channel.name)
        session.add(entry)
        logs.append(entry)

    alert.channels_sent = channels_sent
    session.flush()
    return logs


def dispatch_alerts(session: Session, *, insights: list[Insight] | None = None) -> list[Alert]:
    """Create and dispatch alerts for the given (or all unalerted) insights."""
    if insights is None:
        # Only insights that do not already have an alert, so re-running the
        # pipeline never re-notifies on historical findings.
        already_alerted = select(Alert.insight_id).where(Alert.insight_id.is_not(None))
        insights = list(
            session.scalars(
                select(Insight)
                .where(
                    Insight.priority_score >= settings.alert_min_priority_to_notify,
                    Insight.id.not_in(already_alerted),
                )
                .order_by(Insight.created_at.desc())
                .limit(500)
            )
        )

    created: list[Alert] = []
    for insight in insights:
        alert = create_alert_from_insight(session, insight)
        if alert is None:
            continue
        dispatch_alert(session, alert)
        created.append(alert)

    log.info("alert engine: created and dispatched %d alerts", len(created))
    return created


def alert_summary(session: Session) -> dict[str, Any]:
    from sqlalchemy import func

    rows = session.execute(
        select(Alert.priority_label, func.count(Alert.id))
        .where(Alert.status == "open")
        .group_by(Alert.priority_label)
    ).all()
    by_label = {label: count for label, count in rows}
    total_open = sum(by_label.values())
    total = session.scalar(select(func.count()).select_from(Alert)) or 0
    return {
        "open_total": total_open,
        "total": total,
        "by_priority": by_label,
    }
