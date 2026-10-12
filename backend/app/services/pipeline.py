"""Full pipeline orchestration: collect -> parse -> load -> detect -> analyze -> alert.

This is the single entrypoint used by Airflow DAGs, the API, and the CLI. It is
idempotent: running it twice against unchanged sources produces zero new changes.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collectors.base import ensure_source_definition
from app.collectors.modules import build_collector
from app.collectors.registry import ALL_SOURCES
from app.core.events import Topics, publish_event
from app.core.logging import get_logger
from app.db.base import utcnow
from app.db.models import DetectedChange, PipelineRun, SourceDocument
from app.db.session import session_scope
from app.etl import load as loader
from app.graph.builder import rebuild_graph
from app.graph.resolve import link_records
from app.intelligence.engine import analyze_pending_changes
from app.search.index import index_all

log = get_logger(__name__)


@dataclass
class PipelineResult:
    run_id: str
    status: str = "running"
    sources_checked: int = 0
    sources_changed: int = 0
    changes_detected: int = 0
    insights_generated: int = 0
    alerts_created: int = 0
    errors: list[str] = field(default_factory=list)
    source_results: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "sources_checked": self.sources_checked,
            "sources_changed": self.sources_changed,
            "changes_detected": self.changes_detected,
            "insights_generated": self.insights_generated,
            "alerts_created": self.alerts_created,
            "errors": self.errors,
            "source_results": self.source_results,
            "duration_ms": self.duration_ms,
        }


# Maps a source code to the loader that persists its records.
# Note: the FTF PDF is collected and versioned for cross-validation against the
# Excel workbook, but only the Excel (authoritative, machine-readable) edition
# is loaded as fact rows — otherwise the same filing would be stored twice.
LOADERS: dict[str, Callable[..., Any]] = {
    "fda_ftf_ppiv_excel": loader.load_ftf,
    "uspto_pte_applications": loader.load_pte_applications,
    "uspto_pte_certificates": loader.load_pte_certificates,
    "fda_pde_approved_active_moiety": loader.load_active_moieties,
}


def _handle_orange_book(session: Session, source_code: str, parsed, collected, run_id: str, is_baseline: bool):
    """Orange Book sources produce three datasets plus edition metadata."""
    results = {}
    if source_code == "fda_ob_data_files":
        results["products"] = loader.load_orange_book_products(
            session, source_code, parsed.records, collected, run_id, is_baseline=is_baseline
        )
        results["patents"] = loader.load_orange_book_patents(
            session, source_code, parsed.metadata.get("patents", []), collected, run_id,
            is_baseline=is_baseline,
        )
        results["exclusivity"] = loader.load_orange_book_exclusivity(
            session, source_code, parsed.metadata.get("exclusivity", []), collected, run_id,
            is_baseline=is_baseline,
        )
    elif source_code == "fda_ob_cumulative_supplement":
        loader.upsert_supplement(session, parsed.metadata, collected, run_id)
    return results


def run_source(
    session: Session,
    source_code: str,
    *,
    pipeline_run_id: str,
) -> dict[str, Any]:
    """Collect, parse and load one source, isolated in a savepoint.

    A failure in one source must never roll back work already committed for the
    other sources, so each source runs inside its own nested transaction.
    """
    from app.collectors.registry import SOURCES_BY_CODE

    source = SOURCES_BY_CODE[source_code]
    collector = build_collector(source)
    result: dict[str, Any] = {"source_code": source_code, "module": source.module}
    try:
        with session.begin_nested():
            # The first time a source is ever seen, its rows are a baseline
            # snapshot, not regulatory events. Mark them so no alerts fire.
            is_baseline = (
                session.scalar(
                    select(func.count())
                    .select_from(SourceDocument)
                    .where(SourceDocument.source_code == source_code)
                )
                or 0
            ) == 0

            collected = collector.collect(session)
            if collected is None:
                result.update({"status": "no_document"})
                return result
            result["document_id"] = collected.document.id
            result["version"] = collected.document.version
            result["is_baseline"] = is_baseline
            result["publication_date"] = (
                collected.publication_date.isoformat() if collected.publication_date else None
            )

            if not collected.is_new_version:
                result.update({"status": "unchanged", "records": collected.document.record_count})
                return result

            parsed = collector.parse(collected.data, filename=collected.document.filename)
            collected.document.record_count = len(parsed.records)
            collected.document.parse_status = "ok"
            session.flush()

            counts: dict[str, Any] = {}
            if source_code in LOADERS:
                delta = LOADERS[source_code](
                    session,
                    source_code,
                    parsed.records,
                    collected,
                    pipeline_run_id,
                    is_baseline=is_baseline,
                )
                counts = delta.counts()
            elif source.module == "orange_book":
                for name, delta in _handle_orange_book(
                    session, source_code, parsed, collected, run_id=pipeline_run_id,
                    is_baseline=is_baseline,
                ).items():
                    counts[name] = delta.counts()
                if not counts:
                    counts = {"metadata_only": 0}

            result.update({"status": "processed", "records": len(parsed.records), "counts": counts})
        return result
    except Exception as exc:
        log.exception("pipeline source step failed: %s", source_code)
        result.update({"status": "failed", "error": str(exc)[:500]})
        return result
    finally:
        collector.close()


def run_pipeline(
    *,
    modules: list[str] | None = None,
    source_codes: list[str] | None = None,
    trigger: str = "manual",
    skip_graph: bool = False,
    skip_index: bool = False,
    skip_alerts: bool = False,
    progress: Callable[[str], None] | None = None,
) -> PipelineResult:
    """Execute the full pipeline. Returns a summary result."""
    started = time.time()
    run_id = ""

    with session_scope() as session:
        run = PipelineRun(trigger=trigger, status="running")
        session.add(run)
        session.flush()
        run_id = run.id

        # Ensure the source registry is present.
        for source in ALL_SOURCES:
            ensure_source_definition(session, source)
        session.flush()

        selected = list(ALL_SOURCES)
        if source_codes:
            wanted = set(source_codes)
            selected = [s for s in selected if s.code in wanted]
        elif modules:
            wanted = set(modules)
            selected = [s for s in selected if s.module in wanted]

        result = PipelineResult(run_id=run_id)
        result.sources_checked = len(selected)

        for source in selected:
            if progress:
                progress(f"collecting {source.code}")
            outcome = run_source(session, source.code, pipeline_run_id=run_id)
            result.source_results.append(outcome)
            if outcome.get("status") == "processed":
                result.sources_changed += 1
            if outcome.get("status") == "failed":
                result.errors.append(f"{source.code}: {outcome.get('error')}")

        # Count detected changes produced by this run (baseline excluded).
        result.changes_detected = session.scalar(
            select(func.count())
            .select_from(DetectedChange)
            .where(DetectedChange.pipeline_run_id == run_id)
        ) or 0

        if progress:
            progress("resolving entities")
        link_records(session)

        if not skip_graph:
            if progress:
                progress("rebuilding knowledge graph")
            rebuild_graph(session)

        if not skip_index:
            if progress:
                progress("indexing for search and RAG")
            index_all(session)

        if progress:
            progress("generating insights")
        insights = analyze_pending_changes(session)
        result.insights_generated = len(insights)

        if not skip_alerts:
            if progress:
                progress("dispatching alerts")
            from app.alerts.engine import dispatch_alerts

            alerts = dispatch_alerts(session, insights=insights)
            result.alerts_created = len(alerts)

        result.status = "completed" if not result.errors else "completed_with_errors"
        result.duration_ms = int((time.time() - started) * 1000)

        run.status = result.status
        run.finished_at = utcnow()
        run.duration_ms = result.duration_ms
        run.sources_checked = result.sources_checked
        run.sources_changed = result.sources_changed
        run.changes_detected = result.changes_detected
        run.insights_generated = result.insights_generated
        run.alerts_created = result.alerts_created
        run.summary = result.to_dict()
        if result.errors:
            run.error = "; ".join(result.errors)[:2000]
        session.flush()

    publish_event(Topics.PIPELINE_RUN, result.status, result.to_dict())
    log.info("pipeline %s finished: %s", run_id, result.to_dict())
    return result
