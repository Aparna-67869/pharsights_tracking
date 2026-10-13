"""PDE (Approved Active Moiety) parser.

The FDA workbook has three columns: Active Moiety, Sponsor, Date Issued.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.core.text import clean_text, normalize_name, parse_date_flexible
from app.parsers import excel as xl

log = get_logger(__name__)


def parse_active_moieties(data: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    rows = xl.sheet_rows(data, filename=filename)
    dicts = xl.rows_to_dicts(rows, required=["active moiety", "sponsor", "date issued"])
    records: list[dict[str, Any]] = []
    for row in dicts:
        moiety = clean_text(xl.pick(row, "active moiety"))
        if not moiety or normalize_name(moiety) == "active moiety":
            continue
        issued = parse_date_flexible(xl.pick(row, "date issued"))
        sponsor = clean_text(xl.pick(row, "sponsor"))
        records.append(
            {
                "raw": {k: clean_text(v) for k, v in row.items()},
                "moiety_name": moiety,
                "sponsor_name": sponsor,
                "date_issued": issued,
                "approval_year": issued.year if issued else None,
                "status": "approved",
            }
        )
    log.info("parsed %d active moieties", len(records))
    return records


def source_key(record: dict[str, Any]) -> str:
    """Key is moiety + sponsor: the same moiety may be approved for several sponsors."""
    moiety = normalize_name(record.get("moiety_name"))
    sponsor = normalize_name(record.get("sponsor_name"))
    return f"pde|{moiety}|{sponsor}"


def content_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw": record.get("raw"),
        "moiety_name": record.get("moiety_name"),
        "sponsor_name": record.get("sponsor_name"),
        "date_issued": record.get("date_issued"),
    }
