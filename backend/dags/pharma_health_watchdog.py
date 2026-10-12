"""Hourly watchdog: source health, alert backlog and pipeline liveness.

This DAG is deliberately cheap — it touches no external site. It exists to catch
the failure modes that a once-a-day sweep would surface twelve hours too late:

  * a collector that has started erroring (last_error set),
  * a source that has stopped being checked at all,
  * alerts that were created but never delivered,
  * the pipeline failing repeatedly.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from common import DAG_DEFAULT_ARGS

DAG_ID = "pharma_hourly_health_watchdog"

STALE_SOURCE_HOURS = 36
STALE_ALERT_HOURS = 6


def check_source_health(**context) -> dict:
    from sqlalchemy import select

    from app.db.models import SourceDefinition
    from app.db.session import session_scope

    now = datetime.utcnow()
    errored: list[dict] = []
    stale: list[str] = []
    with session_scope() as session:
        for definition in session.scalars(
            select(SourceDefinition).where(SourceDefinition.enabled.is_(True))
        ):
            if definition.last_error:
                errored.append({"code": definition.code, "error": definition.last_error[:200]})
            if (
                definition.last_success_at is None
                or definition.last_success_at < now - timedelta(hours=STALE_SOURCE_HOURS)
            ):
                stale.append(definition.code)

    report = {"errored": errored, "stale": stale}
    context["ti"].xcom_push(key="source_health", value=report)
    return report


def check_alert_backlog(**context) -> dict:
    """Open alerts older than the grace window with no successful delivery.

    Delivery is recorded per channel in ``notification_logs``, so a missing
    ``sent`` row (rather than the JSON ``channels_sent`` array) is the portable
    signal that works identically on SQLite and Postgres.
    """
    from sqlalchemy import select

    from app.db.models import Alert, NotificationLog
    from app.db.session import session_scope

    cutoff = datetime.utcnow() - timedelta(hours=STALE_ALERT_HOURS)
    delivered = (
        select(NotificationLog.id)
        .where(NotificationLog.alert_id == Alert.id, NotificationLog.status == "sent")
        .exists()
    )
    with session_scope() as session:
        undelivered = list(
            session.scalars(
                select(Alert)
                .where(Alert.created_at < cutoff, Alert.status == "open", ~delivered)
                .limit(100)
            )
        )
    backlog = {"count": len(undelivered), "ids": [a.id for a in undelivered[:20]]}
    context["ti"].xcom_push(key="alert_backlog", value=backlog)
    return backlog


def check_pipeline_liveness(**context) -> dict:
    from sqlalchemy import desc, select

    from app.db.models import PipelineRun
    from app.db.session import session_scope

    with session_scope() as session:
        recent = list(
            session.scalars(select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(5))
        )
    runs = [{"id": r.id, "status": r.status, "started_at": str(r.started_at)} for r in recent]
    failures = [r for r in recent if r.status in {"failed", "completed_with_errors"}]
    result = {"recent": runs, "recent_failures": len(failures)}
    context["ti"].xcom_push(key="pipeline_liveness", value=result)
    return result


def summarise_health(**context) -> str:
    """Emit one consolidated line so an operator can triage from the task log."""
    ti = context["ti"]
    health = ti.xcom_pull(task_ids="check_source_health", key="source_health") or {}
    backlog = ti.xcom_pull(task_ids="check_alert_backlog", key="alert_backlog") or {}
    liveness = ti.xcom_pull(task_ids="check_pipeline_liveness", key="pipeline_liveness") or {}

    summary = (
        f"sources errored={len(health.get('errored', []))} "
        f"stale={len(health.get('stale', []))} | "
        f"undelivered_alerts={backlog.get('count', 0)} | "
        f"recent_pipeline_failures={liveness.get('recent_failures', 0)}"
    )
    print(summary)
    return summary


with DAG(
    dag_id=DAG_ID,
    description="Hourly watchdog over source health, alert delivery backlog and pipeline liveness",
    schedule="15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DAG_DEFAULT_ARGS,
    tags=["pharma", "ops", "watchdog"],
    doc_md=__doc__,
) as dag:
    sources = PythonOperator(task_id="check_source_health", python_callable=check_source_health)
    alerts = PythonOperator(task_id="check_alert_backlog", python_callable=check_alert_backlog)
    liveness = PythonOperator(task_id="check_pipeline_liveness", python_callable=check_pipeline_liveness)
    summary = PythonOperator(task_id="summarise_health", python_callable=summarise_health)

    [sources, alerts, liveness] >> summary
