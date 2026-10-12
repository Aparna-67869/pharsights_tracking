"""Executive dashboard endpoints: KPIs, charts, and saved views."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, or_, select

from app.alerts.engine import alert_summary
from app.api.deps import PrincipalDep, SessionDep, audit, require_scope
from app.api.schemas import KpiOut, SavedViewIn, SavedViewOut
from app.core.errors import NotFoundError
from app.db.models import SavedView
from app.intelligence.analytics import (
    executive_kpis,
    ftf_summary,
    generic_opportunity_heatmap,
    monthly_fda_activity,
    orange_book_summary,
    patent_expiry_timeline,
    patent_family_distribution,
    pde_summary,
    pte_summary,
    sponsor_leaderboard,
    therapy_area_analysis,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/kpis", response_model=KpiOut, summary="Executive KPI strip")
def kpis(session: SessionDep) -> KpiOut:
    return KpiOut(kpis=executive_kpis(session), alerts=alert_summary(session))


@router.get("/module-summaries", summary="Per-module KPI summaries")
def module_summaries(session: SessionDep) -> dict:
    return {
        "ftf": ftf_summary(session),
        "pte": pte_summary(session),
        "pde": pde_summary(session),
        "orange_book": orange_book_summary(session),
    }


@router.get("/charts/patent-expiry-timeline", summary="Patent expiry timeline")
def chart_patent_expiry(session: SessionDep, years: int = Query(10, ge=1, le=30)) -> list[dict]:
    return patent_expiry_timeline(session, years=years)


@router.get("/charts/sponsor-leaderboard", summary="Sponsor leaderboard")
def chart_sponsor_leaderboard(session: SessionDep, limit: int = Query(15, ge=1, le=100)) -> list[dict]:
    return sponsor_leaderboard(session, limit=limit)


@router.get("/charts/therapy-areas", summary="Therapy area analysis")
def chart_therapy_areas(session: SessionDep) -> list[dict]:
    return therapy_area_analysis(session)


@router.get("/charts/monthly-fda-activity", summary="Monthly FDA activity across modules")
def chart_monthly_activity(session: SessionDep, months: int = Query(24, ge=1, le=120)) -> list[dict]:
    return monthly_fda_activity(session, months=months)


@router.get("/charts/generic-opportunity-heatmap", summary="Generic opportunity heatmap")
def chart_heatmap(session: SessionDep, limit: int = Query(25, ge=1, le=200)) -> list[dict]:
    return generic_opportunity_heatmap(session, limit=limit)


@router.get("/charts/patent-family-distribution", summary="Patent family distribution by assignee")
def chart_family_distribution(session: SessionDep, limit: int = Query(10, ge=1, le=100)) -> list[dict]:
    return patent_family_distribution(session, limit=limit)


@router.get("/charts/all", summary="Every dashboard chart in one payload")
def chart_all(session: SessionDep) -> dict:
    """Single call the dashboard uses to hydrate all charts at once."""
    return {
        "patent_expiry_timeline": patent_expiry_timeline(session, years=10),
        "sponsor_leaderboard": sponsor_leaderboard(session, limit=15),
        "therapy_area_analysis": therapy_area_analysis(session),
        "monthly_fda_activity": monthly_fda_activity(session, months=24),
        "generic_opportunity_heatmap": generic_opportunity_heatmap(session, limit=25),
        "patent_family_distribution": patent_family_distribution(session, limit=10),
    }


# ---- Saved views -----------------------------------------------------------


@router.get("/views", response_model=list[SavedViewOut], summary="List saved views")
def list_views(
    session: SessionDep,
    principal: PrincipalDep,
    module: str | None = None,
) -> list[SavedViewOut]:
    stmt = select(SavedView).where(
        or_(SavedView.is_shared.is_(True), SavedView.owner_id == principal.user_id)
    )
    if module:
        stmt = stmt.where(SavedView.module == module)
    return [SavedViewOut.model_validate(r) for r in session.scalars(stmt.order_by(desc(SavedView.created_at)))]


@router.post("/views", response_model=SavedViewOut, summary="Create a saved view")
def create_view(
    payload: SavedViewIn,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> SavedViewOut:
    view = SavedView(
        owner_id=principal.user_id,
        name=payload.name,
        module=payload.module or "general",
        filters=payload.filters,
        is_shared=payload.is_shared,
    )
    session.add(view)
    audit(
        session,
        actor=principal.username,
        action="create_saved_view",
        resource_type="saved_view",
        resource_id=view.id,
        detail={"name": payload.name},
        request=request,
    )
    session.commit()
    return SavedViewOut.model_validate(view)


@router.delete("/views/{view_id}", summary="Delete a saved view")
def delete_view(
    view_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> dict:
    view = session.get(SavedView, view_id)
    if view is None:
        raise NotFoundError("Saved view not found")
    if view.owner_id and view.owner_id != principal.user_id and principal.role.value != "admin":
        from app.core.errors import AuthorizationError

        raise AuthorizationError("You can only delete your own saved views")
    session.delete(view)
    audit(
        session,
        actor=principal.username,
        action="delete_saved_view",
        resource_type="saved_view",
        resource_id=view_id,
        request=request,
    )
    session.commit()
    return {"deleted": True, "id": view_id}
