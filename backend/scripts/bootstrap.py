"""Create the schema, enable pgvector when available, and seed reference data.

Run with:  python -m scripts.bootstrap

Safe to run repeatedly: ``create_all`` is a no-op for existing tables, the
additive-column reconcile is idempotent, and seeding upserts by natural key.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import create_all, engine, reconcile_schema

log = get_logger(__name__)


def _enable_pgvector() -> None:
    """Create the pgvector extension so the mirrored embedding column can be used."""
    if settings.is_sqlite or settings.vector_backend == "numpy":
        return
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        log.info("pgvector extension ready")
    except Exception as exc:  # pragma: no cover - depends on the server image
        log.warning("could not enable pgvector (%s); falling back to numpy search", exc)


def main() -> None:
    _enable_pgvector()
    create_all()
    reconcile_schema()
    log.info("schema ready")

    # Imported late so the seed module can rely on the schema already existing.
    from scripts.seed import main as seed_main

    seed_main()
    log.info("bootstrap complete")


if __name__ == "__main__":
    main()
