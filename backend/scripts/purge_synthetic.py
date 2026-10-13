"""Remove fact rows that did not come from a monitored source document.

The dashboard must reflect the official FDA/USPTO files only. This utility
deletes any ``ftf_records`` / ``pte_*`` / ``active_moieties`` /
``orange_book_products`` row whose natural key cannot be found in the current
source document, plus the changes, insights, alerts and notifications derived
from those rows, and reactivates rows that a previous non-baseline run
deactivated in error.

Run with:  python -m scripts.purge_synthetic
"""

from __future__ import annotations

from sqlalchemy import delete, select

from app.collectors.modules import build_collector
from app.collectors.registry import SOURCES_BY_CODE
from app.collectors.storage import get_store
from app.db.models import (
    Alert,
    DetectedChange,
    Insight,
    NotificationLog,
    SourceDocument,
)
from app.db.session import session_scope
from scripts.backfill_raw import _TARGETS


def _source_keys(session, source_code: str) -> set[str]:
    _model, rec_key, _row_key, _payload = _TARGETS[source_code]
    document = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
        .order_by(SourceDocument.fetched_at.desc())
    ).first()
    if document is None or not document.storage_path:
        return set()
    data = get_store().get(document.storage_path)
    if data is None:
        return set()
    collector = build_collector(SOURCES_BY_CODE[source_code])
    try:
        parsed = collector.parse(data, filename=document.filename or "")
    finally:
        collector.close()
    return {rec_key(r) for r in parsed.records}


def main() -> None:
    with session_scope() as session:
        for source_code, (model, _rec_key, row_key_fn, _payload) in _TARGETS.items():
            published = _source_keys(session, source_code)
            rows = list(session.scalars(select(model).where(model.source_code == source_code)))
            synthetic = [r for r in rows if row_key_fn(r) not in published]
            reactivated = 0
            for row in rows:
                if not row.is_active and row_key_fn(row) in published:
                    row.is_active = True
                    reactivated += 1
            for row in synthetic:
                session.delete(row)
            session.flush()

            if synthetic:
                keys = [row.source_key for row in synthetic if hasattr(row, "source_key")]
                changes = list(
                    session.scalars(
                        select(DetectedChange).where(
                            DetectedChange.source_key.in_(keys),
                            DetectedChange.is_baseline.is_(False),
                        )
                    )
                )
                change_ids = [c.id for c in changes]
                insight_ids = [
                    i for i in session.scalars(select(Insight.id).where(Insight.change_id.in_(change_ids)))
                ]
                alert_ids = [
                    a for a in session.scalars(select(Alert.id).where(Alert.entity_key.in_(keys)))
                ] + [
                    a for a in session.scalars(select(Alert.id).where(Alert.insight_id.in_(insight_ids)))
                ]
                if alert_ids:
                    session.execute(delete(NotificationLog).where(NotificationLog.alert_id.in_(alert_ids)))
                    session.execute(delete(Alert).where(Alert.id.in_(alert_ids)))
                if insight_ids:
                    session.execute(delete(Insight).where(Insight.id.in_(insight_ids)))
                if change_ids:
                    session.execute(delete(DetectedChange).where(DetectedChange.id.in_(change_ids)))

            print(
                f"{source_code:34s} scanned={len(rows):6d} "
                f"synthetic_removed={len(synthetic):3d} reactivated={reactivated}"
            )


if __name__ == "__main__":
    main()
