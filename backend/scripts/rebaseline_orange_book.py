"""One-off: re-baseline the Orange Book sources after the loader fix.

``load_orange_book_products`` forwarded ``appl_no_normalized`` to a model that
never declared it, so every ``fda_ob_data_files`` load failed and the source had
no successful load on record. Once the model declared the column the source
loaded for the first time — but its rows were treated as a change against the
stale, never-refreshed snapshot, producing ~29k phantom add/remove pairs plus
1,000 insights and 520 alerts.

The stored rows are already correct; only the change history is wrong. This
purges the non-baseline change history for the Orange Book sources (and the
insights/alerts derived from it) and reloads the datasets from the archived
current documents as a baseline, so the first real supplement delta is the one
users see.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, func, select

from app.collectors.base import CollectedDocument
from app.collectors.modules import build_collector
from app.collectors.registry import SOURCES_BY_CODE
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import (
    Alert,
    DetectedChange,
    Insight,
    NotificationLog,
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    SourceDocument,
)
from app.db.session import reconcile_schema, session_scope
from app.services.pipeline import _handle_orange_book

OB_SOURCES = ("fda_ob_data_files", "fda_ob_cumulative_supplement", "fda_ob_reference_listed_drugs")
DATASET_MODELS = (OrangeBookProduct, OrangeBookPatent, OrangeBookExclusivity)

# SQLite caps the number of bound parameters per statement, and this purge spans
# tens of thousands of ids, so every ``IN (...)`` runs in chunks.
_CHUNK = 500


def _chunks(items: list[str]):
    for start in range(0, len(items), _CHUNK):
        yield items[start : start + _CHUNK]


def _read_document(document: SourceDocument) -> bytes:
    path = Path(document.storage_path or "")
    if not path.is_absolute():
        path = settings.artifacts_dir / document.storage_path
    return path.read_bytes()


def main() -> None:
    configure_logging()
    reconcile_schema()
    with session_scope() as session:
        # 1. Drop the change rows the first load produced, and everything derived
        #    from them. ``notification_logs`` -> ``alerts`` -> ``insights`` ->
        #    ``detected_changes`` is the FK order, so each table is cleared before
        #    the one it points at.
        change_ids = list(
            session.scalars(
                select(DetectedChange.id).where(
                    DetectedChange.source_code.in_(OB_SOURCES),
                    DetectedChange.is_baseline.is_(False),
                )
            )
        )
        insight_ids = (
            list(session.scalars(select(Insight.id).where(Insight.change_id.in_(change_ids))))
            if change_ids
            else []
        )
        alert_ids = list(
            session.scalars(
                select(Alert.id).where(
                    Alert.change_id.in_(change_ids) | Alert.insight_id.in_(insight_ids)
                )
            )
        ) if (change_ids or insight_ids) else []

        notifications = alerts = insights = changes = 0
        for chunk in _chunks(alert_ids):
            notifications += session.execute(
                delete(NotificationLog).where(NotificationLog.alert_id.in_(chunk))
            ).rowcount
        for chunk in _chunks(alert_ids):
            alerts += session.execute(delete(Alert).where(Alert.id.in_(chunk))).rowcount
        for chunk in _chunks(change_ids):
            insights += session.execute(
                delete(Insight).where(Insight.change_id.in_(chunk))
            ).rowcount
        for chunk in _chunks(change_ids):
            changes += session.execute(
                delete(DetectedChange).where(DetectedChange.id.in_(chunk))
            ).rowcount
        session.flush()
        print(
            f"purged changes={changes} insights={insights} "
            f"alerts={alerts} notification_logs={notifications}"
        )

        # 2. The dataset natural keys changed (patent use code / exclusivity date
        #    are now part of the key), so reload the datasets from the archived
        #    document as a baseline. The source-record count on the document is
        #    the parsed row count; the loader stores every distinct key.
        for model in DATASET_MODELS:
            session.execute(delete(model))
        session.flush()

        source_code = "fda_ob_data_files"
        document = session.scalars(
            select(SourceDocument)
            .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
            .order_by(SourceDocument.fetched_at.desc())
        ).first()
        if document is None or not document.storage_path:
            print(f"{source_code}: SKIP (no archived current document)")
        else:
            data = _read_document(document)
            collector = build_collector(SOURCES_BY_CODE[source_code])
            try:
                parsed = collector.parse(data, filename=document.filename or "")
            finally:
                collector.close()

            collected = CollectedDocument(
                source=SOURCES_BY_CODE[source_code],
                document=document,
                data=data,
                is_new_version=True,
                publication_date=document.publication_date,
                publication_label=document.publication_label,
                resolved_url=document.url,
            )
            results = _handle_orange_book(
                session, source_code, parsed, collected, f"rebaseline-{source_code}", True
            )
            stored = sum(delta.stored for delta in results.values())
            document.source_record_count = len(parsed.records)
            document.record_count = stored
            session.flush()
            print(
                f"{source_code}: parsed={len(parsed.records)} stored={stored} "
                f"datasets={ {k: v.stored for k, v in results.items()} }"
            )

        remaining = session.scalar(
            select(func.count())
            .select_from(DetectedChange)
            .where(DetectedChange.source_code.in_(OB_SOURCES), DetectedChange.is_baseline.is_(False))
        )
        print(f"remaining non-baseline Orange Book changes: {remaining}")
        for model in DATASET_MODELS:
            n = session.scalar(select(func.count()).select_from(model)) or 0
            print(f"  {model.__tablename__}: {n} rows")


if __name__ == "__main__":
    main()
