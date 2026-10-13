"""Backfill provenance data onto already-loaded rows.

Re-parses each module's *current* stored source document and writes the exact
published cell text (``raw``) onto the matching fact rows, then recomputes each
``content_hash`` so the next pipeline run is a no-op rather than a false
"updated" delta.

This touches provenance only. It never creates ``DetectedChange`` rows, never
alerts, and never changes an identifier value.

Run with:  python -m scripts.backfill_raw
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.modules import build_collector
from app.collectors.registry import SOURCES_BY_CODE
from app.collectors.storage import get_store
from app.db.base import stable_hash
from app.db.models import (
    ActiveMoiety,
    FtfRecord,
    OrangeBookProduct,
    PteApplication,
    PteCertificate,
    SourceDocument,
)
from app.db.session import session_scope
from app.parsers import ftf as ftf_parser
from app.parsers import orange_book as ob_parser
from app.parsers import pde as pde_parser
from app.parsers import pte as pte_parser


def _digits(value: Any) -> str:
    return re.sub(r"[^0-9]", "", str(value or "")).lstrip("0") or "0"


def _index(records: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for record in records:
        out.setdefault(key(record), record)
    return out


# module source_code -> (model, parsed-record identity, db-row identity, payload fn)
_TARGETS: dict[str, tuple] = {
    "fda_ftf_ppiv_excel": (
        FtfRecord,
        lambda r: ftf_parser.source_key(r),
        lambda row: row.source_key,
        ftf_parser.content_payload,
    ),
    "uspto_pte_applications": (
        PteApplication,
        lambda r: _digits(r.get("application_number") or r.get("patent_number")),
        lambda row: _digits(row.application_number or row.patent_number),
        pte_parser.application_payload,
    ),
    "uspto_pte_certificates": (
        PteCertificate,
        lambda r: _digits(r.get("patent_number")),
        lambda row: _digits(row.patent_number),
        pte_parser.certificate_payload,
    ),
    "fda_pde_approved_active_moiety": (
        ActiveMoiety,
        lambda r: pde_parser.source_key(r),
        lambda row: row.source_key,
        pde_parser.content_payload,
    ),
    "fda_ob_data_files": (
        OrangeBookProduct,
        lambda r: _digits(r.get("appl_no")) + "-" + str(r.get("product_no") or ""),
        lambda row: _digits(row.appl_no) + "-" + str(row.product_no or ""),
        ob_parser.product_payload,
    ),
}


def backfill_source(session: Session, source_code: str) -> dict[str, int]:
    model, rec_key, row_key, payload_fn = _TARGETS[source_code]
    document = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
        .order_by(SourceDocument.fetched_at.desc())
    ).first()
    if document is None or not document.storage_path:
        return {"status": "no_document"}

    store = get_store()
    data = store.get(document.storage_path)
    if data is None:
        return {"status": "artifact_missing"}

    collector = build_collector(SOURCES_BY_CODE[source_code])
    try:
        parsed = collector.parse(data, filename=document.filename or "")
    finally:
        collector.close()

    index = _index(parsed.records, rec_key)
    rows = list(
        session.scalars(select(model).where(model.source_code == source_code, model.is_active.is_(True)))
    )
    updated = 0
    missing = 0
    for row in rows:
        record = index.get(row_key(row))
        if record is None:
            missing += 1
            continue
        # Republish every comparable field straight from the source document so
        # the stored row can never drift from the official file.
        payload = payload_fn(record)
        for field in payload:
            if hasattr(row, field):
                setattr(row, field, payload[field])
        for field in ("raw", "application_number_normalized", "appl_no_normalized"):
            if hasattr(row, field) and record.get(field) is not None:
                setattr(row, field, record[field])
        row.content_hash = stable_hash(payload)
        updated += 1
    session.flush()
    return {"status": "ok", "rows": len(rows), "updated": updated, "unmatched": missing}


def main() -> None:
    with session_scope() as session:
        for source_code in _TARGETS:
            result = backfill_source(session, source_code)
            print(f"{source_code:34s} {result}")


if __name__ == "__main__":
    main()
