"""Repositories: versioned upsert, change detection, and query helpers.

The core primitive is :func:`sync_versioned_records`. It reconciles a freshly
parsed batch of records against the currently active rows for one source and
returns the added / updated / removed deltas. Rows are never deleted — a changed
row is superseded (``is_active=False``) and a new row with the new
``content_hash`` is inserted, which gives full historical versioning for free.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.base import stable_hash, utcnow

log = get_logger(__name__)

ModelT = TypeVar("ModelT")


@dataclass
class RecordDelta:
    """The outcome of reconciling one source's records."""

    added: list[dict[str, Any]] = field(default_factory=list)
    updated: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]] = field(
        default_factory=list
    )  # (before, after, field_changes)
    removed: list[dict[str, Any]] = field(default_factory=list)
    unchanged_count: int = 0
    total: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.updated or self.removed)

    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "updated": len(self.updated),
            "removed": len(self.removed),
            "unchanged": self.unchanged_count,
            "total": self.total,
        }


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Field-level diff between two payloads, ignoring no-op changes."""
    changes: list[dict[str, Any]] = []
    keys = sorted(set(before) | set(after))
    for key in keys:
        old = before.get(key)
        new = after.get(key)
        old_norm = old.isoformat() if hasattr(old, "isoformat") else old
        new_norm = new.isoformat() if hasattr(new, "isoformat") else new
        if old_norm != new_norm:
            changes.append({"field": key, "before": old_norm, "after": new_norm})
    return changes


def sync_versioned_records(
    session: Session,
    model: type[ModelT],
    *,
    source_code: str,
    records: list[dict[str, Any]],
    key_fn: Callable[[dict[str, Any]], str],
    payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    build_kwargs: Callable[[dict[str, Any], str, str], dict[str, Any]],
    existing_filter: Callable[[Any], Any] | None = None,
) -> RecordDelta:
    """Reconcile parsed records against active rows for ``source_code``.

    Args:
        model: SQLAlchemy model class holding the fact rows.
        source_code: the ``source_code`` column value scoping this dataset.
        records: parsed records (already normalized).
        key_fn: natural key extractor — must be stable across versions.
        payload_fn: comparable content extractor.
        build_kwargs: maps ``(record, source_key, content_hash)`` to model kwargs.
        existing_filter: optional extra filter applied when loading active rows.
    """
    delta = RecordDelta(total=len(records))

    query = select(model).where(model.source_code == source_code, model.is_active.is_(True))
    if existing_filter is not None:
        query = query.where(existing_filter(model))
    existing_rows = list(session.scalars(query))
    existing_by_key = {row.source_key: row for row in existing_rows}

    seen_keys: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    now = utcnow()

    for record in records:
        key = key_fn(record)
        if not key:
            continue
        payload = payload_fn(record)
        digest = stable_hash(payload)

        # Source files legitimately repeat rows (e.g. one exclusivity code applied
        # to several package sizes). Collapse exact duplicates within a batch so
        # the (source_key, content_hash) uniqueness contract holds.
        if (key, digest) in seen_pairs:
            delta.unchanged_count += 1
            continue
        seen_pairs.add((key, digest))
        if key in seen_keys:
            # Same natural key, differing content, within one batch: keep the first
            # occurrence and let the next pipeline run reconcile any real change.
            log.warning("duplicate natural key %r in %s batch; keeping first occurrence", key, source_code)
            delta.unchanged_count += 1
            continue
        seen_keys.add(key)
        row = existing_by_key.get(key)

        if row is None:
            session.add(model(**build_kwargs(record, key, digest)))
            delta.added.append(record)
            continue

        if row.content_hash == digest:
            row.last_seen_at = now
            delta.unchanged_count += 1
            continue

        before = _row_payload(row, payload)
        changes = diff_fields(before, payload)
        if not changes:
            # Hash differed only due to non-comparable fields; treat as unchanged.
            row.last_seen_at = now
            delta.unchanged_count += 1
            continue

        row.is_active = False
        row.updated_at = now
        session.add(model(**build_kwargs(record, key, digest)))
        delta.updated.append((before, payload, changes))

    # Rows present before but absent now are removals (e.g. a de-listed product).
    for key, row in existing_by_key.items():
        if key in seen_keys:
            continue
        row.is_active = False
        row.updated_at = now
        delta.removed.append(_row_payload(row, payload_fn({})))

    session.flush()
    return delta


def _row_payload(row: Any, template: dict[str, Any]) -> dict[str, Any]:
    """Project a model row onto the payload shape using the payload's own keys."""
    result: dict[str, Any] = {}
    for key in template:
        value = getattr(row, key, None)
        result[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return result


# ---- Query helpers ---------------------------------------------------------


def paginate(
    session: Session,
    stmt: Any,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Any], int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 500))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return rows, total


def count_active(session: Session, model: type[ModelT], **filters: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.is_active.is_(True))
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    return session.scalar(stmt) or 0


def active_rows(session: Session, model: type[ModelT], **filters: Any) -> list[Any]:
    stmt = select(model).where(model.is_active.is_(True))
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    return list(session.scalars(stmt))


def records_between(
    session: Session,
    model: type[ModelT],
    column: str,
    start: datetime | None,
    end: datetime | None,
) -> list[Any]:
    stmt = select(model)
    target = getattr(model, column)
    if start is not None:
        stmt = stmt.where(target >= start)
    if end is not None:
        stmt = stmt.where(target <= end)
    return list(session.scalars(stmt))
