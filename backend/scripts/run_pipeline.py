"""Run the full SOP pipeline from the command line.

Run with:
    python -m scripts.run_pipeline                 # every module
    python -m scripts.run_pipeline --module ftf    # one module
    python -m scripts.run_pipeline --source fda_ftf_ppiv_excel
    python -m scripts.run_pipeline --no-alerts     # collect + diff only

This is the same entrypoint the Airflow DAGs and the API background task call,
so behaviour is identical regardless of trigger.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.logging import configure_logging, get_logger
from app.services.pipeline import run_pipeline

log = get_logger(__name__)

MODULES = ["ftf", "pte", "pde", "orange_book"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the regulatory intelligence pipeline")
    parser.add_argument(
        "--module",
        action="append",
        choices=MODULES,
        help="restrict to a module (repeatable); default is all modules",
    )
    parser.add_argument(
        "--source",
        action="append",
        help="restrict to a source code (repeatable); takes precedence over --module",
    )
    parser.add_argument("--skip-graph", action="store_true", help="do not rebuild the knowledge graph")
    parser.add_argument("--skip-index", action="store_true", help="do not rebuild search/RAG indexes")
    parser.add_argument("--no-alerts", action="store_true", help="do not dispatch alerts")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()

    result = run_pipeline(
        modules=args.module,
        source_codes=args.source,
        trigger="cli",
        skip_graph=args.skip_graph,
        skip_index=args.skip_index,
        skip_alerts=args.no_alerts,
        progress=lambda message: log.info("pipeline: %s", message),
    )

    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
