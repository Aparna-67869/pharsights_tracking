"""Daily SOP: collect, diff, analyse and alert across every monitored source.

Schedule rationale
------------------
FDA Paragraph IV certifications, the PDE list and the USPTO PTE pages are
published on an ad-hoc cadence, so a daily poll keeps detection latency under a
day while respecting the sources' politeness expectations. The collectors are
conditional-request aware (ETag / Last-Modified) and hash-compare, so an
unchanged source costs one HEAD-equivalent request and produces no delta.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from common import DAG_DEFAULT_ARGS, MODULES, apply_alert_threshold

DAG_ID = "pharma_daily_regulatory_sweep"


def collect_and_detect(**context) -> dict:
    """Run the full pipeline for every module and return the run summary."""
    from app.services.pipeline import run_pipeline

    result = run_pipeline(
        modules=MODULES,
        trigger=f"airflow:{DAG_ID}",
        skip_alerts=True,  # alerting is a separate, retryable task
    )
    summary = result.to_dict()
    context["ti"].xcom_push(key="run_summary", value=summary)
    return summary


def dispatch_priority_alerts(**context) -> int:
    """Send only the alerts that clear the priority threshold.

    Kept separate from collection so a transient SMTP/Teams/Slack outage retries
    the notification without re-collecting every source.
    """
    from app.alerts.engine import dispatch_alerts
    from app.db.session import session_scope
    from app.intelligence.engine import analyze_pending_changes

    threshold = apply_alert_threshold()
    print(f"dispatching alerts at priority >= {threshold}")
    with session_scope() as session:
        insights = analyze_pending_changes(session)
        alerts = dispatch_alerts(session, insights=insights)
        count = len(alerts)
    context["ti"].xcom_push(key="alerts_sent", value=count)
    return count


def verify_data_freshness(**context) -> None:
    """Fail the run loudly if any enabled source has gone stale.

    A silent collector is the worst failure mode for this platform: the
    dashboard keeps rendering yesterday's truth and nobody notices.
    """
    from sqlalchemy import select

    from app.db.models import SourceDefinition
    from app.db.session import session_scope

    max_age = timedelta(hours=36)
    cutoff = datetime.utcnow() - max_age
    stale: list[str] = []
    with session_scope() as session:
        for definition in session.scalars(
            select(SourceDefinition).where(SourceDefinition.enabled.is_(True))
        ):
            if definition.last_checked_at is None or definition.last_checked_at < cutoff:
                stale.append(definition.code)
    if stale:
        raise ValueError(f"stale sources (no successful check in {max_age}): {', '.join(stale)}")


with DAG(
    dag_id=DAG_ID,
    description="Daily collection, change detection, impact analysis and alerting for all FDA/USPTO sources",
    schedule="0 5 * * *",  # 05:00 UTC, ahead of US business hours
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DAG_DEFAULT_ARGS,
    tags=["pharma", "sop", "daily", "regulatory"],
    doc_md=__doc__,
) as dag:
    collect = PythonOperator(task_id="collect_and_detect", python_callable=collect_and_detect)
    alerts = PythonOperator(task_id="dispatch_priority_alerts", python_callable=dispatch_priority_alerts)
    freshness = PythonOperator(task_id="verify_data_freshness", python_callable=verify_data_freshness)

    collect >> alerts >> freshness
