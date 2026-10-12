"""Global search, 360-degree drug view, and knowledge-graph endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select

from app.api.deps import SessionDep, require_scope
from app.api.schemas import (
    DrugDetailOut,
    GraphNeighborhoodOut,
    SearchResultOut,
)
from app.core.errors import NotFoundError
from app.db.models import (
    ActiveMoiety,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)
from app.graph.builder import graph_stats, neighborhood
from app.search.global_search import search as global_search

router = APIRouter(tags=["search", "graph"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/search", response_model=SearchResultOut, summary="Global unified search")
def search(
    session: SessionDep,
    q: str = Query(..., min_length=1, description="Drug, patent, NDA/ANDA, sponsor, moiety, NCT ID"),
    entity_types: list[str] | None = Query(None),
    limit: int = Query(25, ge=1, le=200),
) -> SearchResultOut:
    result = global_search(session, q, entity_types=entity_types, limit=limit)
    return SearchResultOut.model_validate(result.to_dict())


@router.get("/drugs/{drug_id}/360", summary="360-degree view of a drug")
def drug_360(drug_id: str, session: SessionDep) -> dict:
    """Everything the platform knows about one drug, across every module."""
    drug = session.get(Drug, drug_id)
    if drug is None:
        raise NotFoundError("Drug not found")

    sponsor = session.get(Sponsor, drug.sponsor_id) if drug.sponsor_id else None

    ftf = list(
        session.scalars(
            select(FtfRecord).where(FtfRecord.drug_id == drug.id, FtfRecord.is_active.is_(True))
        )
    )
    pte_apps = list(
        session.scalars(
            select(PteApplication).where(PteApplication.drug_id == drug.id, PteApplication.is_active.is_(True))
        )
    )
    pte_certs = list(
        session.scalars(
            select(PteCertificate).where(PteCertificate.drug_id == drug.id, PteCertificate.is_active.is_(True))
        )
    )
    moieties = list(
        session.scalars(
            select(ActiveMoiety).where(ActiveMoiety.drug_id == drug.id, ActiveMoiety.is_active.is_(True))
        )
    )

    product_ids = [p.id for p in ftf]
    patents = list(
        session.scalars(
            select(Patent).where(
                Patent.id.in_([r.patent_id for r in ftf if r.patent_id] + [r.patent_id for r in pte_certs if r.patent_id])
            )
        )
    ) if (any(r.patent_id for r in ftf) or any(r.patent_id for r in pte_certs)) else []

    ob_products = list(
        session.scalars(
            select(OrangeBookProduct).where(
                OrangeBookProduct.drug_id == drug.id, OrangeBookProduct.is_active.is_(True)
            )
        )
    )
    ob_patents: list[OrangeBookPatent] = []
    ob_exclusivity: list[OrangeBookExclusivity] = []
    if ob_products:
        appl_keys = {(p.appl_type, p.appl_no) for p in ob_products}
        ob_patents = list(
            session.scalars(
                select(OrangeBookPatent).where(
                    OrangeBookPatent.is_active.is_(True),
                    OrangeBookPatent.appl_no.in_([k[1] for k in appl_keys]),
                )
            )
        )
        ob_exclusivity = list(
            session.scalars(
                select(OrangeBookExclusivity).where(
                    OrangeBookExclusivity.is_active.is_(True),
                    OrangeBookExclusivity.appl_no.in_([k[1] for k in appl_keys]),
                )
            )
        )

    insights = list(
        session.scalars(
            select(Insight)
            .where(Insight.entity_key.in_([drug.normalized_name] + [r.source_key for r in ftf]))
            .order_by(desc(Insight.priority_score))
            .limit(20)
        )
    )

    return {
        "drug": DrugDetailOut.model_validate(drug).model_dump(),
        "sponsor": {"id": sponsor.id, "name": sponsor.name} if sponsor else None,
        "paragraph_iv_filings": [
            {
                "id": r.id,
                "nda_number": r.nda_number,
                "rld_brand_name": r.rld_brand_name,
                "date_of_submission": r.date_of_submission.isoformat() if r.date_of_submission else None,
                "exclusivity_status": r.exclusivity_status,
                "number_of_andas": r.number_of_andas,
                "last_qualifying_patent_expiry": r.last_qualifying_patent_expiry.isoformat()
                if r.last_qualifying_patent_expiry
                else None,
            }
            for r in ftf
        ],
        "pte_applications": [
            {
                "id": r.id,
                "application_number": r.application_number,
                "patent_number": r.patent_number,
                "filing_date": r.filing_date.isoformat() if r.filing_date else None,
            }
            for r in pte_apps
        ],
        "pte_certificates": [
            {
                "id": r.id,
                "patent_number": r.patent_number,
                "extension_days": r.extension_days,
                "extended_expiration_date": r.extended_expiration_date.isoformat()
                if r.extended_expiration_date
                else None,
            }
            for r in pte_certs
        ],
        "active_moieties": [
            {
                "id": r.id,
                "moiety_name": r.moiety_name,
                "date_issued": r.date_issued.isoformat() if r.date_issued else None,
            }
            for r in moieties
        ],
        "patents": [
            {
                "id": p.id,
                "patent_number": p.patent_number,
                "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
                "has_pte": p.has_pte,
                "has_paragraph_iv": p.has_paragraph_iv,
            }
            for p in patents
        ],
        "orange_book_products": [
            {
                "id": p.id,
                "application": f"{p.appl_type}{p.appl_no}",
                "trade_name": p.trade_name,
                "te_code": p.te_code,
                "approval_date": p.approval_date.isoformat() if p.approval_date else None,
            }
            for p in ob_products
        ],
        "orange_book_patents": [
            {
                "patent_number": p.patent_number,
                "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
                "use_code": p.patent_use_code,
            }
            for p in ob_patents
        ],
        "orange_book_exclusivity": [
            {
                "code": e.exclusivity_code,
                "date": e.exclusivity_date.isoformat() if e.exclusivity_date else None,
            }
            for e in ob_exclusivity
        ],
        "insights": [
            {
                "id": i.id,
                "title": i.title,
                "priority_label": i.priority_label,
                "priority_score": i.priority_score,
                "recommended_action": i.recommended_action,
            }
            for i in insights
        ],
    }


@router.get("/drugs", response_model=list[DrugDetailOut], summary="Search canonical drugs")
def list_drugs(
    session: SessionDep,
    q: str | None = None,
    therapy_area: str | None = None,
    limit: int = Query(25, ge=1, le=200),
) -> list[DrugDetailOut]:
    stmt = select(Drug)
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(func.lower(Drug.name).like(like), func.lower(func.coalesce(Drug.ingredient, "")).like(like))
        )
    if therapy_area:
        stmt = stmt.where(func.lower(Drug.therapy_area) == therapy_area.casefold())
    return [DrugDetailOut.model_validate(r) for r in session.scalars(stmt.limit(limit))]


@router.get("/sponsors", summary="List canonical sponsors")
def list_sponsors(session: SessionDep, q: str | None = None, limit: int = Query(25, ge=1, le=200)) -> list[dict]:
    stmt = select(Sponsor)
    if q:
        stmt = stmt.where(func.lower(Sponsor.name).like(f"%{q.casefold()}%"))
    return [
        {"id": s.id, "name": s.name, "type": s.sponsor_type, "importance_score": s.importance_score}
        for s in session.scalars(stmt.order_by(desc(Sponsor.importance_score)).limit(limit))
    ]


@router.get("/patents", summary="List patents")
def list_patents(
    session: SessionDep,
    q: str | None = None,
    expiring_before: str | None = None,
    limit: int = Query(25, ge=1, le=200),
) -> list[dict]:
    stmt = select(Patent)
    if q:
        stmt = stmt.where(Patent.patent_number.ilike(f"%{q}%"))
    if expiring_before:
        from datetime import date

        stmt = stmt.where(Patent.expiration_date <= date.fromisoformat(expiring_before))
    return [
        {
            "id": p.id,
            "patent_number": p.patent_number,
            "expiration_date": p.expiration_date.isoformat() if p.expiration_date else None,
            "assignee": p.assignee,
            "has_pte": p.has_pte,
            "has_paragraph_iv": p.has_paragraph_iv,
        }
        for p in session.scalars(stmt.order_by(Patent.expiration_date).limit(limit))
    ]


@router.get("/graph/stats", summary="Knowledge graph statistics")
def stats(session: SessionDep) -> dict:
    return graph_stats(session)


@router.get(
    "/graph/nodes/{node_type}/{natural_key}/neighborhood",
    response_model=GraphNeighborhoodOut,
    summary="Knowledge graph neighbourhood (360-degree traversal)",
)
def node_neighborhood(
    node_type: str,
    natural_key: str,
    session: SessionDep,
    depth: int = Query(1, ge=1, le=4),
    max_nodes: int = Query(200, ge=1, le=1000),
) -> GraphNeighborhoodOut:
    result = neighborhood(session, node_type=node_type, natural_key=natural_key, depth=depth, max_nodes=max_nodes)
    if result is None:
        raise NotFoundError("Graph node not found")
    return GraphNeighborhoodOut.model_validate(result.to_dict())
