"""First-to-File (Paragraph IV certification) endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, desc, func, or_, select

from app.api.deps import SessionDep, require_scope
from app.api.schemas import FtfRecordOut, Page
from app.db.models import FtfRecord
from app.intelligence.analytics import ftf_monthly_trend, ftf_summary, ftf_top_therapy_areas

router = APIRouter(prefix="/ftf", tags=["first-to-file"], dependencies=[Depends(require_scope("read:data"))])


def _filtered(
    q: str | None,
    applicant: str | None,
    nda: str | None,
    patent: str | None,
    status: str | None,
    submitted_from: date | None,
    submitted_to: date | None,
    expiring_before: date | None,
) -> Select:
    stmt = select(FtfRecord).where(FtfRecord.is_active.is_(True))
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(
                func.lower(FtfRecord.drug_name).like(like),
                func.lower(func.coalesce(FtfRecord.rld_brand_name, "")).like(like),
                func.lower(func.coalesce(FtfRecord.nda_number, "")).like(like),
                func.lower(func.coalesce(FtfRecord.rld_nda, "")).like(like),
            )
        )
    if applicant:
        stmt = stmt.where(func.lower(func.coalesce(FtfRecord.rld_brand_name, "")).like(f"%{applicant.casefold()}%"))
    if nda:
        stmt = stmt.where(FtfRecord.nda_number == nda)
    if patent:
        stmt = stmt.where(FtfRecord.patent_number == patent)
    if status:
        stmt = stmt.where(func.lower(FtfRecord.exclusivity_status) == status.casefold())
    if submitted_from:
        stmt = stmt.where(FtfRecord.date_of_submission >= submitted_from)
    if submitted_to:
        stmt = stmt.where(FtfRecord.date_of_submission <= submitted_to)
    if expiring_before:
        stmt = stmt.where(FtfRecord.last_qualifying_patent_expiry <= expiring_before)
    return stmt


@router.get("/records", response_model=Page[FtfRecordOut], summary="List Paragraph IV filings")
def list_records(
    session: SessionDep,
    q: str | None = Query(None, description="Free-text across drug, brand, NDA"),
    applicant: str | None = None,
    nda: str | None = None,
    patent: str | None = None,
    status: str | None = Query(None, description="eligible | extinguished | deferred"),
    submitted_from: date | None = None,
    submitted_to: date | None = None,
    expiring_before: date | None = None,
    sort: str = Query(
        "source",
        description="source = the FDA list's own order | drug = A–Z by drug name | submitted = newest filing first",
    ),
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[FtfRecordOut]:
    stmt = _filtered(q, applicant, nda, patent, status, submitted_from, submitted_to, expiring_before)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort == "submitted":
        order = (desc(FtfRecord.date_of_submission), func.lower(FtfRecord.drug_name))
    elif sort == "drug":
        order = (func.lower(FtfRecord.drug_name), func.lower(func.coalesce(FtfRecord.rld_nda, "")))
    else:
        # The FDA publishes the list in its own sequence (drug, then RLD/NDA).
        # Render exactly that order so the table reads the way the PDF does —
        # "Abacavir Sulfate" then "Abacavir", not a normalized A–Z sort.
        order = (
            FtfRecord.source_ordinal.asc().nulls_last(),
            func.lower(func.coalesce(FtfRecord.rld_nda, "")),
        )
    rows = list(
        session.scalars(stmt.order_by(*order).limit(page_size).offset((page - 1) * page_size))
    )
    return Page.build([FtfRecordOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/records/{record_id}", response_model=FtfRecordOut, summary="Get one Paragraph IV filing")
def get_record(record_id: str, session: SessionDep) -> FtfRecordOut:
    row = session.get(FtfRecord, record_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Paragraph IV record not found")
    return FtfRecordOut.model_validate(row)


@router.get("/summary", summary="FTF KPI summary", dependencies=[__import__("fastapi").Depends(require_scope("read:data"))])
def summary(session: SessionDep) -> dict:
    return ftf_summary(session)


@router.get("/source", summary="Current FDA Paragraph IV document (publication date, version)")
def source_info(session: SessionDep) -> dict:
    """Metadata for the FDA Paragraph IV list currently loaded.

    The SOP requires the publication date printed at the top of the PDF; we
    surface the date parsed out of the document itself, plus the version and
    record count, so the dashboard can show the same header the source shows.
    """
    from app.db.models import SourceDocument
    from app.services.document_actions import MODULE_SOURCE

    doc = session.scalars(
        select(SourceDocument)
        .where(
            SourceDocument.source_code == MODULE_SOURCE["ftf"],
            SourceDocument.is_current.is_(True),
        )
        .order_by(desc(SourceDocument.fetched_at))
    ).first()
    if doc is None:
        return {"publication_date": None, "publication_label": None}
    return {
        "source_code": doc.source_code,
        "filename": doc.filename,
        "version": doc.version,
        "record_count": doc.record_count,
        "source_record_count": doc.source_record_count,
        "publication_date": doc.publication_date.isoformat() if doc.publication_date else None,
        "publication_label": doc.publication_label,
        "fetched_at": doc.fetched_at.isoformat() if doc.fetched_at else None,
        "url": doc.url,
    }


@router.get("/analytics/monthly-trend", summary="Monthly Paragraph IV filing trend")
def monthly_trend(session: SessionDep, months: int = Query(36, ge=1, le=240)) -> list[dict]:
    return ftf_monthly_trend(session, months=months)


@router.get("/analytics/therapy-areas", summary="Paragraph IV filings by therapy area")
def therapy_areas(session: SessionDep, limit: int = Query(10, ge=1, le=50)) -> list[dict]:
    return ftf_top_therapy_areas(session, limit=limit)


@router.get("/export", summary="Export the filtered Paragraph IV list (CSV or Excel)")
def export(
    session: SessionDep,
    q: str | None = None,
    status: str | None = None,
    format: str = Query("csv", pattern="^(csv|xlsx)$", description="csv | xlsx"),
):
    from app.api.export import csv_response, xlsx_response

    stmt = _filtered(q, None, None, None, status, None, None, None).order_by(
        func.lower(FtfRecord.drug_name)
    )
    rows = list(session.scalars(stmt))
    columns = [
        "drug_name", "dosage_form", "strength", "rld_nda", "rld_brand_name", "nda_number",
        "date_of_submission", "number_of_andas", "exclusivity_status", "decision_posting_date",
        "first_applicant_approval_date", "first_commercial_marketing_date",
        "last_qualifying_patent_expiry",
    ]
    headers = [c.replace("_", " ").title() for c in columns]
    if format == "xlsx":
        return xlsx_response(
            rows, columns, filename="ftf_paragraph_iv.xlsx", headers=headers, sheet_name="Paragraph IV"
        )
    return csv_response(rows, columns, filename="ftf_paragraph_iv.csv", headers=headers)
