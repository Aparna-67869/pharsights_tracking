"""Text normalization helpers shared by parsers, ETL and the graph builder."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

# ---- Company names ---------------------------------------------------------

_COMPANY_SUFFIXES = (
    "incorporated", "inc", "corporation", "corp", "company", "co", "limited",
    "ltd", "llc", "l.l.c", "plc", "gmbh", "ag", "sa", "s.a", "nv", "n.v",
    "bv", "b.v", "ab", "as", "a/s", "spa", "s.p.a", "kk", "k.k", "pty",
    "holdings", "group", "pharmaceuticals", "pharmaceutical", "pharma",
    "pharmacia", "laboratories", "laboratory", "labs", "therapeutics",
    "biosciences", "biopharma", "healthcare", "international", "usa",
    "america", "americas", "research", "sciences", "products", "drug",
)

_PUNCT_RE = re.compile(r"[^\w\s&/-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return clean_text(re.sub(r"<[^>]+>", " ", value))


def normalize_name(value: str | None) -> str:
    """Case/whitespace-insensitive comparison key for drugs and companies."""
    text = clean_text(value) or ""
    text = text.casefold()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def normalize_company_name(value: str | None) -> str:
    """Aggressive company key: drops legal suffixes so ``Pfizer Inc.`` == ``Pfizer``."""
    text = normalize_name(value)
    if not text:
        return ""
    tokens = [t for t in text.split(" ") if t]
    while tokens and tokens[-1].rstrip(".") in _COMPANY_SUFFIXES:
        tokens.pop()
    # Drop leading articles
    if tokens and tokens[0] in {"the", "a", "an"}:
        tokens = tokens[1:]
    return " ".join(tokens) if tokens else text


def normalize_drug_name(value: str | None) -> str:
    """Drug key: removes salt forms and parenthetical qualifiers."""
    text = normalize_name(value)
    if not text:
        return ""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(hcl|hydrochloride|sodium|sulfate|sulphate|mesylate|maleate|"
                  r"tartrate|citrate|fumarate|besylate|tosylate|acetate|phosphate|"
                  r"succinate|bitartrate|calcium|potassium|magnesium|dihydrate|"
                  r"monohydrate|anhydrous)\b", " ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_patent_number(value: str | None) -> str:
    """Canonical patent key: uppercase alphanumerics, no punctuation/spaces."""
    text = clean_text(value) or ""
    text = text.upper().replace(" ", "")
    text = re.sub(r"[^A-Z0-9]", "", text)
    # Normalise common prefix forms e.g. "US8357693B2" -> keep as-is; strip kind code
    match = re.match(r"^(US|RE|D|PP|T)?(\d+)([A-Z]\d?)?$", text)
    if match:
        prefix, number, _kind = match.groups()
        prefix = prefix or ""
        return f"{prefix}{number}"
    return text


def normalize_nda_number(value: str | None) -> str:
    """NDA/ANDA number: digits only, zero-padded to 6 where sensible."""
    text = clean_text(value) or ""
    digits = re.sub(r"[^0-9]", "", text)
    return digits.lstrip("0") or digits


def title_case_drug(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    if text.isupper() and len(text) > 3:
        return text.title()
    return text


# ---- Dates -----------------------------------------------------------------

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_YEAR_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")[a-z]*\.?,?\s+(\d{4})\b", re.IGNORECASE
)
_LONG_DATE_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_COMPACT_RE = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_flexible(value: object) -> date | None:
    """Parse the many date formats found in FDA/USPTO artifacts.

    Handles datetime, date, ISO, ``M/D/YYYY``, ``Month D, YYYY``,
    ``D-Mon-YYYY`` and Excel serial numbers.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Excel serial date (1900 date system, with the 1900 leap-year quirk).
        serial = float(value)
        if 1 < serial < 80000:
            try:
                from datetime import timedelta

                return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
            except Exception:
                return None
        return None

    text = clean_text(str(value))
    if not text:
        return None
    lowered = text.casefold().strip()
    if lowered in {"", "n/a", "na", "none", "-", "--", "tbd", "unknown", "not available"}:
        return None

    match = _ISO_RE.search(text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    match = _LONG_DATE_RE.search(text)
    if match:
        month = _MONTHS[match.group(1).casefold()]
        return _safe_date(int(match.group(3)), month, int(match.group(2)))

    match = _SLASH_RE.search(text)
    if match:
        # US convention: M/D/YYYY
        return _safe_date(int(match.group(3)), int(match.group(1)), int(match.group(2)))

    match = _COMPACT_RE.search(text)
    if match:
        first, second, year = (int(g) for g in match.groups())
        # Ambiguous: try D-Mon-YYYY first, then M-D-YYYY
        return _safe_date(year, second, first) or _safe_date(year, first, second)

    match = _MONTH_YEAR_RE.search(text)
    if match:
        return _safe_date(int(match.group(2)), _MONTHS[match.group(1).casefold()], 1)

    for fmt in ("%Y%m%d", "%d%b%Y", "%b %d %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_month_year(value: str | None) -> tuple[int | None, int | None]:
    """Extract ``(year, month)`` from a label such as ``August 2026``."""
    text = clean_text(value)
    if not text:
        return None, None
    match = _MONTH_YEAR_RE.search(text)
    if match:
        return int(match.group(2)), _MONTHS[match.group(1).casefold()]
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    return (int(year_match.group(0)) if year_match else None), None


def parse_extension_period(value: str | None) -> int | None:
    """Convert ``"2 years"`` / ``"931 days"`` into a day count."""
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(year|yr|month|mo|day)", text, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2).casefold()
    if unit.startswith("year") or unit.startswith("yr"):
        return int(round(amount * 365))
    if unit.startswith("month") or unit.startswith("mo"):
        return int(round(amount * 30))
    return int(round(amount))


def parse_bool_flag(value: object) -> bool | None:
    """Orange Book uses ``Yes``/``No`` and ``Y``/``N`` for flags."""
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"yes", "y", "true", "1"}:
        return True
    if text in {"no", "n", "false", "0"}:
        return False
    return None


def slugify(value: str, max_length: int = 60) -> str:
    text = normalize_name(value).replace(" ", "-")
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_length]


def first_non_empty(*values: object) -> str | None:
    for value in values:
        cleaned = clean_text(value if value is None else str(value))
        if cleaned:
            return cleaned
    return None
