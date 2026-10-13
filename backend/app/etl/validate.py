"""Record validation. Rejects structurally invalid rows before they reach the DB."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.logging import get_logger
from app.core.text import clean_text

log = get_logger(__name__)


@dataclass
class ValidationIssue:
    severity: str  # error | warning
    field: str
    message: str


@dataclass
class ValidationReport:
    total: int = 0
    valid: int = 0
    rejected: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid": self.valid,
            "rejected": self.rejected,
            "errors": self.error_count,
            "warnings": self.warning_count,
        }


Validator = Callable[[dict[str, Any]], list[ValidationIssue]]


def validate_batch(records: list[dict[str, Any]], validators: list[Validator]) -> tuple[list[dict[str, Any]], ValidationReport]:
    """Apply validators to each record; drop records with error-severity issues."""
    report = ValidationReport(total=len(records))
    kept: list[dict[str, Any]] = []
    for record in records:
        issues: list[ValidationIssue] = []
        for validator in validators:
            try:
                issues.extend(validator(record))
            except Exception as exc:  # pragma: no cover - defensive
                issues.append(ValidationIssue("error", "validator", str(exc)))
        report.issues.extend(issues)
        if any(i.severity == "error" for i in issues):
            report.rejected += 1
            continue
        kept.append(record)
        report.valid += 1
    return kept, report


def _required(field_name: str, label: str | None = None) -> Validator:
    def _validator(record: dict[str, Any]) -> list[ValidationIssue]:
        if not clean_text(str(record.get(field_name) or "")):
            return [ValidationIssue("error", field_name, f"{label or field_name} is required")]
        return []

    return _validator


def _date_sanity(field_name: str, *, min_year: int = 1900, max_year: int = 2100) -> Validator:
    def _validator(record: dict[str, Any]) -> list[ValidationIssue]:
        value = record.get(field_name)
        if value is None:
            return []
        if not isinstance(value, date):
            return [ValidationIssue("error", field_name, f"{field_name} is not a date")]
        if not (min_year <= value.year <= max_year):
            return [
                ValidationIssue(
                    "warning", field_name, f"{field_name} {value} outside plausible range"
                )
            ]
        return []

    return _validator


def _positive_int(field_name: str) -> Validator:
    def _validator(record: dict[str, Any]) -> list[ValidationIssue]:
        value = record.get(field_name)
        if value is None:
            return []
        try:
            number = int(value)
        except (TypeError, ValueError):
            return [ValidationIssue("error", field_name, f"{field_name} must be an integer")]
        if number < 0:
            return [ValidationIssue("error", field_name, f"{field_name} must be >= 0")]
        return []

    return _validator


# ---- Per-module validator sets --------------------------------------------

FTF_VALIDATORS: list[Validator] = [
    _required("drug_name", "Drug name"),
    _date_sanity("date_of_submission"),
    _date_sanity("last_qualifying_patent_expiry"),
    _positive_int("number_of_andas"),
]

PTE_APPLICATION_VALIDATORS: list[Validator] = [
    _required("patent_number", "Patent number"),
    _date_sanity("filing_date"),
]

PTE_CERTIFICATE_VALIDATORS: list[Validator] = [
    _required("patent_number", "Patent number"),
    _date_sanity("original_expiration_date"),
    _positive_int("extension_days"),
]

PDE_VALIDATORS: list[Validator] = [
    _required("moiety_name", "Active moiety"),
    _date_sanity("date_issued"),
]

ORANGE_BOOK_PRODUCT_VALIDATORS: list[Validator] = [
    _required("appl_no", "Application number"),
    _required("appl_type", "Application type"),
    _date_sanity("approval_date"),
]

ORANGE_BOOK_PATENT_VALIDATORS: list[Validator] = [
    _required("patent_number", "Patent number"),
    _required("appl_no", "Application number"),
    _date_sanity("expiration_date"),
]

ORANGE_BOOK_EXCLUSIVITY_VALIDATORS: list[Validator] = [
    _required("appl_no", "Application number"),
    _required("exclusivity_code", "Exclusivity code"),
    _date_sanity("exclusivity_date"),
]


# ---- Fidelity gate ---------------------------------------------------------
#
# Runs *before* records are published. It compares the parsed value of every
# identifier the dashboard displays against the exact cell text the source
# published, rejecting any row whose stored value would misrepresent the
# official document. The parse layers build these normalized fields; here we
# assert the transformation was lossless.

_IDENTIFIER_FIELDS = (
    "patent_number",
    "nda_number",
    "application_number",
    "appl_no",
)


def _digits_only(value: Any) -> str:
    """Digit form for identifier comparison; leading zeros are insignificant
    (``02222`` and ``2222`` are the same NDA)."""
    return re.sub(r"[^0-9]", "", str(value or "")).lstrip("0") or "0"


def fidelity_validator(raw_key: str, label: str) -> Validator:
    """Reject records whose displayed identifier no longer matches the source cell."""

    def _validator(record: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        raw = record.get("raw") or {}
        for name in _IDENTIFIER_FIELDS:
            published = clean_text(str(raw.get(raw_key) or ""))
            stored = clean_text(str(record.get(name) or ""))
            if not published or not stored:
                continue
            if published == stored:
                continue
            if _digits_only(published) == _digits_only(stored):
                continue
            issues.append(
                ValidationIssue(
                    "error",
                    name,
                    f"{label}: stored {name} {stored!r} does not match published "
                    f"value {published!r}",
                )
            )
        return issues

    return _validator


_FTF_RLD_RE = re.compile(r"^(?P<brand>.*?)[\s\n]+(?P<number>\d{3,6})\s*$", re.DOTALL)


def _ftf_fidelity(record: dict[str, Any]) -> list[ValidationIssue]:
    raw = record.get("raw") or {}
    published = clean_text(str(raw.get("RLD/NDA") or raw.get("rld nda") or ""))
    stored_nda = clean_text(str(record.get("nda_number") or ""))
    if not published or not stored_nda:
        return []
    match = _FTF_RLD_RE.match(published)
    number = clean_text(match.group("number")) if match else ""
    if number and _digits_only(number) != _digits_only(stored_nda):
        return [
            ValidationIssue(
                "error",
                "nda_number",
                f"FTF: stored nda_number {stored_nda!r} does not match the RLD/NDA "
                f"cell {published!r}",
            )
        ]
    return []


FTF_FIDELITY_VALIDATORS: list[Validator] = [_ftf_fidelity]
PTE_APPLICATION_FIDELITY: list[Validator] = [
    fidelity_validator("U.S. Application No", "PTE application"),
    fidelity_validator("U.S. Patent No", "PTE application"),
]
PTE_CERTIFICATE_FIDELITY: list[Validator] = [fidelity_validator("Patent No", "PTE certificate")]
PDE_FIDELITY: list[Validator] = []
ORANGE_BOOK_FIDELITY: list[Validator] = [fidelity_validator("Appl_No", "Orange Book product")]
