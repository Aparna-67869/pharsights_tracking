"""GraphQL API (Strawberry) exposing the same intelligence as the REST layer.

The GraphQL surface is deliberately read-focused: it is the path the Next.js
dashboard uses for nested data (a drug with its patents, PTE, FTF and Orange
Book records in one round trip), while writes stay on REST.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import strawberry
from sqlalchemy import desc, func, select
from strawberry.types import Info

from app.core.logging import get_logger
from app.db.models import (
    ActiveMoiety,
    Alert,
    DetectedChange,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookProduct,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)
from app.db.session import session_scope

log = get_logger(__name__)


def _session() -> Any:
    return session_scope()


# ---- Types -----------------------------------------------------------------


@strawberry.type
class FtfType:
    id: str
    drug_name: str
    rld_brand_name: str | None
    nda_number: str | None
    date_of_submission: date | None
    number_of_andas: int | None
    exclusivity_status: str | None
    last_qualifying_patent_expiry: date | None

    @classmethod
    def from_model(cls, row: FtfRecord) -> FtfType:
        return cls(
            id=row.id,
            drug_name=row.drug_name,
            rld_brand_name=row.rld_brand_name,
            nda_number=row.nda_number,
            date_of_submission=row.date_of_submission,
            number_of_andas=row.number_of_andas,
            exclusivity_status=row.exclusivity_status,
            last_qualifying_patent_expiry=row.last_qualifying_patent_expiry,
        )


@strawberry.type
class PatentType:
    id: str
    patent_number: str
    expiration_date: date | None
    assignee: str | None
    has_pte: bool
    has_paragraph_iv: bool

    @classmethod
    def from_model(cls, row: Patent) -> PatentType:
        return cls(
            id=row.id,
            patent_number=row.patent_number,
            expiration_date=row.expiration_date,
            assignee=row.assignee,
            has_pte=bool(row.has_pte),
            has_paragraph_iv=bool(row.has_paragraph_iv),
        )


@strawberry.type
class PteApplicationType:
    id: str
    application_number: str
    patent_number: str
    trade_name: str | None
    filing_date: date | None

    @classmethod
    def from_model(cls, row: PteApplication) -> PteApplicationType:
        return cls(
            id=row.id,
            application_number=row.application_number,
            patent_number=row.patent_number,
            trade_name=row.trade_name,
            filing_date=row.filing_date,
        )


@strawberry.type
class PteCertificateType:
    id: str
    patent_number: str
    trade_name: str | None
    extension_days: int | None
    original_expiration_date: date | None
    extended_expiration_date: date | None

    @classmethod
    def from_model(cls, row: PteCertificate) -> PteCertificateType:
        return cls(
            id=row.id,
            patent_number=row.patent_number,
            trade_name=row.trade_name,
            extension_days=row.extension_days,
            original_expiration_date=row.original_expiration_date,
            extended_expiration_date=row.extended_expiration_date,
        )


@strawberry.type
class ActiveMoietyType:
    id: str
    moiety_name: str
    sponsor_name: str | None
    date_issued: date | None

    @classmethod
    def from_model(cls, row: ActiveMoiety) -> ActiveMoietyType:
        return cls(
            id=row.id,
            moiety_name=row.moiety_name,
            sponsor_name=row.sponsor_name,
            date_issued=row.date_issued,
        )


@strawberry.type
class OrangeBookProductType:
    id: str
    application: str
    trade_name: str | None
    ingredient: str | None
    applicant: str | None
    te_code: str | None
    approval_date: date | None

    @classmethod
    def from_model(cls, row: OrangeBookProduct) -> OrangeBookProductType:
        return cls(
            id=row.id,
            application=f"{row.appl_type}{row.appl_no}",
            trade_name=row.trade_name,
            ingredient=row.ingredient,
            applicant=row.applicant_full_name or row.applicant,
            te_code=row.te_code,
            approval_date=row.approval_date,
        )


@strawberry.type
class DrugType:
    id: str
    name: str
    ingredient: str | None
    therapy_area: str | None
    brand_names: list[str]
    sponsor_name: str | None

    @classmethod
    def from_model(cls, row: Drug, sponsor_name: str | None = None) -> DrugType:
        return cls(
            id=row.id,
            name=row.name,
            ingredient=row.ingredient,
            therapy_area=row.therapy_area,
            brand_names=list(row.brand_names or []),
            sponsor_name=sponsor_name,
        )

    @strawberry.field
    def paragraph_iv_filings(self, info: Info) -> list[FtfType]:
        with _session() as session:
            rows = session.scalars(
                select(FtfRecord).where(FtfRecord.drug_id == self.id, FtfRecord.is_active.is_(True))
            )
            return [FtfType.from_model(r) for r in rows]

    @strawberry.field
    def pte_certificates(self, info: Info) -> list[PteCertificateType]:
        with _session() as session:
            rows = session.scalars(
                select(PteCertificate).where(
                    PteCertificate.drug_id == self.id, PteCertificate.is_active.is_(True)
                )
            )
            return [PteCertificateType.from_model(r) for r in rows]

    @strawberry.field
    def orange_book_products(self, info: Info) -> list[OrangeBookProductType]:
        with _session() as session:
            rows = session.scalars(
                select(OrangeBookProduct).where(
                    OrangeBookProduct.drug_id == self.id, OrangeBookProduct.is_active.is_(True)
                )
            )
            return [OrangeBookProductType.from_model(r) for r in rows]


@strawberry.type
class AlertType:
    id: str
    module: str
    event_type: str
    title: str
    message: str | None
    priority_score: int
    priority_label: str
    status: str
    created_at: datetime

    @classmethod
    def from_model(cls, row: Alert) -> AlertType:
        return cls(
            id=row.id,
            module=row.module,
            event_type=row.event_type,
            title=row.title,
            message=row.message,
            priority_score=row.priority_score,
            priority_label=row.priority_label,
            status=row.status,
            created_at=row.created_at,
        )


@strawberry.type
class InsightType:
    id: str
    module: str
    title: str
    what_changed: str | None
    why_it_matters: str | None
    generic_opportunity: str | None
    exclusivity_risk: str | None
    recommended_action: str | None
    priority_score: int
    priority_label: str
    created_at: datetime

    @classmethod
    def from_model(cls, row: Insight) -> InsightType:
        return cls(
            id=row.id,
            module=row.module,
            title=row.title,
            what_changed=row.what_changed,
            why_it_matters=row.why_it_matters,
            generic_opportunity=row.generic_opportunity,
            exclusivity_risk=row.exclusivity_risk,
            recommended_action=row.recommended_action,
            priority_score=row.priority_score,
            priority_label=row.priority_label,
            created_at=row.created_at,
        )


@strawberry.type
class ChangeType:
    id: str
    module: str
    entity_type: str
    change_type: str
    source_key: str
    detected_at: datetime
    is_baseline: bool
    field_changes: strawberry.scalars.JSON

    @classmethod
    def from_model(cls, row: DetectedChange) -> ChangeType:
        return cls(
            id=row.id,
            module=row.module,
            entity_type=row.entity_type,
            change_type=row.change_type,
            source_key=row.source_key,
            detected_at=row.detected_at,
            is_baseline=bool(row.is_baseline),
            field_changes=row.field_changes or [],
        )


@strawberry.type
class KpiType:
    drugs_monitored: int
    patents_expiring_soon: int
    new_ftf_records: int
    new_pte_applications: int
    new_pte_grants: int
    new_active_moieties: int
    orange_book_updates: int
    open_alerts: int
    high_risk_opportunities: int
    changes_last_30_days: int
    insights_total: int


@strawberry.type
class CopilotAnswerType:
    answer: str
    intent: str
    model: str
    provider: str
    latency_ms: int
    citations: strawberry.scalars.JSON


# ---- Queries ---------------------------------------------------------------


@strawberry.type
class Query:
    @strawberry.field
    def kpis(self) -> KpiType:
        from app.intelligence.analytics import executive_kpis

        with _session() as session:
            return KpiType(**executive_kpis(session))

    @strawberry.field
    def drugs(self, limit: int = 25, therapy_area: str | None = None) -> list[DrugType]:
        with _session() as session:
            stmt = select(Drug)
            if therapy_area:
                stmt = stmt.where(func.lower(Drug.therapy_area) == therapy_area.casefold())
            sponsors = {s.id: s.name for s in session.scalars(select(Sponsor))}
            return [
                DrugType.from_model(d, sponsors.get(d.sponsor_id))
                for d in session.scalars(stmt.limit(limit))
            ]

    @strawberry.field
    def drug(self, drug_id: str) -> DrugType | None:
        with _session() as session:
            row = session.get(Drug, drug_id)
            if row is None:
                return None
            sponsor = session.get(Sponsor, row.sponsor_id) if row.sponsor_id else None
            return DrugType.from_model(row, sponsor.name if sponsor else None)

    @strawberry.field
    def paragraph_iv_filings(self, limit: int = 50, status: str | None = None) -> list[FtfType]:
        with _session() as session:
            stmt = select(FtfRecord).where(FtfRecord.is_active.is_(True))
            if status:
                stmt = stmt.where(func.lower(FtfRecord.exclusivity_status) == status.casefold())
            rows = session.scalars(stmt.order_by(desc(FtfRecord.date_of_submission)).limit(limit))
            return [FtfType.from_model(r) for r in rows]

    @strawberry.field
    def pte_certificates(self, limit: int = 50) -> list[PteCertificateType]:
        with _session() as session:
            rows = session.scalars(
                select(PteCertificate)
                .where(PteCertificate.is_active.is_(True))
                .order_by(desc(PteCertificate.extension_days))
                .limit(limit)
            )
            return [PteCertificateType.from_model(r) for r in rows]

    @strawberry.field
    def active_moieties(self, limit: int = 50) -> list[ActiveMoietyType]:
        with _session() as session:
            rows = session.scalars(
                select(ActiveMoiety)
                .where(ActiveMoiety.is_active.is_(True))
                .order_by(desc(ActiveMoiety.date_issued))
                .limit(limit)
            )
            return [ActiveMoietyType.from_model(r) for r in rows]

    @strawberry.field
    def alerts(self, limit: int = 50, status: str | None = "open") -> list[AlertType]:
        with _session() as session:
            stmt = select(Alert)
            if status:
                stmt = stmt.where(Alert.status == status)
            rows = session.scalars(
                stmt.order_by(desc(Alert.priority_score), desc(Alert.created_at)).limit(limit)
            )
            return [AlertType.from_model(r) for r in rows]

    @strawberry.field
    def insights(self, limit: int = 50, min_score: int | None = None) -> list[InsightType]:
        with _session() as session:
            stmt = select(Insight)
            if min_score is not None:
                stmt = stmt.where(Insight.priority_score >= min_score)
            rows = session.scalars(
                stmt.order_by(desc(Insight.priority_score), desc(Insight.created_at)).limit(limit)
            )
            return [InsightType.from_model(r) for r in rows]

    @strawberry.field
    def changes(self, limit: int = 50, include_baseline: bool = False) -> list[ChangeType]:
        with _session() as session:
            stmt = select(DetectedChange)
            if not include_baseline:
                stmt = stmt.where(DetectedChange.is_baseline.is_(False))
            rows = session.scalars(stmt.order_by(desc(DetectedChange.detected_at)).limit(limit))
            return [ChangeType.from_model(r) for r in rows]

    @strawberry.field
    def search(self, query: str, limit: int = 25) -> strawberry.scalars.JSON:
        from app.search.global_search import search as global_search

        with _session() as session:
            return global_search(session, query, limit=limit).to_dict()


@strawberry.type
class Mutation:
    @strawberry.mutation
    def ask_copilot(self, question: str, use_llm: bool = True) -> CopilotAnswerType:
        from app.copilot.agent import ask

        with _session() as session:
            answer = ask(session, question, use_llm=use_llm)
            return CopilotAnswerType(
                answer=answer.answer,
                intent=answer.intent,
                model=answer.model,
                provider=answer.provider,
                latency_ms=answer.latency_ms,
                citations=answer.citations,
            )


schema = strawberry.Schema(query=Query, mutation=Mutation)
