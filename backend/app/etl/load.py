"""Load parsed records into the warehouse and record every delta.

This is the change-detection engine. For each source it:
  1. validates and normalizes the batch,
  2. reconciles against active rows (versioned upsert),
  3. writes a ``DetectedChange`` row per added / updated / removed record,
  4. emits a domain event per change for the streaming layer.

The result is a complete, queryable audit trail of every regulatory movement.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.base import CollectedDocument
from app.core.events import Topics, publish_event
from app.core.logging import get_logger
from app.core.text import normalize_name
from app.db.base import utcnow
from app.db.models import (
    ActiveMoiety,
    DetectedChange,
    FtfRecord,
    OrangeBookExclusivity,
    OrangeBookPatent,
    OrangeBookProduct,
    OrangeBookSupplement,
    PteApplication,
    PteCertificate,
)
from app.db.repositories import RecordDelta, sync_versioned_records
from app.etl import validate as V
from app.parsers import ftf as ftf_parser
from app.parsers import orange_book as ob_parser
from app.parsers import pde as pde_parser
from app.parsers import pte as pte_parser

log = get_logger(__name__)

MODULE_TOPIC_ADDED = {
    "ftf": Topics.FTF_ADDED,
    "pte_application": Topics.PTE_APP_ADDED,
    "pte_certificate": Topics.PTE_CERT_ADDED,
    "active_moiety": Topics.PDE_ADDED,
    "orange_book_product": Topics.OB_CHANGED,
    "orange_book_patent": Topics.PATENT_CHANGED,
    "orange_book_exclusivity": Topics.OB_CHANGED,
}

MODULE_TOPIC_UPDATED = {
    "ftf": Topics.FTF_UPDATED,
    "pte_application": Topics.PTE_UPDATED,
    "pte_certificate": Topics.PTE_UPDATED,
    "active_moiety": Topics.PDE_UPDATED,
    "orange_book_product": Topics.OB_CHANGED,
    "orange_book_patent": Topics.PATENT_CHANGED,
    "orange_book_exclusivity": Topics.OB_CHANGED,
}

MODULE_TOPIC_REMOVED = {
    "ftf": Topics.FTF_REMOVED,
    "pte_application": Topics.PTE_UPDATED,
    "pte_certificate": Topics.PTE_UPDATED,
    "active_moiety": Topics.PDE_UPDATED,
    "orange_book_product": Topics.OB_CHANGED,
    "orange_book_patent": Topics.PATENT_CHANGED,
    "orange_book_exclusivity": Topics.OB_CHANGED,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _jsonable_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in payload.items()}


def record_changes(
    session: Session,
    *,
    module: str,
    source_code: str,
    entity_type: str,
    delta: RecordDelta,
    document: CollectedDocument | None,
    pipeline_run_id: str | None,
    is_baseline: bool = False,
) -> list[DetectedChange]:
    """Persist one ``DetectedChange`` per delta entry.

    ``is_baseline`` marks the first-ever snapshot of a source: the rows are
    recorded for history and diffing, but the alert engine ignores them.
    """
    changes: list[DetectedChange] = []
    doc_id = document.document.id if document else None
    prev_doc_id = None
    if document is not None:
        prev = session.scalars(
            select(DetectedChange.previous_document_id)
            .where(DetectedChange.source_code == source_code)
            .order_by(DetectedChange.detected_at.desc())
            .limit(1)
        ).first()
        prev_doc_id = prev

    def _add(change_type: str, source_key: str, before: Any, after: Any, field_changes: list) -> None:
        change = DetectedChange(
            module=module,
            source_code=source_code,
            entity_type=entity_type,
            change_type=change_type,
            source_key=source_key[:512],
            document_id=doc_id,
            previous_document_id=prev_doc_id,
            pipeline_run_id=pipeline_run_id,
            detected_at=utcnow(),
            field_changes=field_changes or [],
            before=_jsonable_dict(before) if before else None,
            after=_jsonable_dict(after) if after else None,
            is_baseline=is_baseline,
        )
        session.add(change)
        changes.append(change)

    for record in delta.added:
        key = _key_for(entity_type, record)
        _add("added", key, None, _payload_for(entity_type, record), [])
    for before, after, field_changes in delta.updated:
        key = _key_for(entity_type, after)
        _add("updated", key, before, after, field_changes)
    for record in delta.removed:
        key = _key_for(entity_type, record)
        _add("removed", key, record, None, [])

    session.flush()

    # Publish to the streaming layer.
    for change in changes:
        topic = {
            "added": MODULE_TOPIC_ADDED,
            "updated": MODULE_TOPIC_UPDATED,
            "removed": MODULE_TOPIC_REMOVED,
        }[change.change_type].get(entity_type, Topics.OB_CHANGED)
        publish_event(
            topic,
            change.change_type,
            {
                "change_id": change.id,
                "module": module,
                "entity_type": entity_type,
                "source_key": change.source_key,
                "field_changes": change.field_changes,
                "before": change.before,
                "after": change.after,
            },
        )
    return changes


def _key_for(entity_type: str, record: dict[str, Any]) -> str:
    if entity_type == "ftf_record":
        return ftf_parser.source_key(record)
    if entity_type == "pte_application":
        return pte_parser.source_key_application(record)
    if entity_type == "pte_certificate":
        return pte_parser.source_key_certificate(record)
    if entity_type == "active_moiety":
        return pde_parser.source_key(record)
    if entity_type == "orange_book_product":
        return ob_parser.product_source_key(record)
    if entity_type == "orange_book_patent":
        return ob_parser.patent_source_key(record)
    if entity_type == "orange_book_exclusivity":
        return ob_parser.exclusivity_source_key(record)
    return str(record)


def _payload_for(entity_type: str, record: dict[str, Any]) -> dict[str, Any]:
    if entity_type == "ftf_record":
        return ftf_parser.content_payload(record)
    if entity_type == "pte_application":
        return pte_parser.application_payload(record)
    if entity_type == "pte_certificate":
        return pte_parser.certificate_payload(record)
    if entity_type == "active_moiety":
        return pde_parser.content_payload(record)
    if entity_type == "orange_book_product":
        return ob_parser.product_payload(record)
    if entity_type == "orange_book_patent":
        return ob_parser.patent_payload(record)
    if entity_type == "orange_book_exclusivity":
        return ob_parser.exclusivity_payload(record)
    return record


# ---- Per-module loaders ----------------------------------------------------


def load_ftf(session: Session, source_code: str, records: list[dict[str, Any]], document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.FTF_VALIDATORS)
    valid, fidelity = V.validate_batch(valid, V.FTF_FIDELITY_VALIDATORS)
    log.info("FTF validation: %s fidelity: %s", report.to_dict(), fidelity.to_dict())
    delta = sync_versioned_records(
        session,
        FtfRecord,
        source_code=source_code,
        records=valid,
        key_fn=ftf_parser.source_key,
        payload_fn=ftf_parser.content_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            "source_ordinal": rec.get("source_ordinal"),
            **ftf_parser.content_payload(rec),
            "rld_nda": rec.get("rld_nda"),
            "certification_type": rec.get("certification_type") or "Paragraph IV",
            "status": "active",
        },
    )
    record_changes(
        session,
        module="ftf",
        source_code=source_code,
        entity_type="ftf_record",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_pte_applications(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.PTE_APPLICATION_VALIDATORS)
    valid, fidelity = V.validate_batch(valid, V.PTE_APPLICATION_FIDELITY)
    log.info("PTE application validation: %s fidelity: %s", report.to_dict(), fidelity.to_dict())
    delta = sync_versioned_records(
        session,
        PteApplication,
        source_code=source_code,
        records=valid,
        key_fn=pte_parser.source_key_application,
        payload_fn=pte_parser.application_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            **pte_parser.application_payload(rec),
            "patent_number": rec.get("patent_number"),
            "application_number_normalized": rec.get("application_number_normalized"),
            "patent_center_link": rec.get("patent_center_link"),
            "sponsor_name": rec.get("sponsor_name"),
            "status": rec.get("status") or "filed",
        },
    )
    record_changes(
        session,
        module="pte",
        source_code=source_code,
        entity_type="pte_application",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_pte_certificates(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.PTE_CERTIFICATE_VALIDATORS)
    valid, fidelity = V.validate_batch(valid, V.PTE_CERTIFICATE_FIDELITY)
    log.info("PTE certificate validation: %s fidelity: %s", report.to_dict(), fidelity.to_dict())
    delta = sync_versioned_records(
        session,
        PteCertificate,
        source_code=source_code,
        records=valid,
        key_fn=pte_parser.source_key_certificate,
        payload_fn=pte_parser.certificate_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            **pte_parser.certificate_payload(rec),
            "patent_number": rec.get("patent_number"),
            "sponsor_name": rec.get("sponsor_name"),
            "status": rec.get("status") or "granted",
        },
    )
    record_changes(
        session,
        module="pte",
        source_code=source_code,
        entity_type="pte_certificate",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_active_moieties(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.PDE_VALIDATORS)
    log.info("PDE validation: %s", report.to_dict())
    delta = sync_versioned_records(
        session,
        ActiveMoiety,
        source_code=source_code,
        records=valid,
        key_fn=pde_parser.source_key,
        payload_fn=pde_parser.content_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            **pde_parser.content_payload(rec),
            "normalized_name": normalize_name(rec.get("moiety_name")),
            "approval_year": rec.get("approval_year"),
            "status": rec.get("status") or "approved",
        },
    )
    record_changes(
        session,
        module="pde",
        source_code=source_code,
        entity_type="active_moiety",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_orange_book_products(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.ORANGE_BOOK_PRODUCT_VALIDATORS)
    valid, fidelity = V.validate_batch(valid, V.ORANGE_BOOK_FIDELITY)
    log.info("Orange Book product validation: %s fidelity: %s", report.to_dict(), fidelity.to_dict())
    delta = sync_versioned_records(
        session,
        OrangeBookProduct,
        source_code=source_code,
        records=valid,
        key_fn=ob_parser.product_source_key,
        payload_fn=ob_parser.product_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            "appl_type": rec.get("appl_type"),
            "appl_no": rec.get("appl_no"),
            "appl_no_normalized": rec.get("appl_no_normalized"),
            "product_no": rec.get("product_no"),
            **ob_parser.product_payload(rec),
        },
    )
    record_changes(
        session,
        module="orange_book",
        source_code=source_code,
        entity_type="orange_book_product",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_orange_book_patents(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.ORANGE_BOOK_PATENT_VALIDATORS)
    log.info("Orange Book patent validation: %s", report.to_dict())
    delta = sync_versioned_records(
        session,
        OrangeBookPatent,
        source_code=source_code,
        records=valid,
        key_fn=ob_parser.patent_source_key,
        payload_fn=ob_parser.patent_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            "appl_type": rec.get("appl_type"),
            "appl_no": rec.get("appl_no"),
            "product_no": rec.get("product_no"),
            "patent_number": rec.get("patent_number"),
            **ob_parser.patent_payload(rec),
        },
    )
    record_changes(
        session,
        module="orange_book",
        source_code=source_code,
        entity_type="orange_book_patent",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def load_orange_book_exclusivity(session: Session, source_code: str, records, document, run_id, is_baseline: bool = False) -> RecordDelta:
    valid, report = V.validate_batch(records, V.ORANGE_BOOK_EXCLUSIVITY_VALIDATORS)
    log.info("Orange Book exclusivity validation: %s", report.to_dict())
    delta = sync_versioned_records(
        session,
        OrangeBookExclusivity,
        source_code=source_code,
        records=valid,
        key_fn=ob_parser.exclusivity_source_key,
        payload_fn=ob_parser.exclusivity_payload,
        build_kwargs=lambda rec, key, digest: {
            "source_code": source_code,
            "source_key": key,
            "content_hash": digest,
            "appl_type": rec.get("appl_type"),
            "appl_no": rec.get("appl_no"),
            "product_no": rec.get("product_no"),
            "exclusivity_code": rec.get("exclusivity_code"),
            **ob_parser.exclusivity_payload(rec),
        },
    )
    record_changes(
        session,
        module="orange_book",
        source_code=source_code,
        entity_type="orange_book_exclusivity",
        delta=delta,
        document=document,
        pipeline_run_id=run_id,
        is_baseline=is_baseline,
    )
    return delta


def upsert_supplement(session: Session, metadata: dict[str, Any], document, run_id) -> OrangeBookSupplement:
    """Create or update the supplement edition record from the PDF cover."""
    number = str(metadata.get("supplement_number") or "unknown")
    year = metadata.get("publication_year")
    existing = session.scalars(
        select(OrangeBookSupplement).where(
            OrangeBookSupplement.supplement_number == number,
            OrangeBookSupplement.publication_year == year,
        )
    ).first()
    if existing is None:
        existing = OrangeBookSupplement(
            supplement_number=number,
            edition=str(metadata.get("edition") or ""),
            publication_month=metadata.get("publication_month"),
            publication_year=year,
            publication_date=metadata.get("publication_date"),
            document_id=document.document.id if document else None,
            is_current=True,
            details={"source": "cumulative_supplement_pdf"},
        )
        session.add(existing)
        session.flush()
        publish_event(
            Topics.OB_SUPPLEMENT,
            "published",
            {
                "supplement_number": number,
                "publication_year": year,
                "publication_month": metadata.get("publication_month"),
            },
        )
    else:
        existing.document_id = document.document.id if document else existing.document_id
        existing.publication_month = metadata.get("publication_month") or existing.publication_month
        existing.edition = str(metadata.get("edition") or existing.edition)
        session.flush()
    return existing
