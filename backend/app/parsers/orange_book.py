"""Orange Book parsers.

Three inputs:
  * ``products.txt``    — tilde-delimited approved product listings
  * ``patent.txt``      — patent listings attached to products
  * ``exclusivity.txt`` — exclusivity grants attached to products
  * cumulative supplement PDF — supplement number / publication month metadata

The tilde-delimited files are the authoritative structured dataset; the PDF
supplies the edition metadata (supplement number, month, year).
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from typing import Any

from app.core.logging import get_logger
from app.core.text import (
    clean_text,
    normalize_nda_number,
    normalize_patent_number,
    parse_bool_flag,
    parse_date_flexible,
    parse_month_year,
)
from app.parsers import pdf as pdfparser

log = get_logger(__name__)

DELIMITER = "~"

SUPPLEMENT_NO_RE = re.compile(r"CUMULATIVE\s+SUPPLEMENT\s+(\d+)", re.IGNORECASE)
EDITION_RE = re.compile(r"(\d+)(?:ST|ND|RD|TH)\s+EDITION", re.IGNORECASE)
MONTH_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)

# Exclusivity code meanings per the Orange Book preface.
EXCLUSIVITY_MEANINGS: dict[str, str] = {
    "NCE": "New Chemical Entity exclusivity (5 years)",
    "NP": "New Product exclusivity (3 years)",
    "NS": "New Salt/ester exclusivity (3 years)",
    "NDF": "New Dosage Form exclusivity (3 years)",
    "ODE": "Orphan Drug Exclusivity (7 years)",
    "ODE-RE": "Orphan Drug Exclusivity - Rare Disease (7 years)",
    "PED": "Pediatric Exclusivity (6 months)",
    "I-270": "I-270 exclusivity",
    "M": "Miscellaneous exclusivity",
    "RTO": "Reference product Transition/Other exclusivity",
    "NP-RE": "New Product exclusivity - Rare Disease",
}


def extract_zip_members(data: bytes) -> dict[str, bytes]:
    """Return ``{filename: bytes}`` for the Orange Book data archive."""
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/")[-1]
            members[name.casefold()] = archive.read(info)
    return members


def _iter_delimited(data: bytes) -> list[dict[str, str]]:
    text = data.decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(DELIMITER)]
    records: list[dict[str, str]] = []
    for line in lines[1:]:
        values = line.split(DELIMITER)
        # Some rows contain trailing empties; pad to the header width.
        if len(values) < len(header):
            values += [""] * (len(header) - len(values))
        records.append({header[i]: values[i] for i in range(len(header))})
    return records


def parse_products(data: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _iter_delimited(data):
        trade_name = clean_text(row.get("Trade_Name"))
        appl_no = clean_text(row.get("Appl_No"))
        product_no = clean_text(row.get("Product_No"))
        if not appl_no:
            continue
        records.append(
            {
                "raw": {k: clean_text(v) for k, v in row.items()},
                "ingredient": clean_text(row.get("Ingredient")),
                "dosage_form_route": clean_text(row.get("DF;Route")),
                "trade_name": trade_name,
                "applicant": clean_text(row.get("Applicant")),
                "applicant_full_name": clean_text(row.get("Applicant_Full_Name")),
                "strength": clean_text(row.get("Strength")),
                "appl_type": clean_text(row.get("Appl_Type")),
                "appl_no": appl_no,
                "appl_no_normalized": normalize_nda_number(appl_no) or appl_no,
                "product_no": product_no,
                "te_code": clean_text(row.get("TE_Code")),
                "approval_date": parse_date_flexible(row.get("Approval_Date")),
                "rld": parse_bool_flag(row.get("RLD")),
                "rs": parse_bool_flag(row.get("RS")),
                "product_type": clean_text(row.get("Type")),
            }
        )
    log.info("parsed %d Orange Book products", len(records))
    return records


def parse_patents(data: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _iter_delimited(data):
        patent_number = clean_text(row.get("Patent_No"))
        appl_no = clean_text(row.get("Appl_No"))
        if not patent_number or not appl_no:
            continue
        expiration_text = clean_text(row.get("Patent_Expire_Date_Text"))
        records.append(
            {
                "appl_type": clean_text(row.get("Appl_Type")),
                "appl_no": appl_no,
                "appl_no_normalized": normalize_nda_number(appl_no) or appl_no,
                "product_no": clean_text(row.get("Product_No")),
                "patent_number": normalize_patent_number(patent_number) or patent_number,
                "expiration_text": expiration_text,
                "expiration_date": parse_date_flexible(expiration_text),
                "drug_substance_flag": parse_bool_flag(row.get("Drug_Substance_Flag")),
                "drug_product_flag": parse_bool_flag(row.get("Drug_Product_Flag")),
                "patent_use_code": clean_text(row.get("Patent_Use_Code")),
                "delist_flag": bool(parse_bool_flag(row.get("Delist_Flag"))),
                "submission_date": parse_date_flexible(row.get("Submission_Date")),
            }
        )
    log.info("parsed %d Orange Book patent listings", len(records))
    return records


def parse_exclusivity(data: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _iter_delimited(data):
        appl_no = clean_text(row.get("Appl_No"))
        code = clean_text(row.get("Exclusivity_Code"))
        if not appl_no or not code:
            continue
        records.append(
            {
                "appl_type": clean_text(row.get("Appl_Type")),
                "appl_no": appl_no,
                "appl_no_normalized": normalize_nda_number(appl_no) or appl_no,
                "product_no": clean_text(row.get("Product_No")),
                "exclusivity_code": code,
                "exclusivity_date": parse_date_flexible(row.get("Exclusivity_Date")),
                "exclusivity_meaning": EXCLUSIVITY_MEANINGS.get(code.upper()),
            }
        )
    log.info("parsed %d Orange Book exclusivity records", len(records))
    return records


def parse_supplement_metadata(data: bytes) -> dict[str, Any]:
    """Read supplement number / edition / publication month from the PDF cover."""
    text = pdfparser.first_page_text(data)
    result: dict[str, Any] = {
        "supplement_number": None,
        "edition": None,
        "publication_month": None,
        "publication_year": None,
        "publication_date": None,
    }
    match = SUPPLEMENT_NO_RE.search(text)
    if match:
        result["supplement_number"] = match.group(1)
    match = EDITION_RE.search(text)
    if match:
        result["edition"] = match.group(1)
    match = MONTH_YEAR_RE.search(text)
    if match:
        year, month = parse_month_year(match.group(0))
        result["publication_month"] = month
        result["publication_year"] = year
        if year and month:
            result["publication_date"] = date(year, month, 1)
    return result


def product_source_key(record: dict[str, Any]) -> str:
    return "ob_prod|{}|{}|{}".format(
        (record.get("appl_type") or "").upper(),
        record.get("appl_no") or "",
        record.get("product_no") or "",
    )


def patent_source_key(record: dict[str, Any]) -> str:
    # ``patent_use_code`` is part of the key because FDA lists one row per use
    # code for the same patent/product (e.g. U-1447 and U-1448); omitting it
    # silently collapsed ~4.7k real rows on load.
    return "ob_pat|{}|{}|{}|{}|{}".format(
        (record.get("appl_type") or "").upper(),
        record.get("appl_no") or "",
        record.get("product_no") or "",
        record.get("patent_number") or "",
        record.get("patent_use_code") or "",
    )


def exclusivity_source_key(record: dict[str, Any]) -> str:
    # The same exclusivity code can appear more than once for a product with
    # different expiry dates (e.g. two ODE* rows), so the date disambiguates.
    return "ob_excl|{}|{}|{}|{}|{}".format(
        (record.get("appl_type") or "").upper(),
        record.get("appl_no") or "",
        record.get("product_no") or "",
        record.get("exclusivity_code") or "",
        record.get("exclusivity_date") or "",
    )


def product_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "raw": record.get("raw"),
        "trade_name": record.get("trade_name"),
        "ingredient": record.get("ingredient"),
        "applicant": record.get("applicant"),
        "applicant_full_name": record.get("applicant_full_name"),
        "strength": record.get("strength"),
        "dosage_form_route": record.get("dosage_form_route"),
        "te_code": record.get("te_code"),
        "approval_date": record.get("approval_date"),
        "rld": record.get("rld"),
        "rs": record.get("rs"),
        "product_type": record.get("product_type"),
    }


def patent_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "patent_number": record.get("patent_number"),
        "expiration_date": record.get("expiration_date"),
        "expiration_text": record.get("expiration_text"),
        "drug_substance_flag": record.get("drug_substance_flag"),
        "drug_product_flag": record.get("drug_product_flag"),
        "patent_use_code": record.get("patent_use_code"),
        "delist_flag": record.get("delist_flag"),
        "submission_date": record.get("submission_date"),
    }


def exclusivity_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "exclusivity_code": record.get("exclusivity_code"),
        "exclusivity_date": record.get("exclusivity_date"),
    }
