"""Search index: builds the full-text corpus and the RAG vector store.

``index_all`` is idempotent and cheap on re-runs: chunks are content-hashed, so
only genuinely new or changed documents are embedded and stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.copilot.embeddings import get_embedder
from app.core.logging import get_logger
from app.db.base import stable_hash
from app.db.models import (
    ActiveMoiety,
    DocumentChunk,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookPatent,
    OrangeBookProduct,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)

log = get_logger(__name__)

MAX_CHUNK_CHARS = 1800


@dataclass
class IndexStats:
    chunks_written: int = 0
    chunks_skipped: int = 0
    documents: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "chunks_written": self.chunks_written,
            "chunks_skipped": self.chunks_skipped,
            "documents": self.documents,
        }


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _document_text(title: str, fields: dict[str, Any]) -> str:
    lines = [title]
    for key, value in fields.items():
        if value in (None, "", [], {}):
            continue
        label = key.replace("_", " ").title()
        lines.append(f"{label}: {_fmt(value)}")
    return "\n".join(lines)


def _chunk(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    paragraphs = text.split("\n")
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 > MAX_CHUNK_CHARS and current:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _upsert_chunks(
    session: Session,
    *,
    source_type: str,
    source_id: str,
    module: str | None,
    entity_key: str | None,
    title: str,
    text: str,
    extra_metadata: dict[str, Any] | None = None,
    stats: IndexStats,
    existing_hashes: dict[str, set[str]],
) -> None:
    """Write chunks for one document, skipping unchanged content."""
    embedder = get_embedder()
    pieces = _chunk(text)
    seen = existing_hashes.setdefault(f"{source_type}:{source_id}", set())

    for index, piece in enumerate(pieces):
        digest = stable_hash({"t": piece})
        if digest in seen:
            stats.chunks_skipped += 1
            continue
        vector = embedder.embed_one(piece)
        session.add(
            DocumentChunk(
                source_type=source_type,
                source_id=source_id,
                module=module,
                entity_key=entity_key,
                title=title[:512],
                content=piece,
                token_count=len(piece.split()),
                chunk_index=index,
                embedding=vector,
                embedding_model=embedder.name,
                metadata_json=extra_metadata or {},
            )
        )
        seen.add(digest)
        stats.chunks_written += 1
    stats.documents += 1


def _load_existing_hashes(session: Session) -> dict[str, set[str]]:
    """Map ``source_type:source_id`` to the hashes of chunks already stored."""
    result: dict[str, set[str]] = {}
    rows = session.execute(
        select(DocumentChunk.source_type, DocumentChunk.source_id, DocumentChunk.content)
    ).all()
    for source_type, source_id, content in rows:
        result.setdefault(f"{source_type}:{source_id}", set()).add(stable_hash({"t": content}))
    return result


def index_all(session: Session, *, reset: bool = False) -> IndexStats:
    """Build the RAG corpus from every canonical entity."""
    stats = IndexStats()
    if reset:
        session.execute(delete(DocumentChunk))
        session.flush()
    existing = _load_existing_hashes(session)

    # --- Drugs (the richest 360 document) ---
    for drug in session.scalars(select(Drug)):
        related: dict[str, Any] = {}
        if drug.sponsor_id:
            sponsor = session.get(Sponsor, drug.sponsor_id)
            if sponsor:
                related["sponsor"] = sponsor.name
        patents = session.execute(
            select(OrangeBookPatent.patent_number, OrangeBookPatent.expiration_date)
            .join(
                OrangeBookProduct,
                (OrangeBookProduct.appl_type == OrangeBookPatent.appl_type)
                & (OrangeBookProduct.appl_no == OrangeBookPatent.appl_no),
            )
            .where(
                OrangeBookProduct.drug_id == drug.id,
                OrangeBookPatent.is_active.is_(True),
            )
        ).all()
        patent_summary = [
            f"{number} (expires {_fmt(expiration)})" for number, expiration in patents if number
        ]
        ftf_rows = session.scalars(
            select(FtfRecord).where(FtfRecord.drug_id == drug.id, FtfRecord.is_active.is_(True))
        )
        ftf_summary = [
            f"{r.drug_name} ({r.rld_nda or r.nda_number or ''}) PIV submitted "
            f"{_fmt(r.date_of_submission)} status {r.exclusivity_status or 'n/a'}"
            for r in ftf_rows
        ]
        title = f"Drug: {drug.name}"
        text = _document_text(
            title,
            {
                "ingredient": drug.ingredient,
                "therapy_area": drug.therapy_area,
                "dosage_form": drug.dosage_form,
                "strength": drug.strength,
                "rld_nda": drug.rld_nda,
                "brand_names": drug.brand_names,
                "sponsor": related.get("sponsor"),
                "listed_patents": patent_summary[:10],
                "paragraph_iv_filings": ftf_summary[:10],
            },
        )
        _upsert_chunks(
            session,
            source_type="drug",
            source_id=drug.id,
            module=None,
            entity_key=drug.normalized_name,
            title=title,
            text=text,
            extra_metadata={"therapy_area": drug.therapy_area},
            stats=stats,
            existing_hashes=existing,
        )

    # --- Patents ---
    for patent in session.scalars(select(Patent)):
        title = f"Patent: {patent.patent_number}"
        text = _document_text(
            title,
            {
                "expiration_date": patent.expiration_date,
                "original_expiration_date": patent.original_expiration_date,
                "assignee": patent.assignee,
                "has_pte": patent.has_pte,
                "pte_extension_days": patent.pte_extension_days,
                "has_paragraph_iv": patent.has_paragraph_iv,
                "drug_substance_flag": patent.drug_substance_flag,
                "drug_product_flag": patent.drug_product_flag,
                "patent_use_code": patent.patent_use_code,
                "delisted": patent.delisted,
            },
        )
        _upsert_chunks(
            session,
            source_type="patent",
            source_id=patent.id,
            module=None,
            entity_key=patent.normalized_number,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- Sponsors ---
    for sponsor in session.scalars(select(Sponsor)):
        title = f"Sponsor: {sponsor.name}"
        text = _document_text(
            title,
            {
                "aliases": sponsor.aliases,
                "type": sponsor.sponsor_type,
                "importance_score": sponsor.importance_score,
            },
        )
        _upsert_chunks(
            session,
            source_type="sponsor",
            source_id=sponsor.id,
            module=None,
            entity_key=sponsor.normalized_name,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- FTF records ---
    for row in session.scalars(select(FtfRecord).where(FtfRecord.is_active.is_(True))):
        title = f"Paragraph IV filing: {row.drug_name}"
        text = _document_text(
            title,
            {
                "nda_number": row.nda_number,
                "rld_brand_name": row.rld_brand_name,
                "dosage_form": row.dosage_form,
                "strength": row.strength,
                "date_of_submission": row.date_of_submission,
                "number_of_andas": row.number_of_andas,
                "exclusivity_status": row.exclusivity_status,
                "first_applicant_approval_date": row.first_applicant_approval_date,
                "last_qualifying_patent_expiry": row.last_qualifying_patent_expiry,
            },
        )
        _upsert_chunks(
            session,
            source_type="ftf_record",
            source_id=row.id,
            module="ftf",
            entity_key=row.source_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- PTE applications and certificates ---
    for row in session.scalars(select(PteApplication).where(PteApplication.is_active.is_(True))):
        title = f"PTE application: {row.trade_name or row.patent_number}"
        text = _document_text(
            title,
            {
                "application_number": row.application_number,
                "patent_number": row.patent_number,
                "filing_date": row.filing_date,
                "generic_name": row.generic_name,
                "designated_number": row.designated_number,
            },
        )
        _upsert_chunks(
            session,
            source_type="pte_application",
            source_id=row.id,
            module="pte",
            entity_key=row.source_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    for row in session.scalars(select(PteCertificate).where(PteCertificate.is_active.is_(True))):
        title = f"PTE certificate: {row.trade_name or row.patent_number}"
        text = _document_text(
            title,
            {
                "patent_number": row.patent_number,
                "generic_name": row.generic_name,
                "original_expiration_date": row.original_expiration_date,
                "extension_days": row.extension_days,
                "extension_text": row.extension_text,
            },
        )
        _upsert_chunks(
            session,
            source_type="pte_certificate",
            source_id=row.id,
            module="pte",
            entity_key=row.source_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- Active moieties ---
    for row in session.scalars(select(ActiveMoiety).where(ActiveMoiety.is_active.is_(True))):
        title = f"Approved active moiety: {row.moiety_name}"
        text = _document_text(
            title,
            {"sponsor": row.sponsor_name, "date_issued": row.date_issued, "status": row.status},
        )
        _upsert_chunks(
            session,
            source_type="active_moiety",
            source_id=row.id,
            module="pde",
            entity_key=row.source_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- Orange Book products ---
    for row in session.scalars(
        select(OrangeBookProduct).where(OrangeBookProduct.is_active.is_(True))
    ):
        title = f"Orange Book product: {row.trade_name or row.ingredient}"
        text = _document_text(
            title,
            {
                "application": f"{row.appl_type}{row.appl_no}",
                "ingredient": row.ingredient,
                "applicant": row.applicant_full_name or row.applicant,
                "strength": row.strength,
                "dosage_form_route": row.dosage_form_route,
                "te_code": row.te_code,
                "approval_date": row.approval_date,
                "reference_listed_drug": row.rld,
                "product_type": row.product_type,
            },
        )
        _upsert_chunks(
            session,
            source_type="orange_book_product",
            source_id=row.id,
            module="orange_book",
            entity_key=row.source_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    # --- Insights (so the copilot can reason over prior analysis) ---
    for insight in session.scalars(select(Insight)):
        title = insight.title
        text = _document_text(
            title,
            {
                "what_changed": insight.what_changed,
                "why_it_matters": insight.why_it_matters,
                "generic_opportunity": insight.generic_opportunity,
                "exclusivity_risk": insight.exclusivity_risk,
                "recommended_action": insight.recommended_action,
                "priority": f"{insight.priority_label} ({insight.priority_score})",
                "affected_companies": insight.affected_companies,
                "affected_products": insight.affected_products,
            },
        )
        _upsert_chunks(
            session,
            source_type="insight",
            source_id=insight.id,
            module=insight.module,
            entity_key=insight.entity_key,
            title=title,
            text=text,
            stats=stats,
            existing_hashes=existing,
        )

    session.flush()
    log.info("search index built: %s", stats.to_dict())
    return stats
