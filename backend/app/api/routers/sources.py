"""Source registry, collection runs, and pipeline control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import desc, func, select

from app.api.deps import PrincipalDep, SessionDep, audit, require_scope
from app.api.schemas import (
    CollectionRunOut,
    Page,
    PipelineRunOut,
    PipelineTriggerRequest,
    SourceDocumentOut,
    SourceOut,
)
from app.core.errors import NotFoundError
from app.db.models import CollectionRun, PipelineRun, SourceDefinition, SourceDocument

router = APIRouter(prefix="/sources", tags=["sources"], dependencies=[Depends(require_scope("read:data"))])


@router.get("", response_model=list[SourceOut], summary="Monitored source registry")
def list_sources(session: SessionDep) -> list[SourceOut]:
    rows = session.scalars(select(SourceDefinition).order_by(SourceDefinition.module, SourceDefinition.code))
    return [SourceOut.model_validate(r) for r in rows]


@router.get("/{code}", response_model=SourceOut, summary="Get one source definition")
def get_source(code: str, session: SessionDep) -> SourceOut:
    row = session.scalars(select(SourceDefinition).where(SourceDefinition.code == code)).first()
    if row is None:
        raise NotFoundError("Source not found")
    return SourceOut.model_validate(row)


@router.get("/{code}/documents", response_model=Page[SourceDocumentOut], summary="Document versions for a source")
def source_documents(
    code: str,
    session: SessionDep,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[SourceDocumentOut]:
    stmt = select(SourceDocument).where(SourceDocument.source_code == code).order_by(
        desc(SourceDocument.version)
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return Page.build([SourceDocumentOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/{code}/runs", response_model=Page[CollectionRunOut], summary="Collection history for a source")
def source_runs(
    code: str,
    session: SessionDep,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[CollectionRunOut]:
    stmt = select(CollectionRun).where(CollectionRun.source_code == code).order_by(
        desc(CollectionRun.started_at)
    )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return Page.build([CollectionRunOut.model_validate(r) for r in rows], total, page, page_size)


# ---- Pipeline --------------------------------------------------------------


pipeline_router = APIRouter(
    prefix="/pipeline", tags=["pipeline"], dependencies=[Depends(require_scope("read:data"))]
)


@pipeline_router.get("/runs", response_model=Page[PipelineRunOut], summary="Pipeline run history")
def pipeline_runs(
    session: SessionDep,
    page: int = 1,
    page_size: int = Query(50, le=500),
) -> Page[PipelineRunOut]:
    stmt = select(PipelineRun).order_by(desc(PipelineRun.started_at))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return Page.build([PipelineRunOut.model_validate(r) for r in rows], total, page, page_size)


@pipeline_router.get("/runs/{run_id}", response_model=PipelineRunOut, summary="Get one pipeline run")
def pipeline_run(run_id: str, session: SessionDep) -> PipelineRunOut:
    row = session.get(PipelineRun, run_id)
    if row is None:
        raise NotFoundError("Pipeline run not found")
    return PipelineRunOut.model_validate(row)


@pipeline_router.post(
    "/run",
    summary="Trigger a pipeline run",
    dependencies=[__import__("fastapi").Depends(require_scope("run:pipeline"))],
)
def trigger_pipeline(
    payload: PipelineTriggerRequest,
    background: BackgroundTasks,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> dict:
    """Run the full collect -> detect -> analyze -> alert pipeline.

    The run executes in the background so the request returns immediately; poll
    ``/pipeline/runs`` for the outcome.
    """
    audit(
        session,
        actor=principal.username,
        action="trigger_pipeline",
        resource_type="pipeline",
        detail=payload.model_dump(),
        request=request,
    )
    session.commit()

    def _run() -> None:
        from app.services.pipeline import run_pipeline

        run_pipeline(
            modules=payload.modules,
            source_codes=payload.source_codes,
            trigger=f"api:{principal.username}",
            skip_graph=payload.skip_graph,
            skip_index=payload.skip_index,
            skip_alerts=payload.skip_alerts,
        )

    background.add_task(_run)
    return {"status": "accepted", "message": "Pipeline run started in the background"}


@pipeline_router.get("/scheduler", summary="Automatic monitoring schedule status")
def scheduler_status() -> dict:
    """Report the automatic monitoring cadence and its last sweep.

    The platform runs the pipeline on its own; this is how the Operations page
    shows users that monitoring is live rather than waiting to be triggered.
    """
    from app.services import scheduler

    return scheduler.status()
