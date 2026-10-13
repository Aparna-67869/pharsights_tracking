"""FTF (First-To-File / Paragraph IV) parsers.

Two representations are supported and cross-validated:
  * Excel workbook  — authoritative structured list
  * PDF             — same columns, used to confirm the published snapshot

The FTF row's natural key is ``(drug, dosage form, strength, RLD/NDA, submission date)``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.core.logging import get_logger
from app.core.text import (
    clean_text,
    normalize_drug_name,
    normalize_nda_number,
    normalize_patent_number,
    parse_date_flexible,
)
from app.parsers import excel as xl
from app.parsers import pdf as pdfparser

log = get_logger(__name__)

FTF_COLUMNS = [
    "drug name",
    "dosage form",
    "strength",
    "rld nda",
    "date of submission",
    "number of andas submitted",
    "180 day status",
    "180 day decision posting date",
    "date of first applicant approval",
    "date of first commercial marketing by ftf",
    "expiration date of last qualifying patent",
]

_PUB_DATE_RE = re.compile(r"as of\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE)
_RLD_SPLIT_RE = re.compile(r"^(?P<brand>.*?)[\s\n]+(?P<number>\d{3,6})\s*$", re.DOTALL)
# The PDF hyphenates long words across a line break ("multi-\ndose"), which
# PyMuPDF joins as "multi- dose". Collapse that to "multi-dose" for both the
# rendered text and the natural key. Range excludes ASCII digits so genuine
# numeric strengths ("600 mg/50 mg/ 300 mg") are untouched.
_SOFT_HYPHEN_RE = re.compile(r"(?<=[^\W\d_])-\s+(?=[^\W\d_])", re.UNICODE)


def _dehyphenate(value: Any) -> str | None:
    text = clean_text(value if value is None else str(value))
    if not text:
        return text
    return _SOFT_HYPHEN_RE.sub("-", text)


def _split_rld(value: Any) -> tuple[str | None, str | None]:
    """Split the ``RLD/NDA`` cell (e.g. ``"Ziagen\\n20977"``) into brand and NDA."""
    text = clean_text(value if value is None else str(value))
    if not text:
        return None, None
    match = _RLD_SPLIT_RE.match(text)
    if match:
        brand = clean_text(match.group("brand"))
        number = clean_text(match.group("number"))
        return brand, number
    # Fall back: extract trailing digits, treat the rest as the brand.
    digits = re.findall(r"\d{3,6}", text)
    brand = clean_text(re.sub(r"\d{3,6}\s*$", "", text).strip(" ,;")) if digits else text
    return brand, (digits[-1] if digits else None)


def _parse_int(value: Any) -> int | None:
    text = clean_text(value if value is None else str(value))
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _row_to_record(row: dict[str, Any]) -> dict[str, Any] | None:
    drug_name = _dehyphenate(xl.pick(row, "drug name"))
    if not drug_name:
        return None
    # Skip repeated header rows produced by PDF page breaks.
    if normalize_drug_name(drug_name) == "drug name":
        return None

    rld_raw = _dehyphenate(xl.pick(row, "rld nda", "rld/nda", "rld"))
    brand, nda = _split_rld(rld_raw)

    submission = parse_date_flexible(xl.pick(row, "date of submission"))
    submission_text = clean_text(xl.pick(row, "date of submission"))
    # "Pre-MMA" rows have no submission date; keep the label as evidence.
    pre_mma = bool(submission_text and "pre" in submission_text.casefold())

    record: dict[str, Any] = {
        # Verbatim source cells, keyed by the workbook's own column headers. The
        # normalized fields below are for matching; the dashboard renders these.
        "raw": {k: _dehyphenate(v) for k, v in row.items()},
        "drug_name": drug_name,
        "dosage_form": _dehyphenate(xl.pick(row, "dosage form")),
        "strength": _dehyphenate(xl.pick(row, "strength")),
        "rld_brand_name": brand,
        "nda_number": normalize_nda_number(nda) or None,
        "rld_nda": rld_raw,
        "date_of_submission": submission,
        "number_of_andas": _parse_int(xl.pick(row, "number of andas submitted", "number of andas")),
        "exclusivity_status": clean_text(xl.pick(row, "180 day status", "180-day status")),
        "decision_posting_date": parse_date_flexible(
            xl.pick(row, "180 day decision posting date", "decision posting")
        ),
        "first_applicant_approval_date": parse_date_flexible(
            xl.pick(row, "date of first applicant approval", "first applicant approval")
        ),
        "first_commercial_marketing_date": parse_date_flexible(
            xl.pick(row, "date of first commercial marketing", "commercial marketing")
        ),
        "last_qualifying_patent_expiry": parse_date_flexible(
            xl.pick(row, "expiration date of last qualifying patent", "expiration date")
        ),
        "certification_type": "Paragraph IV",
        "pre_mma": pre_mma,
    }
    return record


def parse_ftf_excel(data: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    rows = xl.sheet_rows(data, filename=filename)
    dicts = xl.rows_to_dicts(rows, required=["drug name", "date of submission", "rld"])
    records = [r for r in (_row_to_record(d) for d in dicts) if r]
    log.info("parsed %d FTF records from Excel", len(records))
    return records


def parse_ftf_pdf(data: bytes) -> list[dict[str, Any]]:
    tables = pdfparser.extract_tables(data)
    dicts = pdfparser.iter_table_dicts(
        tables,
        header_keywords=["drug name", "dosage form", "date of", "strength"],
        min_keyword_hits=3,
    )
    records = [r for r in (_row_to_record(d) for d in dicts) if r]
    log.info("parsed %d FTF records from PDF", len(records))
    return records


def extract_ftf_publication_date(text: str) -> date | None:
    match = _PUB_DATE_RE.search(text or "")
    return parse_date_flexible(match.group(1)) if match else None


def source_key(record: dict[str, Any]) -> str:
    """Natural key identifying an FTF row across versions.

    Includes the RLD/NDA brand because the FDA list contains genuinely distinct
    rows that share drug/dosage/strength/NDA but differ by the brand they are
    listed under — e.g. ``Zepbound`` vs ``Zepbound (Autoinjector)`` on NDA
    217806, or ``Jenloga`` vs ``Kapvay`` on NDA 22331. Omitting the brand merged
    those pairs and silently dropped real filings.
    """
    parts = [
        normalize_drug_name(record.get("drug_name")),
        (record.get("dosage_form") or "").casefold(),
        (record.get("strength") or "").casefold(),
        record.get("nda_number") or "",
        (record.get("rld_brand_name") or "").casefold(),
    ]
    return "ftf|" + "|".join(parts)


def content_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Fields that constitute the comparable content of an FTF row."""
    return {
        "drug_name": record.get("drug_name"),
        "raw": record.get("raw"),
        "dosage_form": record.get("dosage_form"),
        "strength": record.get("strength"),
        "rld_brand_name": record.get("rld_brand_name"),
        "nda_number": record.get("nda_number"),
        "date_of_submission": record.get("date_of_submission"),
        "number_of_andas": record.get("number_of_andas"),
        "exclusivity_status": record.get("exclusivity_status"),
        "decision_posting_date": record.get("decision_posting_date"),
        "first_applicant_approval_date": record.get("first_applicant_approval_date"),
        "first_commercial_marketing_date": record.get("first_commercial_marketing_date"),
        "last_qualifying_patent_expiry": record.get("last_qualifying_patent_expiry"),
    }


def patent_number_from_record(record: dict[str, Any]) -> str | None:
    value = record.get("patent_number")
    return normalize_patent_number(value) if value else None
