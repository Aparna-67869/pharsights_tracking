"""One-off: re-ingest PTE (applications + certificates) and PDE facts.

The natural keys for these modules were not unique per published row, so
``sync_versioned_records`` silently dropped the second of any colliding pair:
PTE applications 712 -> 696, PTE certificates 1141 -> 1140, PDE 554 -> 553. The
certificate patent number also carried an Excel float artifact (``8088378.0``).
The keys and parsers are now corrected; this purges the affected baseline rows
and reloads them from the already-archived current documents.
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
    ActiveMoiety,
    DetectedChange,
    PteApplication,
    PteCertificate,
    SourceDocument,
)
from app.db.session import reconcile_schema, session_scope
from app.etl import load as loader

# source_code -> (model, loader fn, baseline-change source codes)
TARGETS = {
    "uspto_pte_applications": (PteApplication, loader.load_pte_applications),
    "uspto_pte_certificates": (PteCertificate, loader.load_pte_certificates),
    "fda_pde_approved_active_moiety": (ActiveMoiety, loader.load_active_moieties),
}


def _read_document(document: SourceDocument) -> bytes:
    path = Path(document.storage_path or "")
    if not path.is_absolute():
        path = settings.artifacts_dir / document.storage_path
    return path.read_bytes()


def main() -> None:
    configure_logging()
    reconcile_schema()
    with session_scope() as session:
        for source_code, (model, load_fn) in TARGETS.items():
            before = session.scalar(select(func.count()).select_from(model)) or 0

            document = session.scalars(
                select(SourceDocument)
                .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
                .order_by(SourceDocument.fetched_at.desc())
            ).first()
            if document is None or not document.storage_path:
                print(f"{source_code:34s} SKIP (no archived current document)")
                continue
            data = _read_document(document)

            session.execute(delete(model))
            session.execute(
                delete(DetectedChange).where(
                    DetectedChange.source_code == source_code,
                    DetectedChange.is_baseline.is_(True),
                )
            )
            session.flush()

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
            delta = load_fn(
                session,
                source_code,
                parsed.records,
                collected,
                run_id=f"reingest-{source_code}",
                is_baseline=True,
            )
            document.source_record_count = len(parsed.records)
            document.record_count = delta.stored
            session.flush()
            after = session.scalar(select(func.count()).select_from(model)) or 0
            print(
                f"{source_code:34s} parsed={len(parsed.records):5d} "
                f"stored={delta.stored:5d} rows {before}->{after}"
            )


if __name__ == "__main__":
    main()
