"""Orange Book endpoints: products, patents, exclusivity, supplements."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select

from app.api.deps import SessionDep, require_scope
from app.api.export import csv_response
from app.api.schemas import (
    OrangeBookExclusivityOut,
    OrangeBookPatentOut,
    OrangeBookProductOut,
    OrangeBookSupplementOut,
    Page,
)
from app.db.models import (
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    OrangeBookSupplement,
    SourceDocument,
)
from app.intelligence.analytics import (
    orange_book_summary,
    orange_book_supplement_history,
)

router = APIRouter(prefix="/orange-book", tags=["orange-book"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/summary", summary="Orange Book KPI summary")
def summary(session: SessionDep) -> dict:
    return orange_book_summary(session)


@router.get("/products", response_model=Page[OrangeBookProductOut], summary="List Orange Book products")
def list_products(
    session: SessionDep,
    q: str | None = None,
    applicant: str | None = None,
    appl_type: str | None = Query(None, description="N = NDA, A = ANDA"),
    appl_no: str | None = None,
    te_code: str | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[OrangeBookProductOut]:
    stmt = select(OrangeBookProduct).where(OrangeBookProduct.is_active.is_(True))
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(OrangeBookProduct.trade_name, "")).like(like),
                func.lower(func.coalesce(OrangeBookProduct.ingredient, "")).like(like),
            )
        )
    if applicant:
        stmt = stmt.where(
            func.lower(func.coalesce(OrangeBookProduct.applicant_full_name, "")).like(f"%{applicant.casefold()}%")
        )
    if appl_type:
        stmt = stmt.where(OrangeBookProduct.appl_type == appl_type.upper())
    if appl_no:
        stmt = stmt.where(OrangeBookProduct.appl_no == appl_no)
    if te_code:
        stmt = stmt.where(OrangeBookProduct.te_code == te_code.upper())
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(OrangeBookProduct.appl_type, OrangeBookProduct.appl_no)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return Page.build([OrangeBookProductOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/patents", response_model=Page[OrangeBookPatentOut], summary="List Orange Book patent listings")
def list_patents(
    session: SessionDep,
    appl_no: str | None = None,
    patent_number: str | None = None,
    expiring_before: date | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[OrangeBookPatentOut]:
    stmt = select(OrangeBookPatent).where(OrangeBookPatent.is_active.is_(True))
    if appl_no:
        stmt = stmt.where(OrangeBookPatent.appl_no == appl_no)
    if patent_number:
        stmt = stmt.where(OrangeBookPatent.patent_number == patent_number)
    if expiring_before:
        stmt = stmt.where(OrangeBookPatent.expiration_date <= expiring_before)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(OrangeBookPatent.expiration_date).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([OrangeBookPatentOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/exclusivity", response_model=Page[OrangeBookExclusivityOut], summary="List exclusivity grants")
def list_exclusivity(
    session: SessionDep,
    appl_no: str | None = None,
    code: str | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[OrangeBookExclusivityOut]:
    stmt = select(OrangeBookExclusivity).where(OrangeBookExclusivity.is_active.is_(True))
    if appl_no:
        stmt = stmt.where(OrangeBookExclusivity.appl_no == appl_no)
    if code:
        stmt = stmt.where(OrangeBookExclusivity.exclusivity_code == code.upper())
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(OrangeBookExclusivity.exclusivity_date))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return Page.build([OrangeBookExclusivityOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/supplements", response_model=list[OrangeBookSupplementOut], summary="Supplement edition history")
def supplements(session: SessionDep, limit: int = Query(24, ge=1, le=120)) -> list[OrangeBookSupplementOut]:
    stmt = (
        select(OrangeBookSupplement)
        .order_by(
            desc(OrangeBookSupplement.publication_year),
            desc(OrangeBookSupplement.publication_month),
        )
        .limit(limit)
    )
    return [OrangeBookSupplementOut.model_validate(r) for r in session.scalars(stmt)]


@router.get("/supplements/compare", summary="Compare the two most recent supplement editions")
def compare_supplements(session: SessionDep) -> dict:
    from app.copilot.agent import tool_compare_supplements

    return tool_compare_supplements(session)


@router.get("/supplement/history", summary="Supplement edition deltas over time")
def supplement_history(session: SessionDep, limit: int = Query(24, ge=1, le=120)) -> list[dict]:
    return orange_book_supplement_history(session, limit=limit)


@router.get("/documents", summary="Downloadable Orange Book source documents")
def documents(session: SessionDep) -> list[dict]:
    """List the Orange Book artifacts the platform has archived, newest first."""
    rows = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.module == "orange_book")
        .order_by(desc(SourceDocument.fetched_at))
        .limit(50)
    )
    return [
        {
            "id": r.id,
            "source_code": r.source_code,
            "filename": r.filename,
            "url": r.url,
            "version": r.version,
            "is_current": r.is_current,
            "byte_size": r.byte_size,
            "publication_date": r.publication_date.isoformat() if r.publication_date else None,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


@router.get("/documents/{document_id}/download", summary="Download an archived Orange Book artifact")
def download_document(document_id: str, session: SessionDep):
    from fastapi.responses import Response

    from app.collectors.storage import get_store
    from app.core.errors import NotFoundError

    document = session.get(SourceDocument, document_id)
    if document is None or not document.storage_path:
        raise NotFoundError("Document not found")
    store = get_store()
    if not store.exists(document.storage_path):
        raise NotFoundError("Artifact is no longer in storage")
    data = store.get(document.storage_path)
    return Response(
        content=data,
        media_type=document.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.filename or "document"}"'},
    )


@router.get("/export/products", summary="Export Orange Book products as CSV")
def export_products(session: SessionDep, appl_type: str | None = None):
    stmt = select(OrangeBookProduct).where(OrangeBookProduct.is_active.is_(True))
    if appl_type:
        stmt = stmt.where(OrangeBookProduct.appl_type == appl_type.upper())
    rows = list(session.scalars(stmt.order_by(OrangeBookProduct.appl_type, OrangeBookProduct.appl_no)))
    columns = [
        "appl_type", "appl_no", "product_no", "ingredient", "trade_name", "applicant_full_name",
        "strength", "dosage_form_route", "te_code", "approval_date", "rld", "rs", "product_type",
    ]
    return csv_response(rows, columns, filename="orange_book_products.csv")
