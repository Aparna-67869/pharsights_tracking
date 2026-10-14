"""SQLAlchemy 2.0 domain model for the Pharma Intelligence Platform.

Layout:
  * Ingestion & lineage ....... SourceDocument, CollectionRun, PipelineRun, DetectedChange
  * Reference entities ........ Sponsor, Drug, ActiveMoiety, Patent
  * Module facts .............. FtfRecord, PteApplication, PteCertificate,
                                OrangeBookProduct, OrangeBookPatent,
                                OrangeBookExclusivity, OrangeBookSupplement
  * Knowledge graph ........... KgNode, KgEdge
  * Intelligence output ....... Insight, Alert, NotificationLog
  * Platform .................. User, SavedView, AuditLog,
                                CopilotConversation, CopilotMessage, DocumentChunk

Every monitored fact table carries ``source_key`` + ``content_hash`` so the
change-detection engine can diff versions without relying on primary keys.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey, new_uuid, utcnow

# ===========================================================================
# Ingestion, lineage and change tracking
# ===========================================================================


class SourceDefinition(Base, UUIDPrimaryKey, TimestampMixin):
    """Registry of monitored regulatory sources (the SOP's monitored pages)."""

    __tablename__ = "source_definitions"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    module: Mapped[str] = mapped_column(String(32), index=True)  # ftf|pte|pde|orange_book
    url: Mapped[str] = mapped_column(String(1024))
    document_kind: Mapped[str] = mapped_column(String(32))  # pdf|xlsx|xls|zip|html
    cadence: Mapped[str] = mapped_column(String(32), default="daily")  # daily|monthly
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Locator config used by the collector to resolve the current document URL
    # (CSS selector / regex / direct link), stored as JSON for flexibility.
    locator: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Health mirror of the most recent collection attempt for this source.
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list[SourceDocument]] = relationship(back_populates="source_def")


class SourceDocument(Base, UUIDPrimaryKey, TimestampMixin):
    """A concrete fetched artifact and its immutable version lineage."""

    __tablename__ = "source_documents"

    source_code: Mapped[str] = mapped_column(String(64), ForeignKey("source_definitions.code"), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    filename: Mapped[str] = mapped_column(String(512))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Publication/update date parsed out of the document itself (authoritative),
    # distinct from fetched_at (when we happened to download it).
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    publication_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # record_count is what the module actually serves (valid, deduplicated rows);
    # source_record_count is the raw parsed row count before validation, kept so
    # the provenance bar can explain a source row the platform legitimately drops.
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    source_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|ok|failed
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source_def: Mapped[SourceDefinition] = relationship(back_populates="documents")
    changes: Mapped[list[DetectedChange]] = relationship(back_populates="document")

    __table_args__ = (
        Index("ix_source_documents_current", "source_code", "is_current"),
        Index("ix_source_documents_hash", "source_code", "content_hash"),
    )


class CollectionRun(Base, UUIDPrimaryKey, TimestampMixin):
    """One execution of a single source collector."""

    __tablename__ = "collection_runs"

    source_code: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    new_version: Mapped[bool] = mapped_column(Boolean, default=False)
    records_parsed: Mapped[int] = mapped_column(Integer, default=0)
    records_added: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_removed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PipelineRun(Base, UUIDPrimaryKey, TimestampMixin):
    """End-to-end orchestration run (all collectors -> detect -> analyze -> alert)."""

    __tablename__ = "pipeline_runs"

    run_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_uuid)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")  # manual|airflow|api|scheduled
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sources_checked: Mapped[int] = mapped_column(Integer, default=0)
    sources_changed: Mapped[int] = mapped_column(Integer, default=0)
    changes_detected: Mapped[int] = mapped_column(Integer, default=0)
    insights_generated: Mapped[int] = mapped_column(Integer, default=0)
    alerts_created: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class DetectedChange(Base, UUIDPrimaryKey, TimestampMixin):
    """A single delta between two document versions.

    ``change_type`` is one of added | updated | removed. ``before``/``after``
    hold the normalized record payloads so the UI can render a field-level diff.
    """

    __tablename__ = "detected_changes"

    module: Mapped[str] = mapped_column(String(32), index=True)
    source_code: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    change_type: Mapped[str] = mapped_column(String(16), index=True)
    source_key: Mapped[str] = mapped_column(String(512), index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("source_documents.id"), nullable=True)
    previous_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    field_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    significance: Mapped[int] = mapped_column(Integer, default=50)  # 0-100
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # A change detected on the very first snapshot of a source is baseline data,
    # not a regulatory event. Baseline changes populate history but never raise
    # alerts, so onboarding a new source does not flood users with notifications.
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    document: Mapped[SourceDocument | None] = relationship(back_populates="changes")

    __table_args__ = (
        Index("ix_detected_changes_lookup", "module", "entity_type", "detected_at"),
        Index("ix_detected_changes_dedupe", "source_code", "source_key", "change_type", "document_id"),
    )


# ===========================================================================
# Reference entities
# ===========================================================================


class Sponsor(Base, UUIDPrimaryKey, TimestampMixin):
    """Company: NDA/ANDA applicant, patent assignee, PTE sponsor, PDE sponsor."""

    __tablename__ = "sponsors"

    name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    sponsor_type: Mapped[str | None] = mapped_column(String(48), nullable=True)  # brand|generic|biotech
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    headquarters: Mapped[str | None] = mapped_column(String(255), nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=50.0)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    __table_args__ = (UniqueConstraint("normalized_name", name="uq_sponsor_normalized_name"),)


class Drug(Base, UUIDPrimaryKey, TimestampMixin):
    """Canonical product entity spanning all modules."""

    __tablename__ = "drugs"

    name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    ingredient: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(512), nullable=True)
    route: Mapped[str | None] = mapped_column(String(255), nullable=True)
    therapy_area: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    brand_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    rld_nda: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    __table_args__ = (Index("ix_drugs_norm_name", "normalized_name", unique=False),)


class ActiveMoiety(Base, UUIDPrimaryKey, TimestampMixin):
    """Approved active moiety (PDE / written-requests module)."""

    __tablename__ = "active_moieties"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    # 0-based position in the FDA workbook; see PteApplication.source_ordinal.
    source_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moiety_name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    sponsor_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    date_issued: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    approval_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="approved")
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    drug_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (Index("ix_active_moieties_key", "source_key", "content_hash"),)


class Patent(Base, UUIDPrimaryKey, TimestampMixin):
    """Canonical patent entity aggregated from Orange Book, PTE and FTF."""

    __tablename__ = "patents"

    patent_number: Mapped[str] = mapped_column(String(64), index=True)
    normalized_number: Mapped[str] = mapped_column(String(64), index=True)
    patent_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # utility|reissue
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    original_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    adjusted_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pte_extension_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_pte: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    has_paragraph_iv: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    drug_substance_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drug_product_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    patent_use_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delisted: Mapped[bool] = mapped_column(Boolean, default=False)
    inpadoc_family_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    family_members: Mapped[list[str]] = mapped_column(JSON, default=list)
    litigation: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    __table_args__ = (UniqueConstraint("normalized_number", name="uq_patent_normalized_number"),)


# ===========================================================================
# Module facts — FTF
# ===========================================================================


class FtfRecord(Base, UUIDPrimaryKey, TimestampMixin):
    """Paragraph IV (first-to-file) certification row from the FDA PPIV list."""

    __tablename__ = "ftf_records"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    # 0-based position of this row in the published FDA document. The SOP renders
    # the table in the regulator's own order, so the position is stored rather
    # than re-derived by sorting a column.
    source_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    drug_name: Mapped[str] = mapped_column(String(512), index=True)
    dosage_form: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rld_nda: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rld_brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nda_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    date_of_submission: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    number_of_andas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exclusivity_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    decision_posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_applicant_approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_commercial_marketing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_qualifying_patent_expiry: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    certification_type: Mapped[str] = mapped_column(String(32), default="Paragraph IV")
    applicant: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    patent_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Exact text as published in the source row. The typed columns above hold
    # forms safe for joins/lookups; the UI must always render these raw values.
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")
    drug_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=True)
    patent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patents.id"), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (
        UniqueConstraint("source_key", "content_hash", name="uq_ftf_key_hash"),
        Index("ix_ftf_active_submission", "is_active", "date_of_submission"),
    )


# ===========================================================================
# Module facts — PTE
# ===========================================================================


class PteApplication(Base, UUIDPrimaryKey, TimestampMixin):
    """Patent Term Extension application (USPTO, last five years)."""

    __tablename__ = "pte_applications"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    # 0-based position of this row in the published USPTO workbook; the SOP
    # renders the table in the regulator's own order rather than a sorted column.
    source_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    application_number: Mapped[str] = mapped_column(String(64), index=True)
    patent_number: Mapped[str] = mapped_column(String(64), index=True)
    patent_center_link: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    trade_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    generic_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    designated_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sponsor_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    application_number_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(48), default="filed")
    drug_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=True)
    patent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patents.id"), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source_key", "content_hash", name="uq_pte_app_key_hash"),)


class PteCertificate(Base, UUIDPrimaryKey, TimestampMixin):
    """Granted patent term extension certificate (USPTO)."""

    __tablename__ = "pte_certificates"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    source_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    patent_number: Mapped[str] = mapped_column(String(64), index=True)
    trade_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    generic_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sponsor_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    original_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    extended_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    extension_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extension_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    granted_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="granted")
    drug_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=True)
    patent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patents.id"), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source_key", "content_hash", name="uq_pte_cert_key_hash"),)


# ===========================================================================
# Module facts — Orange Book
# ===========================================================================


class OrangeBookSupplement(Base, UUIDPrimaryKey, TimestampMixin):
    """A published Orange Book cumulative supplement edition."""

    __tablename__ = "orange_book_supplements"

    supplement_number: Mapped[str] = mapped_column(String(32), index=True)
    edition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    products_added: Mapped[int] = mapped_column(Integer, default=0)
    products_removed: Mapped[int] = mapped_column(Integer, default=0)
    products_modified: Mapped[int] = mapped_column(Integer, default=0)
    patents_added: Mapped[int] = mapped_column(Integer, default=0)
    exclusivity_added: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("supplement_number", "publication_year", name="uq_ob_supplement_edition"),
    )


class OrangeBookProduct(Base, UUIDPrimaryKey, TimestampMixin):
    """Approved drug product row from the Orange Book data files."""

    __tablename__ = "orange_book_products"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    ingredient: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    dosage_form_route: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trade_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    applicant: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    applicant_full_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(512), nullable=True)
    appl_type: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    appl_no: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    appl_no_normalized: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    product_no: Mapped[str | None] = mapped_column(String(8), nullable=True)
    te_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    rld: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rs: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(8), nullable=True)  # RX|OTC|DISCN
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    drug_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=True)
    sponsor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sponsors.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (
        UniqueConstraint("source_key", "content_hash", name="uq_ob_product_key_hash"),
        Index("ix_ob_product_appl", "appl_type", "appl_no"),
    )


class OrangeBookPatent(Base, UUIDPrimaryKey, TimestampMixin):
    """Patent listing attached to an Orange Book product."""

    __tablename__ = "orange_book_patents"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    appl_type: Mapped[str] = mapped_column(String(4), index=True)
    appl_no: Mapped[str] = mapped_column(String(16), index=True)
    product_no: Mapped[str | None] = mapped_column(String(8), nullable=True)
    patent_number: Mapped[str] = mapped_column(String(64), index=True)
    expiration_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    drug_substance_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    drug_product_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    patent_use_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delist_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    patent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patents.id"), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source_key", "content_hash", name="uq_ob_patent_key_hash"),)


class OrangeBookExclusivity(Base, UUIDPrimaryKey, TimestampMixin):
    """Exclusivity grant attached to an Orange Book product."""

    __tablename__ = "orange_book_exclusivity"

    source_code: Mapped[str] = mapped_column(String(64), index=True)

    source_key: Mapped[str] = mapped_column(String(512), index=True)
    appl_type: Mapped[str] = mapped_column(String(4), index=True)
    appl_no: Mapped[str] = mapped_column(String(16), index=True)
    product_no: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exclusivity_code: Mapped[str] = mapped_column(String(16), index=True)
    exclusivity_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    exclusivity_meaning: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    __table_args__ = (UniqueConstraint("source_key", "content_hash", name="uq_ob_excl_key_hash"),)


# ===========================================================================
# Knowledge graph
# ===========================================================================


class KgNode(Base, UUIDPrimaryKey, TimestampMixin):
    """A node in the pharma knowledge graph."""

    __tablename__ = "kg_nodes"

    node_type: Mapped[str] = mapped_column(String(48), index=True)
    # drug|patent|nda|anda|sponsor|active_moiety|clinical_trial|orange_book_record
    natural_key: Mapped[str] = mapped_column(String(512), index=True)
    label: Mapped[str] = mapped_column(String(512), index=True)
    ref_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    importance: Mapped[float] = mapped_column(Float, default=50.0)

    __table_args__ = (
        UniqueConstraint("node_type", "natural_key", name="uq_kg_node_type_key"),
        Index("ix_kg_node_ref", "ref_table", "ref_id"),
    )


class KgEdge(Base, UUIDPrimaryKey, TimestampMixin):
    """A typed, directed relationship between two graph nodes."""

    __tablename__ = "kg_edges"

    source_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("kg_nodes.id"), index=True)
    target_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("kg_nodes.id"), index=True)
    relation: Mapped[str] = mapped_column(String(64), index=True)
    # has_nda|has_anda|has_patent|marketed_by|has_active_moiety|has_pte|
    # paragraph_iv_on|listed_in_orange_book|same_family|in_litigation|tested_in
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "relation", name="uq_kg_edge"),
        Index("ix_kg_edge_source", "source_node_id", "relation"),
        Index("ix_kg_edge_target", "target_node_id", "relation"),
    )


# ===========================================================================
# Intelligence output
# ===========================================================================


class Insight(Base, UUIDPrimaryKey, TimestampMixin):
    """AI impact analysis produced for a detected change."""

    __tablename__ = "insights"

    change_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("detected_changes.id"), nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    what_changed: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_companies: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_products: Mapped[list[str]] = mapped_column(JSON, default=list)
    generic_opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusivity_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_score: Mapped[int] = mapped_column(Integer, default=50, index=True)
    priority_label: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(32), default="rule_engine")  # rule_engine|llm
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)

    __table_args__ = (Index("ix_insights_priority", "priority_label", "priority_score"),)


class Alert(Base, UUIDPrimaryKey, TimestampMixin):
    """A user-facing alert derived from one or more changes/insights."""

    __tablename__ = "alerts"

    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    title: Mapped[str] = mapped_column(String(512))
    message: Mapped[str] = mapped_column(Text)
    priority_score: Mapped[int] = mapped_column(Integer, default=50, index=True)
    priority_label: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|ack|resolved|dismissed
    entity_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    drug_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    sponsor_name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    patent_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    change_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    insight_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("insights.id"), nullable=True)
    channels_sent: Mapped[list[str]] = mapped_column(JSON, default=list)
    acknowledged_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    notifications: Mapped[list[NotificationLog]] = relationship(back_populates="alert")

    __table_args__ = (
        Index("ix_alerts_status_priority", "status", "priority_score"),
        Index("ix_alerts_module_created", "module", "created_at"),
    )


class NotificationLog(Base, UUIDPrimaryKey, TimestampMixin):
    """Delivery attempt record for one alert over one channel."""

    __tablename__ = "notification_logs"

    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)  # email|teams|dashboard
    recipient: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    alert: Mapped[Alert] = relationship(back_populates="notifications")


# ===========================================================================
# Platform: users, views, audit, copilot, RAG
# ===========================================================================


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(48), default="analyst", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SavedView(Base, UUIDPrimaryKey, TimestampMixin):
    """A persisted dashboard filter set / custom dashboard."""

    __tablename__ = "saved_views"

    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str] = mapped_column(String(48), index=True)
    view_type: Mapped[str] = mapped_column(String(32), default="table")  # table|dashboard|chart
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base, UUIDPrimaryKey):
    """Immutable audit trail for every state-changing operation."""

    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    actor_role: Mapped[str | None] = mapped_column(String(48), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CopilotConversation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "copilot_conversations"

    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="New conversation")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    messages: Mapped[list[CopilotMessage]] = relationship(back_populates="conversation")


class CopilotMessage(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "copilot_messages"

    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("copilot_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system|tool
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    conversation: Mapped[CopilotConversation] = relationship(back_populates="messages")


class DocumentChunk(Base, UUIDPrimaryKey, TimestampMixin):
    """RAG corpus chunk. ``embedding`` is stored as JSON so the same table works
    on SQLite and Postgres; production uses pgvector via a mirrored column."""

    __tablename__ = "document_chunks"

    source_type: Mapped[str] = mapped_column(String(48), index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    module: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    entity_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)

    __table_args__ = (Index("ix_chunks_source", "source_type", "source_id"),)


class AlertSubscription(Base, UUIDPrimaryKey, TimestampMixin):
    """A user's standing interest in a module, sponsor, drug, patent or area.

    Delivery is driven off the authenticated identity: email and Microsoft Teams
    notifications are addressed to the signed-in user, so no per-user SMTP or
    webhook configuration is required.
    """

    __tablename__ = "alert_subscriptions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A subscription can filter by any combination of these; empty = all.
    modules: Mapped[list[str]] = mapped_column(JSON, default=list)  # ftf|pte|pde|orange_book
    sponsors: Mapped[list[str]] = mapped_column(JSON, default=list)
    drugs: Mapped[list[str]] = mapped_column(JSON, default=list)
    patents: Mapped[list[str]] = mapped_column(JSON, default=list)
    therapy_areas: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_priority: Mapped[int] = mapped_column(Integer, default=40)
    channels: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["dashboard", "email", "teams"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
