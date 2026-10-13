"""One-off: re-ingest FTF facts with the corrected parser.

The FTF fact rows were loaded from the Excel companion with a natural key that
omitted the RLD brand, so 1642 rows were stored where the official list has
1647, and a handful of cells carried ``_x000D_`` artifacts. This purges the
affected baseline rows and re-loads them from the already-archived document.
"""

from sqlalchemy import delete, func, select

from app.core.logging import configure_logging
from app.db.models import DetectedChange, FtfRecord, SourceDocument
from app.db.session import session_scope
from app.etl import load as loader
from app.parsers import ftf as ftf_parser

SOURCE = "fda_ftf_ppiv_pdf"
STALE_SOURCES = ("fda_ftf_ppiv_excel",)


def main() -> None:
    configure_logging()
    with session_scope() as session:
        before = session.scalar(select(func.count()).select_from(FtfRecord)) or 0
        print("ftf rows before:", before)

        doc = session.scalars(
            select(SourceDocument)
            .where(SourceDocument.source_code == SOURCE, SourceDocument.is_current.is_(True))
            .order_by(SourceDocument.fetched_at.desc())
        ).first()
        assert doc is not None and doc.storage_path, "no archived current document"
        from pathlib import Path

        from app.core.config import settings

        path = Path(doc.storage_path)
        if not path.is_absolute():
            path = settings.artifacts_dir / doc.storage_path
        data = path.read_bytes()
        print("document:", doc.filename, "bytes:", len(data), "pub:", doc.publication_date)

        session.execute(delete(FtfRecord))
        session.execute(
            delete(DetectedChange).where(
                DetectedChange.source_code.in_((SOURCE, *STALE_SOURCES)),
                DetectedChange.is_baseline.is_(True),
            )
        )
        session.flush()

        records = ftf_parser.parse_ftf_pdf(data)
        print("parsed records:", len(records))

        from app.collectors.base import CollectedDocument
        from app.collectors.registry import SOURCES_BY_CODE

        collected = CollectedDocument(
            source=SOURCES_BY_CODE[SOURCE],
            document=doc,
            data=data,
            is_new_version=True,
            publication_date=doc.publication_date,
            publication_label=doc.publication_label,
            resolved_url=doc.url,
        )
        delta = loader.load_ftf(
            session,
            SOURCE,
            records,
            collected,
            run_id="reingest-ftf",
            is_baseline=True,
        )
        print("delta:", delta.to_dict() if hasattr(delta, "to_dict") else delta)
        session.flush()

        after = session.scalar(select(func.count()).select_from(FtfRecord)) or 0
        print("ftf rows after:", after)
        artifacts = session.scalar(
            select(func.count()).select_from(FtfRecord).where(FtfRecord.drug_name.like("%_x000D_%"))
        )
        print("rows with _x000D_ artifact:", artifacts)


if __name__ == "__main__":
    main()
