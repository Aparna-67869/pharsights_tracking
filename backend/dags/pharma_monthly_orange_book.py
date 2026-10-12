"""Monthly SOP: Orange Book edition handling and knowledge-graph refresh.

The Orange Book ships a monthly cumulative supplement plus full data files, so
these sources are polled monthly rather than daily. This DAG also performs the
heavier rebuilds (knowledge graph, vector index) that are wasteful to run every
day once the incremental daily sweep has already loaded the deltas.
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from common import DAG_DEFAULT_ARGS

DAG_ID = "pharma_monthly_orange_book"


def run_orange_book_pipeline(**context) -> dict:
    from app.services.pipeline import run_pipeline

    result = run_pipeline(
        modules=["orange_book"],
        trigger=f"airflow:{DAG_ID}",
        skip_graph=True,
        skip_index=True,
        skip_alerts=True,
    )
    summary = result.to_dict()
    context["ti"].xcom_push(key="ob_summary", value=summary)
    return summary


def rebuild_knowledge_graph() -> dict:
    """Rebuild the drug/patent/NDA/ANDA/sponsor graph from current fact rows."""
    from app.graph.builder import rebuild_graph
    from app.graph.resolve import link_records
    from app.db.session import session_scope

    with session_scope() as session:
        link_records(session)
        stats = rebuild_graph(session)
    return stats if isinstance(stats, dict) else {"status": "rebuilt"}


def rebuild_search_index() -> dict:
    """Rebuild the full-text corpus and the RAG vector store."""
    from app.search.index import index_all
    from app.db.session import session_scope

    with session_scope() as session:
        result = index_all(session)
    return result if isinstance(result, dict) else {"status": "indexed"}


def analyse_orange_book_deltas(**context) -> int:
    from app.alerts.engine import dispatch_alerts
    from app.db.session import session_scope
    from app.intelligence.engine import analyze_pending_changes

    with session_scope() as session:
        insights = analyze_pending_changes(session)
        alerts = dispatch_alerts(session, insights=insights)
        return len(alerts)


with DAG(
    dag_id=DAG_ID,
    description="Monthly Orange Book supplement ingest plus knowledge-graph and RAG index rebuild",
    schedule="0 4 3 * *",  # 3rd of the month, 04:00 UTC
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DAG_DEFAULT_ARGS,
    tags=["pharma", "sop", "monthly", "orange-book"],
    doc_md=__doc__,
) as dag:
    orange_book = PythonOperator(task_id="run_orange_book_pipeline", python_callable=run_orange_book_pipeline)
    graph = PythonOperator(task_id="rebuild_knowledge_graph", python_callable=rebuild_knowledge_graph)
    index = PythonOperator(task_id="rebuild_search_index", python_callable=rebuild_search_index)
    alerts = PythonOperator(task_id="analyse_orange_book_deltas", python_callable=analyse_orange_book_deltas)

    orange_book >> graph >> index >> alerts
