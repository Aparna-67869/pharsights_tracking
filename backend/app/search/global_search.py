"""Unified global search across every entity type.

One query box resolves drug names, patent numbers, NDA/ANDA numbers, sponsors,
active moieties and NCT IDs. Results carry the entity type and a relevance score
so the UI can group them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.text import (
    normalize_company_name,
    normalize_drug_name,
    normalize_nda_number,
    normalize_patent_number,
)
from app.db.models import (
    ActiveMoiety,
    Drug,
    FtfRecord,
    OrangeBookProduct,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)

log = get_logger(__name__)


@dataclass
class SearchHit:
    entity_type: str
    id: str
    title: str
    subtitle: str | None = None
    score: float = 0.0
    matched_on: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "score": round(self.score, 3),
            "matched_on": self.matched_on,
            "attributes": self.attributes,
            "url": self.url,
        }


@dataclass
class SearchResult:
    query: str
    interpreted_as: dict[str, str | None]
    total: int
    hits: list[SearchHit]
    facets: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "interpreted_as": self.interpreted_as,
            "total": self.total,
            "hits": [h.to_dict() for h in self.hits],
            "facets": self.facets,
        }


def interpret_query(query: str) -> dict[str, str | None]:
    """Classify the raw query so the right indexes are searched first."""
    raw = (query or "").strip()
    lowered = raw.casefold()
    interpretation: dict[str, str | None] = {
        "raw": raw,
        "patent_number": None,
        "nda_number": None,
        "nct_id": None,
        "drug_key": None,
        "sponsor_key": None,
    }
    if lowered.startswith("nct") and any(c.isdigit() for c in lowered):
        interpretation["nct_id"] = raw.upper()
    if any(ch.isdigit() for ch in raw):
        candidate = normalize_patent_number(raw)
        if candidate and (len(candidate) >= 6 or candidate.startswith(("RE", "US"))):
            interpretation["patent_number"] = candidate
        interpretation["nda_number"] = normalize_nda_number(raw)
    interpretation["drug_key"] = normalize_drug_name(raw)
    interpretation["sponsor_key"] = normalize_company_name(raw)
    return interpretation


def _score_exact(is_exact: bool, base: float) -> float:
    return base * (2.0 if is_exact else 1.0)


def search(
    session: Session,
    query: str,
    *,
    entity_types: list[str] | None = None,
    limit: int = 25,
) -> SearchResult:
    """Execute a unified search and return ranked, faceted hits."""
    raw = (query or "").strip()
    if not raw:
        return SearchResult(query="", interpreted_as={}, total=0, hits=[], facets={})

    interpretation = interpret_query(raw)
    like = f"%{raw.casefold()}%"
    drug_key = interpretation["drug_key"] or ""
    sponsor_key = interpretation["sponsor_key"] or ""
    patent_number = interpretation["patent_number"]
    nda_number = interpretation["nda_number"]

    hits: list[SearchHit] = []
    wanted = set(entity_types) if entity_types else None

    def want(entity_type: str) -> bool:
        return wanted is None or entity_type in wanted

    # ---- Drugs ----
    if want("drug"):
        stmt = (
            select(Drug)
            .where(
                or_(
                    func.lower(Drug.name).like(like),
                    Drug.normalized_name.like(f"%{drug_key}%"),
                    func.lower(func.coalesce(Drug.ingredient, "")).like(like),
                    func.lower(func.coalesce(Drug.therapy_area, "")).like(like),
                )
            )
            .limit(limit)
        )
        for drug in session.scalars(stmt):
            exact = drug.normalized_name == drug_key
            hits.append(
                SearchHit(
                    entity_type="drug",
                    id=drug.id,
                    title=drug.name,
                    subtitle=drug.ingredient or drug.therapy_area,
                    score=_score_exact(exact, 0.9),
                    matched_on="drug name",
                    attributes={
                        "therapy_area": drug.therapy_area,
                        "rld_nda": drug.rld_nda,
                        "brand_names": drug.brand_names,
                    },
                    url=f"/drugs/{drug.id}",
                )
            )

    # ---- Patents ----
    if want("patent"):
        conditions = [
            func.lower(Patent.patent_number).like(like),
            func.lower(func.coalesce(Patent.assignee, "")).like(like),
        ]
        if patent_number:
            conditions.append(Patent.normalized_number == patent_number)
        stmt = select(Patent).where(or_(*conditions)).limit(limit)
        for patent in session.scalars(stmt):
            exact = patent_number is not None and patent.normalized_number == patent_number
            hits.append(
                SearchHit(
                    entity_type="patent",
                    id=patent.id,
                    title=patent.patent_number,
                    subtitle=patent.assignee,
                    score=_score_exact(exact, 0.85),
                    matched_on="patent number",
                    attributes={
                        "expiration_date": patent.expiration_date.isoformat()
                        if patent.expiration_date
                        else None,
                        "has_pte": patent.has_pte,
                        "has_paragraph_iv": patent.has_paragraph_iv,
                    },
                    url=f"/patents/{patent.id}",
                )
            )

    # ---- Sponsors ----
    if want("sponsor"):
        stmt = (
            select(Sponsor)
            .where(
                or_(
                    func.lower(Sponsor.name).like(like),
                    Sponsor.normalized_name.like(f"%{sponsor_key}%"),
                )
            )
            .limit(limit)
        )
        for sponsor in session.scalars(stmt):
            exact = sponsor.normalized_name == sponsor_key
            hits.append(
                SearchHit(
                    entity_type="sponsor",
                    id=sponsor.id,
                    title=sponsor.name,
                    subtitle=sponsor.sponsor_type,
                    score=_score_exact(exact, 0.8),
                    matched_on="sponsor name",
                    attributes={"aliases": sponsor.aliases},
                    url=f"/sponsors/{sponsor.id}",
                )
            )

    # ---- FTF ----
    if want("ftf_record"):
        conditions = [
            func.lower(FtfRecord.drug_name).like(like),
            func.lower(func.coalesce(FtfRecord.rld_nda, "")).like(like),
            func.lower(func.coalesce(FtfRecord.nda_number, "")).like(like),
        ]
        if nda_number:
            conditions.append(FtfRecord.nda_number == nda_number)
        stmt = (
            select(FtfRecord)
            .where(FtfRecord.is_active.is_(True), or_(*conditions))
            .limit(limit)
        )
        for row in session.scalars(stmt):
            exact = bool(nda_number) and row.nda_number == nda_number
            hits.append(
                SearchHit(
                    entity_type="ftf_record",
                    id=row.id,
                    title=f"{row.drug_name} — Paragraph IV",
                    subtitle=f"{row.rld_brand_name or ''} {row.nda_number or ''}".strip(),
                    score=_score_exact(exact, 0.75),
                    matched_on="Paragraph IV filing",
                    attributes={
                        "submission_date": row.date_of_submission.isoformat()
                        if row.date_of_submission
                        else None,
                        "exclusivity_status": row.exclusivity_status,
                        "number_of_andas": row.number_of_andas,
                    },
                    url=f"/ftf/{row.id}",
                )
            )

    # ---- PTE applications ----
    if want("pte_application"):
        stmt = (
            select(PteApplication)
            .where(
                PteApplication.is_active.is_(True),
                or_(
                    func.lower(PteApplication.patent_number).like(like),
                    func.lower(func.coalesce(PteApplication.trade_name, "")).like(like),
                    func.lower(func.coalesce(PteApplication.generic_name, "")).like(like),
                    func.lower(PteApplication.application_number).like(like),
                ),
            )
            .limit(limit)
        )
        for row in session.scalars(stmt):
            hits.append(
                SearchHit(
                    entity_type="pte_application",
                    id=row.id,
                    title=f"PTE application {row.application_number}",
                    subtitle=f"{row.trade_name or ''} (patent {row.patent_number})".strip(),
                    score=0.7,
                    matched_on="PTE application",
                    attributes={
                        "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                    },
                    url=f"/pte/applications/{row.id}",
                )
            )

    # ---- PTE certificates ----
    if want("pte_certificate"):
        stmt = (
            select(PteCertificate)
            .where(
                PteCertificate.is_active.is_(True),
                or_(
                    func.lower(PteCertificate.patent_number).like(like),
                    func.lower(func.coalesce(PteCertificate.trade_name, "")).like(like),
                    func.lower(func.coalesce(PteCertificate.generic_name, "")).like(like),
                ),
            )
            .limit(limit)
        )
        for row in session.scalars(stmt):
            hits.append(
                SearchHit(
                    entity_type="pte_certificate",
                    id=row.id,
                    title=f"PTE certificate {row.patent_number}",
                    subtitle=f"{row.trade_name or ''} (+{row.extension_days or '?'} days)".strip(),
                    score=0.7,
                    matched_on="PTE certificate",
                    attributes={"extension_days": row.extension_days},
                    url=f"/pte/certificates/{row.id}",
                )
            )

    # ---- Active moieties ----
    if want("active_moiety"):
        stmt = (
            select(ActiveMoiety)
            .where(
                ActiveMoiety.is_active.is_(True),
                or_(
                    func.lower(ActiveMoiety.moiety_name).like(like),
                    func.lower(func.coalesce(ActiveMoiety.sponsor_name, "")).like(like),
                ),
            )
            .limit(limit)
        )
        for row in session.scalars(stmt):
            hits.append(
                SearchHit(
                    entity_type="active_moiety",
                    id=row.id,
                    title=row.moiety_name,
                    subtitle=row.sponsor_name,
                    score=0.7,
                    matched_on="active moiety",
                    attributes={
                        "date_issued": row.date_issued.isoformat() if row.date_issued else None
                    },
                    url=f"/pde/{row.id}",
                )
            )

    # ---- Orange Book products ----
    if want("orange_book_product"):
        conditions = [
            func.lower(func.coalesce(OrangeBookProduct.trade_name, "")).like(like),
            func.lower(func.coalesce(OrangeBookProduct.ingredient, "")).like(like),
            func.lower(func.coalesce(OrangeBookProduct.applicant_full_name, "")).like(like),
        ]
        if nda_number:
            conditions.append(OrangeBookProduct.appl_no == nda_number)
        stmt = (
            select(OrangeBookProduct)
            .where(OrangeBookProduct.is_active.is_(True), or_(*conditions))
            .limit(limit)
        )
        for row in session.scalars(stmt):
            exact = bool(nda_number) and row.appl_no == nda_number
            hits.append(
                SearchHit(
                    entity_type="orange_book_product",
                    id=row.id,
                    title=f"{row.trade_name or row.ingredient} ({row.appl_type}{row.appl_no})",
                    subtitle=row.applicant_full_name or row.applicant,
                    score=_score_exact(exact, 0.75),
                    matched_on="Orange Book listing",
                    attributes={
                        "te_code": row.te_code,
                        "approval_date": row.approval_date.isoformat()
                        if row.approval_date
                        else None,
                    },
                    url=f"/orange-book/products/{row.id}",
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[:limit]

    facets: dict[str, int] = {}
    for hit in hits:
        facets[hit.entity_type] = facets.get(hit.entity_type, 0) + 1

    return SearchResult(
        query=raw,
        interpreted_as=interpretation,
        total=len(hits),
        hits=hits,
        facets=facets,
    )
