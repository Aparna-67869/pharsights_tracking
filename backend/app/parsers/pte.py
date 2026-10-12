"""PTE (Patent Term Extension) parsers.

Two USPTO workbooks:
  * ``pte_past5years.xlsx``  — applications filed in the last five years
  * ``pte_certs.xls``        — certificates issued (legacy BIFF format)

The certificate file stores the original expiration as an Excel serial date and
the granted period as free text ("2 years", "931 days"), so both are converted
to canonical values during parsing.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.core.text import (
    clean_text,
    normalize_patent_number,
    parse_date_flexible,
    parse_extension_period,
)
from app.parsers import excel as xl

log = get_logger(__name__)

# USPTO appends a parenthetical generic name to the trade name:
# "REZUROCK (belumosudil mesylate)".
_TRADE_GENERIC_RE = re.compile(r"^(?P<trade>[^(]+?)\s*\((?P<generic>[^)]+)\)\s*$")


def _split_trade_name(value: Any) -> tuple[str | None, str | None]:
    text = clean_text(value if value is None else str(value))
    if not text:
        return None, None
    match = _TRADE_GENERIC_RE.match(text)
    if match:
        return clean_text(match.group("trade")), clean_text(match.group("generic"))
    return text, None


def parse_pte_applications(data: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    rows = xl.sheet_rows(data, filename=filename)
    dicts = xl.rows_to_dicts(
        rows, required=["u.s. application no", "u.s. patent no", "pte application filing date"]
    )
    records: list[dict[str, Any]] = []
    for row in dicts:
        application_number = clean_text(
            xl.pick(row, "u.s. application no", "application no", "application number")
        )
        patent_number = clean_text(
            xl.pick(row, "u.s. patent no", "patent no", "patent number")
        )
        if not application_number and not patent_number:
            continue
        trade_name, generic_name = _split_trade_name(xl.pick(row, "trade name"))
        records.append(
            {
                "application_number": application_number,
                "patent_number": normalize_patent_number(patent_number) or patent_number,
                "patent_center_link": clean_text(xl.pick(row, "patent center link")),
                "filing_date": parse_date_flexible(
                    xl.pick(row, "pte application filing date", "filing date")
                ),
                "trade_name": trade_name,
                "generic_name": generic_name,
                "designated_number": clean_text(
                    xl.pick(row, "fda/usda designated number", "designated number")
                ),
                "sponsor_name": None,  # not published in this workbook; enriched later
                "status": "filed",
            }
        )
    log.info("parsed %d PTE applications", len(records))
    return records


def parse_pte_certificates(data: bytes, *, filename: str = "") -> list[dict[str, Any]]:
    rows = xl.sheet_rows(data, filename=filename)
    dicts = xl.rows_to_dicts(
        rows, required=["patent no", "tradename", "period of extension granted"]
    )
    records: list[dict[str, Any]] = []
    for row in dicts:
        patent_number = clean_text(xl.pick(row, "patent no", "patent number"))
        if not patent_number:
            continue
        trade_name, generic_name = _split_trade_name(
            xl.pick(row, "tradename of product", "tradename")
        )
        original_expiry = parse_date_flexible(
            xl.pick(row, "original expiration date", "expiration date")
        )
        extension_text = clean_text(
            xl.pick(row, "period of extension granted", "period of extension")
        )
        extension_days = parse_extension_period(extension_text)
        records.append(
            {
                "patent_number": normalize_patent_number(patent_number) or patent_number,
                "trade_name": trade_name,
                "generic_name": generic_name,
                "sponsor_name": None,
                "original_expiration_date": original_expiry,
                "extension_text": extension_text,
                "extension_days": extension_days,
                "granted_date": None,  # not published per row
                "status": "granted",
            }
        )
    log.info("parsed %d PTE certificates", len(records))
    return records


def source_key_application(record: dict[str, Any]) -> str:
    return "pte_app|" + (record.get("application_number") or record.get("patent_number") or "")


def source_key_certificate(record: dict[str, Any]) -> str:
    return "pte_cert|" + (record.get("patent_number") or "")


def application_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "application_number": record.get("application_number"),
        "patent_number": record.get("patent_number"),
        "filing_date": record.get("filing_date"),
        "trade_name": record.get("trade_name"),
        "generic_name": record.get("generic_name"),
        "designated_number": record.get("designated_number"),
    }


def certificate_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "patent_number": record.get("patent_number"),
        "trade_name": record.get("trade_name"),
        "generic_name": record.get("generic_name"),
        "original_expiration_date": record.get("original_expiration_date"),
        "extension_days": record.get("extension_days"),
        "extension_text": record.get("extension_text"),
    }
