"""Shared Airflow plumbing for the pharma intelligence DAGs.

Every DAG funnels into ``run_pipeline`` — the same entrypoint the API background
task and the CLI use — so a schedule change never changes pipeline semantics.
"""

from __future__ import annotations

import os
from datetime import timedelta

from airflow.models import Variable

DAG_DEFAULT_ARGS = {
    "owner": "pharma-intel",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "email_on_failure": False,
    "execution_timeout": timedelta(hours=2),
}

# Celery/Kubernetes worker image that has the backend package installed.
PIPELINE_TASK_IMAGE = os.getenv("PIPELINE_TASK_IMAGE", "pharma-intel-backend:latest")

MODULES = ["ftf", "pte", "pde", "orange_book"]


def apply_alert_threshold() -> int:
    """Apply the operator-tunable alert threshold from Airflow Variables.

    The engine reads ``settings.alert_min_priority_to_notify``; this lets an
    operator raise or lower the bar from the Airflow UI without a redeploy.
    """
    from app.core.config import settings

    threshold = int(Variable.get("alert_min_priority_to_notify", default_var=40))
    settings.alert_min_priority_to_notify = threshold
    return threshold
