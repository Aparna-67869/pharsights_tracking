"""Historical change tracking, insights, and audit log endpoints."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select

from app.api.deps import SessionDep, require_scope
from app.api.export import csv_response
from app.api.schemas import AuditLogOut, DetectedChangeOut, InsightOut, Page
from app.db.models import AuditLog, DetectedChange, Insight

router = APIRouter(tags=["intelligence"], dependencies=[Depends(require_scope("read:data"))])


@router.get("/changes", response_model=Page[DetectedChangeOut], summary="Detected change history")
def list_changes(
    session: SessionDep,
    module: str | None = None,
    entity_type: str | None = None,
    change_type: str | None = Query(None, description="added | updated | removed"),
    source_code: str | None = None,
    since: date | None = None,
    include_baseline: bool = Query(False, description="Include the initial snapshot rows"),
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[DetectedChangeOut]:
    stmt = select(DetectedChange)
    if module:
        stmt = stmt.where(DetectedChange.module == module)
    if entity_type:
        stmt = stmt.where(DetectedChange.entity_type == entity_type)
    if change_type:
        stmt = stmt.where(DetectedChange.change_type == change_type)
    if source_code:
        stmt = stmt.where(DetectedChange.source_code == source_code)
    if since:
        stmt = stmt.where(DetectedChange.detected_at >= datetime.combine(since, datetime.min.time()))
    if not include_baseline:
        stmt = stmt.where(DetectedChange.is_baseline.is_(False))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(DetectedChange.detected_at)).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([DetectedChangeOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/changes/export", summary="Export the change history as CSV")
def export_changes(session: SessionDep, module: str | None = None, include_baseline: bool = False):
    stmt = select(DetectedChange)
    if module:
        stmt = stmt.where(DetectedChange.module == module)
    if not include_baseline:
        stmt = stmt.where(DetectedChange.is_baseline.is_(False))
    rows = list(session.scalars(stmt.order_by(desc(DetectedChange.detected_at)).limit(50000)))
    columns = ["detected_at", "module", "entity_type", "change_type", "source_key", "is_baseline"]
    return csv_response(rows, columns, filename="change_history.csv")


@router.get("/changes/{change_id}", response_model=DetectedChangeOut, summary="Get one detected change")
def get_change(change_id: str, session: SessionDep) -> DetectedChangeOut:
    row = session.get(DetectedChange, change_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Change not found")
    return DetectedChangeOut.model_validate(row)


@router.get("/changes/{change_id}/versions", summary="Before/after comparison for a change")
def compare_change_versions(change_id: str, session: SessionDep) -> dict:
    """Return the version comparison for a change and its source document lineage."""
    from app.core.errors import NotFoundError

    change = session.get(DetectedChange, change_id)
    if change is None:
        raise NotFoundError("Change not found")
    document = change.document
    previous = None
    if change.previous_document_id:
        from app.db.models import SourceDocument

        previous = session.get(SourceDocument, change.previous_document_id)
    return {
        "change_id": change.id,
        "change_type": change.change_type,
        "entity_type": change.entity_type,
        "source_key": change.source_key,
        "field_changes": change.field_changes,
        "before": change.before,
        "after": change.after,
        "document": {
            "id": document.id,
            "version": document.version,
            "publication_date": document.publication_date.isoformat()
            if document and document.publication_date
            else None,
            "url": document.url if document else None,
        }
        if document
        else None,
        "previous_document": {
            "id": previous.id,
            "version": previous.version,
            "publication_date": previous.publication_date.isoformat()
            if previous.publication_date
            else None,
        }
        if previous
        else None,
    }


@router.get("/insights", response_model=Page[InsightOut], summary="AI-generated impact analyses")
def list_insights(
    session: SessionDep,
    module: str | None = None,
    priority_label: str | None = None,
    min_score: int | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[InsightOut]:
    stmt = select(Insight)
    if module:
        stmt = stmt.where(Insight.module == module)
    if priority_label:
        stmt = stmt.where(Insight.priority_label == priority_label)
    if min_score is not None:
        stmt = stmt.where(Insight.priority_score >= min_score)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(Insight.priority_score), desc(Insight.created_at))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return Page.build([InsightOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/insights/{insight_id}", response_model=InsightOut, summary="Get one impact analysis")
def get_insight(insight_id: str, session: SessionDep) -> InsightOut:
    row = session.get(Insight, insight_id)
    if row is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("Insight not found")
    return InsightOut.model_validate(row)


@router.get("/audit-logs", response_model=Page[AuditLogOut], summary="Audit trail")
def list_audit_logs(
    session: SessionDep,
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        session.scalars(
            stmt.order_by(desc(AuditLog.occurred_at)).limit(page_size).offset((page - 1) * page_size)
        )
    )
    return Page.build([AuditLogOut.model_validate(r) for r in rows], total, page, page_size)
