"""Version comparison service.

Thin, reusable layer over :class:`~app.db.models.DetectedChange` so any module
can show "what changed since the last snapshot" — added / removed / updated
records between two versions of a source document.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DetectedChange, SourceDocument


def changes_for_document(session: Session, document_id: str, *, limit: int = 500) -> list[DetectedChange]:
    return list(
        session.scalars(
            select(DetectedChange)
            .where(DetectedChange.document_id == document_id)
            .order_by(DetectedChange.change_type, DetectedChange.source_key)
            .limit(limit)
        )
    )


def diff_between_documents(session: Session, before_id: str, after_id: str) -> dict[str, Any]:
    """Structured diff between two versioned documents of the same source."""
    before = session.get(SourceDocument, before_id)
    after = session.get(SourceDocument, after_id)
    if before is None or after is None:
        return {"error": "document not found"}

    changes = list(
        session.scalars(
            select(DetectedChange).where(
                DetectedChange.document_id == after_id,
                DetectedChange.change_type != "baseline",
            )
        )
    )
    added = [c for c in changes if c.change_type == "added"]
    removed = [c for c in changes if c.change_type == "removed"]
    updated = [c for c in changes if c.change_type == "updated"]

    return {
        "source_code": after.source_code,
        "module": after.module,
        "before": {
            "version": before.version,
            "filename": before.filename,
            "publication_date": before.publication_date.isoformat() if before.publication_date else None,
            "record_count": before.record_count,
            "fetched_at": before.fetched_at.isoformat() if before.fetched_at else None,
        },
        "after": {
            "version": after.version,
            "filename": after.filename,
            "publication_date": after.publication_date.isoformat() if after.publication_date else None,
            "record_count": after.record_count,
            "fetched_at": after.fetched_at.isoformat() if after.fetched_at else None,
        },
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "updated": len(updated),
            "net": len(added) - len(removed),
        },
        "added": [_change_brief(c) for c in added[:200]],
        "removed": [_change_brief(c) for c in removed[:200]],
        "updated": [_change_brief(c) for c in updated[:200]],
    }


def module_change_counts(session: Session, *, days: int = 30) -> dict[str, dict[str, int]]:
    from datetime import timedelta

    from app.db.base import utcnow

    since = utcnow() - timedelta(days=days)
    rows = session.execute(
        select(DetectedChange.module, DetectedChange.change_type, func.count(DetectedChange.id))
        .where(DetectedChange.detected_at >= since, DetectedChange.is_baseline.is_(False))
        .group_by(DetectedChange.module, DetectedChange.change_type)
    ).all()
    out: dict[str, dict[str, int]] = {}
    for module, change_type, count in rows:
        out.setdefault(module, {})[change_type] = count
    return out


def _change_brief(change: DetectedChange) -> dict[str, Any]:
    return {
        "id": change.id,
        "source_key": change.source_key,
        "entity_type": change.entity_type,
        "change_type": change.change_type,
        "detected_at": change.detected_at.isoformat() if change.detected_at else None,
        "fields": [fc.get("field") for fc in (change.field_changes or [])][:8],
    }
