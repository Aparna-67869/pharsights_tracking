"""Pydantic schemas for the REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


# ---- Auth -----------------------------------------------------------------


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    username: str


class UserProfile(BaseModel):
    username: str
    role: str
    permissions: list[str]


# ---- Sources & pipeline ---------------------------------------------------


class SourceOut(ORMModel):
    id: str
    code: str
    name: str
    module: str
    url: str
    document_kind: str | None = None
    cadence: str | None = None
    description: str | None = None
    enabled: bool
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None


class SourceDocumentOut(ORMModel):
    id: str
    source_code: str
    module: str
    url: str
    filename: str | None = None
    version: int
    is_current: bool
    publication_date: date | None = None
    publication_label: str | None = None
    record_count: int | None = None
    parse_status: str | None = None
    byte_size: int | None = None
    content_hash: str | None = None
    fetched_at: datetime | None = None


class CollectionRunOut(ORMModel):
    id: str
    source_code: str
    status: str
    new_version: bool
    records_parsed: int | None = None
    duration_ms: int | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    details: dict[str, Any] | None = None


class PipelineRunOut(ORMModel):
    id: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    sources_checked: int | None = None
    sources_changed: int | None = None
    changes_detected: int | None = None
    insights_generated: int | None = None
    alerts_created: int | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None


class PipelineTriggerRequest(BaseModel):
    modules: list[str] | None = None
    source_codes: list[str] | None = None
    skip_graph: bool = False
    skip_index: bool = False
    skip_alerts: bool = False


# ---- FTF ------------------------------------------------------------------


class FtfRecordOut(ORMModel):
    id: str
    drug_name: str
    dosage_form: str | None = None
    strength: str | None = None
    rld_nda: str | None = None
    rld_brand_name: str | None = None
    nda_number: str | None = None
    date_of_submission: date | None = None
    number_of_andas: int | None = None
    exclusivity_status: str | None = None
    decision_posting_date: date | None = None
    first_applicant_approval_date: date | None = None
    first_commercial_marketing_date: date | None = None
    last_qualifying_patent_expiry: date | None = None
    certification_type: str | None = None
    source_code: str
    first_seen_at: datetime
    drug_id: str | None = None
    patent_id: str | None = None


# ---- PTE ------------------------------------------------------------------


class PteApplicationOut(ORMModel):
    id: str
    application_number: str
    patent_number: str
    filing_date: date | None = None
    trade_name: str | None = None
    generic_name: str | None = None
    designated_number: str | None = None
    sponsor_name: str | None = None
    status: str | None = None
    source_code: str


class PteCertificateOut(ORMModel):
    id: str
    patent_number: str
    trade_name: str | None = None
    generic_name: str | None = None
    sponsor_name: str | None = None
    original_expiration_date: date | None = None
    extended_expiration_date: date | None = None
    extension_days: int | None = None
    extension_text: str | None = None
    granted_date: date | None = None
    status: str | None = None
    source_code: str


# ---- PDE ------------------------------------------------------------------


class ActiveMoietyOut(ORMModel):
    id: str
    moiety_name: str
    sponsor_name: str | None = None
    date_issued: date | None = None
    approval_year: int | None = None
    status: str | None = None
    source_code: str
    drug_id: str | None = None


# ---- Orange Book ----------------------------------------------------------


class OrangeBookProductOut(ORMModel):
    id: str
    appl_type: str
    appl_no: str
    product_no: str | None = None
    ingredient: str | None = None
    trade_name: str | None = None
    applicant: str | None = None
    applicant_full_name: str | None = None
    strength: str | None = None
    dosage_form_route: str | None = None
    te_code: str | None = None
    approval_date: date | None = None
    rld: bool | None = None
    rs: bool | None = None
    product_type: str | None = None


class OrangeBookPatentOut(ORMModel):
    id: str
    appl_type: str
    appl_no: str
    product_no: str | None = None
    patent_number: str
    expiration_date: date | None = None
    drug_substance_flag: bool | None = None
    drug_product_flag: bool | None = None
    patent_use_code: str | None = None
    delist_flag: bool | None = None


class OrangeBookExclusivityOut(ORMModel):
    id: str
    appl_type: str
    appl_no: str
    product_no: str | None = None
    exclusivity_code: str
    exclusivity_date: date | None = None
    exclusivity_meaning: str | None = None


class OrangeBookSupplementOut(ORMModel):
    id: str
    supplement_number: str
    edition: str | None = None
    publication_month: int | None = None
    publication_year: int | None = None
    publication_date: date | None = None
    is_current: bool
    products_added: int | None = None
    products_removed: int | None = None
    products_modified: int | None = None


# ---- Changes, insights, alerts -------------------------------------------


class DetectedChangeOut(ORMModel):
    id: str
    module: str
    source_code: str
    entity_type: str
    change_type: str
    source_key: str
    detected_at: datetime
    is_baseline: bool
    field_changes: list[dict[str, Any]] | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class InsightOut(ORMModel):
    id: str
    module: str
    entity_type: str
    entity_key: str
    title: str
    what_changed: str | None = None
    why_it_matters: str | None = None
    affected_companies: list[str] | None = None
    affected_products: list[str] | None = None
    generic_opportunity: str | None = None
    exclusivity_risk: str | None = None
    recommended_action: str | None = None
    priority_score: int
    priority_label: str
    score_breakdown: dict[str, Any] | None = None
    generated_by: str | None = None
    confidence: float | None = None
    created_at: datetime


class AlertOut(ORMModel):
    id: str
    module: str
    event_type: str
    severity: str
    title: str
    message: str | None = None
    priority_score: int
    priority_label: str
    status: str
    entity_type: str | None = None
    entity_key: str | None = None
    drug_name: str | None = None
    sponsor_name: str | None = None
    insight_id: str | None = None
    channels_sent: list[str] | None = None
    acknowledged_by: str | None = None
    created_at: datetime


class AlertUpdate(BaseModel):
    status: str | None = None
    acknowledged_by: str | None = None


# ---- Knowledge graph & search --------------------------------------------


class GraphNodeOut(BaseModel):
    id: str
    type: str
    key: str
    label: str
    ref_table: str | None = None
    ref_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    importance: float = 50.0


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphNeighborhoodOut(BaseModel):
    root: GraphNodeOut
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class SearchHitOut(BaseModel):
    entity_type: str
    id: str
    title: str
    subtitle: str | None = None
    score: float
    matched_on: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    url: str | None = None


class SearchResultOut(BaseModel):
    query: str
    interpreted_as: dict[str, Any] = Field(default_factory=dict)
    total: int
    hits: list[SearchHitOut]
    facets: dict[str, int] = Field(default_factory=dict)


class DrugDetailOut(ORMModel):
    id: str
    name: str
    ingredient: str | None = None
    therapy_area: str | None = None
    dosage_form: str | None = None
    strength: str | None = None
    rld_nda: str | None = None
    brand_names: list[str] | None = None
    sponsor_id: str | None = None


# ---- Copilot --------------------------------------------------------------


class CopilotAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    use_llm: bool = True
    conversation_id: str | None = None


class CopilotToolCallOut(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    result_summary: Any = None


class CopilotAnswerOut(BaseModel):
    question: str
    answer: str
    intent: str
    tool_calls: list[CopilotToolCallOut] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    model: str
    provider: str
    latency_ms: int
    data: dict[str, Any] = Field(default_factory=dict)


# ---- Dashboard ------------------------------------------------------------


class KpiOut(BaseModel):
    kpis: dict[str, Any]
    alerts: dict[str, Any]


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    module: str | None = None
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False


class SavedViewOut(ORMModel):
    id: str
    name: str
    module: str | None = None
    description: str | None = None
    filters: dict[str, Any]
    is_shared: bool
    owner: str | None = None
    created_at: datetime


class AuditLogOut(ORMModel):
    id: str
    actor: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime
