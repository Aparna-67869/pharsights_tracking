"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

log = get_logger(__name__)

_connect_args: dict = {}
_engine_kwargs: dict = {"echo": settings.db_echo, "pool_pre_ping": True, "future": True}

if settings.is_sqlite:
    _connect_args = {"check_same_thread": False}
    _engine_kwargs.pop("pool_pre_ping")
    # SQLite has no server-side pool; a pooled connection is cheap. Keep the
    # pool large so concurrent requests (each may briefly hold two sessions —
    # the request session plus a best-effort telemetry write) do not queue on
    # connection checkout.
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=30,
    )
else:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=1800,
    )

engine = create_engine(settings.database_url, connect_args=_connect_args, **_engine_kwargs)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # SQLite allows a single writer. Without a busy timeout a second writer
        # fails instantly with "database is locked" (e.g. any login while the
        # pipeline holds the lock), so make competing writers wait instead.
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts, workers and DAG tasks."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def resilient_write(operation: Callable[[Session], None], *, attempts: int = 5) -> bool:
    """Run ``operation`` in its own transaction, retrying on SQLite lock errors.

    Used for best-effort writes (audit rows) that must never propagate a failure
    into the caller. Each attempt gets a fresh session so a poisoned transaction
    from one attempt cannot leak into the next. Returns True if it committed.
    """
    last_error: Exception | None = None
    for _ in range(attempts):
        session = SessionLocal()
        try:
            operation(session)
            session.commit()
            return True
        except Exception as exc:  # noqa: BLE001 - retried below
            last_error = exc
            session.rollback()
        finally:
            session.close()
        time.sleep(0.05)
    log.warning("resilient write failed after %d attempts: %s", attempts, last_error)
    return False


def create_all() -> None:
    # Import models so metadata is populated before create_all.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


# Additive columns introduced after the initial release. ``create_all`` never
# alters an existing table, so a fresh SQLite/Postgres deployment that already
# holds data would otherwise miss them.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "source_definitions": {
        "last_checked_at": "TIMESTAMP",
        "last_success_at": "TIMESTAMP",
        "last_error": "TEXT",
    },
    # Provenance: exact source cells + non-lossy identifier forms.
    "ftf_records": {"raw": "JSON", "source_ordinal": "INTEGER"},
    "pte_applications": {"raw": "JSON", "application_number_normalized": "VARCHAR(64)"},
    "pte_certificates": {"raw": "JSON"},
    "active_moieties": {"raw": "JSON"},
    "orange_book_products": {"raw": "JSON", "appl_no_normalized": "VARCHAR(16)"},
}


def reconcile_schema() -> None:
    """Idempotently add known additive columns to existing tables."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def drop_all() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)
