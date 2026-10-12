"""PDE (approved active moiety / written request) endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select

from app.api.deps import SessionDep, require_scope
from app.api.export import csv_response
from app.api.schemas import ActiveMoietyOut, Page
from app.db.models import ActiveMoiety
from app.intelligence.analytics import pde_summary, pde_top_sponsors, pde_yearly_trend

router = APIRouter(prefix="/pde", tags=["approved-active-moiety"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/summary", summary="PDE KPI summary")
def summary(session: SessionDep) -> dict:
    return pde_summary(session)


@router.get("/moieties", response_model=Page[ActiveMoietyOut], summary="List approved active moieties")
def list_moieties(
    session: SessionDep,
    q: str | None = None,
    sponsor: str | None = None,
    year: int | None = None,
    issued_from: date | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[ActiveMoietyOut]:
    stmt = select(ActiveMoiety).where(ActiveMoiety.is_active.is_(True))
    if q:
        stmt = stmt.where(func.lower(ActiveMoiety.moiety_name).like(f"%{q.casefold()}%"))
    if sponsor:
        stmt = stmt.where(func.lower(func.coalesce(ActiveMoiety.sponsor_name, "")).like(f"%{sponsor.casefold()}%"))
    if year:
        stmt = stmt.where(ActiveMoiety.approval_year == year)
    if issued_from:
        stmt = stmt.where(ActiveMoiety.date_issued >= issued_from)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(ActiveMoiety.date_issued)).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([ActiveMoietyOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/moieties/{moiety_id}", response_model=ActiveMoietyOut, summary="Get one active moiety")
def get_moiety(moiety_id: str, session: SessionDep) -> ActiveMoietyOut:
    row = session.get(ActiveMoiety, moiety_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Active moiety not found")
    return ActiveMoietyOut.model_validate(row)


@router.get("/analytics/yearly-trend", summary="Approved active moieties by year")
def yearly_trend(session: SessionDep, years: int = Query(15, ge=1, le=60)) -> list[dict]:
    return pde_yearly_trend(session, years=years)


@router.get("/analytics/top-sponsors", summary="Top sponsors by approved active moieties")
def top_sponsors(session: SessionDep, limit: int = Query(15, ge=1, le=100)) -> list[dict]:
    return pde_top_sponsors(session, limit=limit)


@router.get("/export", summary="Export approved active moieties as CSV")
def export(session: SessionDep):
    rows = list(
        session.scalars(
            select(ActiveMoiety)
            .where(ActiveMoiety.is_active.is_(True))
            .order_by(desc(ActiveMoiety.date_issued))
        )
    )
    columns = ["moiety_name", "sponsor_name", "date_issued", "approval_year", "status"]
    return csv_response(rows, columns, filename="approved_active_moieties.csv")
