"""Patent Term Extension (USPTO) endpoints — applications and certificates."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_, select

from app.api.deps import SessionDep, require_scope
from app.api.export import csv_response
from app.api.schemas import Page, PteApplicationOut, PteCertificateOut
from app.db.models import PteApplication, PteCertificate
from app.intelligence.analytics import pte_extension_distribution, pte_monthly_trend, pte_summary

router = APIRouter(prefix="/pte", tags=["patent-term-extension"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/summary", summary="PTE KPI summary")
def summary(session: SessionDep) -> dict:
    return pte_summary(session)


@router.get("/applications", response_model=Page[PteApplicationOut], summary="List PTE applications")
def list_applications(
    session: SessionDep,
    q: str | None = None,
    patent_number: str | None = None,
    filed_from: date | None = None,
    filed_to: date | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[PteApplicationOut]:
    stmt = select(PteApplication).where(PteApplication.is_active.is_(True))
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(PteApplication.trade_name, "")).like(like),
                func.lower(func.coalesce(PteApplication.generic_name, "")).like(like),
                func.lower(PteApplication.patent_number).like(like),
                func.lower(PteApplication.application_number).like(like),
            )
        )
    if patent_number:
        stmt = stmt.where(PteApplication.patent_number == patent_number)
    if filed_from:
        stmt = stmt.where(PteApplication.filing_date >= filed_from)
    if filed_to:
        stmt = stmt.where(PteApplication.filing_date <= filed_to)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(PteApplication.filing_date)).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([PteApplicationOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/certificates", response_model=Page[PteCertificateOut], summary="List PTE certificates")
def list_certificates(
    session: SessionDep,
    q: str | None = None,
    patent_number: str | None = None,
    min_extension_days: int | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[PteCertificateOut]:
    stmt = select(PteCertificate).where(PteCertificate.is_active.is_(True))
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(
                func.lower(func.coalesce(PteCertificate.trade_name, "")).like(like),
                func.lower(func.coalesce(PteCertificate.generic_name, "")).like(like),
                func.lower(PteCertificate.patent_number).like(like),
            )
        )
    if patent_number:
        stmt = stmt.where(PteCertificate.patent_number == patent_number)
    if min_extension_days is not None:
        stmt = stmt.where(PteCertificate.extension_days >= min_extension_days)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(PteCertificate.extension_days)).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([PteCertificateOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/applications/{application_id}", response_model=PteApplicationOut, summary="Get one PTE application")
def get_application(application_id: str, session: SessionDep) -> PteApplicationOut:
    row = session.get(PteApplication, application_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("PTE application not found")
    return PteApplicationOut.model_validate(row)


@router.get("/certificates/{certificate_id}", response_model=PteCertificateOut, summary="Get one PTE certificate")
def get_certificate(certificate_id: str, session: SessionDep) -> PteCertificateOut:
    row = session.get(PteCertificate, certificate_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("PTE certificate not found")
    return PteCertificateOut.model_validate(row)


@router.get("/analytics/monthly-trend", summary="Monthly PTE application trend")
def monthly_trend(session: SessionDep, months: int = Query(60, ge=1, le=240)) -> list[dict]:
    return pte_monthly_trend(session, months=months)


@router.get("/analytics/extension-distribution", summary="Granted extension length distribution")
def extension_distribution(session: SessionDep) -> list[dict]:
    return pte_extension_distribution(session)


@router.get("/export/applications", summary="Export PTE applications as CSV")
def export_applications(session: SessionDep):
    rows = list(
        session.scalars(
            select(PteApplication)
            .where(PteApplication.is_active.is_(True))
            .order_by(desc(PteApplication.filing_date))
        )
    )
    columns = ["application_number", "patent_number", "trade_name", "generic_name", "filing_date"]
    return csv_response(rows, columns, filename="pte_applications.csv")


@router.get("/export/certificates", summary="Export PTE certificates as CSV")
def export_certificates(session: SessionDep):
    rows = list(
        session.scalars(
            select(PteCertificate)
            .where(PteCertificate.is_active.is_(True))
            .order_by(desc(PteCertificate.extension_days))
        )
    )
    columns = [
        "patent_number", "trade_name", "generic_name", "original_expiration_date",
        "extended_expiration_date", "extension_days",
    ]
    return csv_response(rows, columns, filename="pte_certificates.csv")
