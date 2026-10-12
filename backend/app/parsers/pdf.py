"""Generic PDF text and table extraction built on PyMuPDF."""

from __future__ import annotations

import re
from typing import Any

from app.core.errors import ParserError
from app.core.logging import get_logger
from app.core.text import clean_text

log = get_logger(__name__)

# Suppress PyMuPDF's advisory about the optional layout package.
try:  # pragma: no cover
    import pymupdf

    pymupdf.TOOLS.mupdf_display_errors(False)
except Exception:  # pragma: no cover
    pass


def open_pdf(data: bytes):
    import pymupdf

    try:
        return pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ParserError(f"Unable to open PDF: {exc}") from exc


def page_texts(data: bytes, *, max_pages: int | None = None) -> list[str]:
    document = open_pdf(data)
    try:
        limit = len(document) if max_pages is None else min(max_pages, len(document))
        return [document[i].get_text() for i in range(limit)]
    finally:
        document.close()


def extract_tables(
    data: bytes,
    *,
    max_pages: int | None = None,
    min_rows: int = 2,
) -> list[list[list[str]]]:
    """Extract table rows from every page, normalized to clean strings.

    Returns a flat list of tables; each table is a list of rows; each row is a
    list of cell strings with internal newlines collapsed to spaces.
    """
    document = open_pdf(data)
    tables: list[list[list[str]]] = []
    try:
        limit = len(document) if max_pages is None else min(max_pages, len(document))
        for index in range(limit):
            page = document[index]
            try:
                found = page.find_tables()
            except Exception as exc:  # pragma: no cover
                log.debug("table detection failed on page %d: %s", index, exc)
                continue
            for table in found:
                try:
                    raw_rows = table.extract()
                except Exception:
                    continue
                rows = [
                    [clean_text(cell) or "" for cell in row] for row in raw_rows if row is not None
                ]
                rows = [r for r in rows if any(r)]
                if len(rows) >= min_rows:
                    tables.append(rows)
    finally:
        document.close()
    return tables


def first_page_text(data: bytes) -> str:
    document = open_pdf(data)
    try:
        return document[0].get_text() if len(document) else ""
    finally:
        document.close()


def search_metadata(data: bytes, patterns: dict[str, str]) -> dict[str, str | None]:
    """Run named regex patterns across the first few pages of a PDF."""
    document = open_pdf(data)
    try:
        header = "\n".join(
            document[i].get_text() for i in range(min(4, len(document)))
        )
    finally:
        document.close()

    results: dict[str, str | None] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, header, re.IGNORECASE)
        results[name] = clean_text(match.group(1)) if match and match.groups() else (
            clean_text(match.group(0)) if match else None
        )
    return results


def iter_table_dicts(
    tables: list[list[list[str]]],
    *,
    header_keywords: list[str],
    min_keyword_hits: int = 2,
) -> list[dict[str, Any]]:
    """Yield dict rows from tables whose header matches the given keywords."""
    records: list[dict[str, Any]] = []
    for table in tables:
        if not table:
            continue
        header = [clean_text(c) or "" for c in table[0]]
        header_blob = " ".join(h.casefold() for h in header)
        hits = sum(1 for kw in header_keywords if kw.casefold() in header_blob)
        if hits < min_keyword_hits:
            continue
        for row in table[1:]:
            record = {}
            for index, name in enumerate(header):
                key = re.sub(r"\s+", " ", name.replace("\n", " ")).strip().casefold()
                if not key:
                    continue
                record[key] = row[index] if index < len(row) else ""
            if any(v for v in record.values()):
                records.append(record)
    return records
