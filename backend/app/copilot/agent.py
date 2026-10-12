"""AI Copilot: intent routing + tool execution + grounded synthesis.

The copilot is a retrieval-first agent. A deterministic intent router maps the
natural-language question onto one of the platform's structured query tools
(the same functions the dashboards use), so answers are always computed from
real records — never hallucinated. RAG context and an optional LLM layer on top
for narrative.

Supported intents map directly to the SOP's example questions:
  * new PTE applications this month
  * compare the latest Orange Book supplement with the previous one
  * active moieties approved in <therapy area>
  * Paragraph IV filings for <therapy area>
  * patents expiring in the next N months
  * sponsors with recent PTE approvals
  * generic opportunities for <year>
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.alerts.engine import alert_summary
from app.copilot.embeddings import get_embedder
from app.copilot.llm import ChatMessage, get_llm
from app.copilot.rag import build_context_block, retrieve
from app.core.logging import get_logger
from app.db.models import (
    ActiveMoiety,
    Drug,
    FtfRecord,
    Insight,
    OrangeBookProduct,
    OrangeBookSupplement,
    Patent,
    PteApplication,
    PteCertificate,
    Sponsor,
)
from app.intelligence.analytics import (
    executive_kpis,
    generic_opportunity_heatmap,
    patents_expiring_soon,
    pde_summary,
    pde_top_sponsors,
    pte_summary,
)
from app.search.global_search import search as global_search

log = get_logger(__name__)

SYSTEM_PROMPT = """You are the Pharma Intelligence Copilot, an expert regulatory-affairs and \
intellectual-property analyst for a pharmaceutical company.

You answer questions about FDA Paragraph IV (first-to-file) certifications, USPTO patent term \
extensions, approved active moieties, and the Orange Book, using ONLY the records provided in the \
CONTEXT section.

Rules:
- Ground every factual claim in the CONTEXT. Never invent drug names, patent numbers, dates or companies.
- If the CONTEXT does not contain the answer, say so plainly and suggest a more specific query.
- Be concise and structured. Lead with the direct answer, then supporting detail.
- Express dates as ISO (YYYY-MM-DD) or as written in the source.
- Highlight regulatory significance: generic-entry opportunity, exclusivity risk, litigation exposure.
"""


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "error": self.error,
            "result_summary": _summarize(self.result),
        }


def _summarize(result: Any) -> Any:
    if isinstance(result, list):
        return {"count": len(result), "sample": result[:3]}
    if isinstance(result, dict):
        return result
    return result


@dataclass
class CopilotAnswer:
    question: str
    answer: str
    intent: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    model: str = "offline"
    provider: str = "offline"
    latency_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "intent": self.intent,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "citations": self.citations,
            "model": self.model,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "data": self.data,
        }


# ===========================================================================
# Tools — each returns structured data the UI can also render as a table
# ===========================================================================


def tool_new_pte_applications(session: Session, *, months: int = 1, limit: int = 50) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=months * 31)
    rows = session.scalars(
        select(PteApplication)
        .where(PteApplication.is_active.is_(True), PteApplication.filing_date >= cutoff)
        .order_by(desc(PteApplication.filing_date))
        .limit(limit)
    )
    return [
        {
            "application_number": r.application_number,
            "patent_number": r.patent_number,
            "trade_name": r.trade_name,
            "generic_name": r.generic_name,
            "filing_date": r.filing_date.isoformat() if r.filing_date else None,
        }
        for r in rows
    ]


def tool_new_pte_certificates(session: Session, *, months: int = 12, limit: int = 50) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=months * 31)
    rows = session.scalars(
        select(PteCertificate)
        .where(
            PteCertificate.is_active.is_(True),
            PteCertificate.first_seen_at >= cutoff,
        )
        .order_by(desc(PteCertificate.first_seen_at))
        .limit(limit)
    )
    return [
        {
            "patent_number": r.patent_number,
            "trade_name": r.trade_name,
            "generic_name": r.generic_name,
            "extension_days": r.extension_days,
            "original_expiration_date": r.original_expiration_date.isoformat()
            if r.original_expiration_date
            else None,
        }
        for r in rows
    ]


def tool_active_moieties(
    session: Session, *, therapy_area: str | None = None, months: int | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    stmt = select(ActiveMoiety).where(ActiveMoiety.is_active.is_(True))
    if therapy_area:
        drug_ids = [
            d.id
            for d in session.scalars(
                select(Drug).where(func.lower(Drug.therapy_area) == therapy_area.casefold())
            )
        ]
        stmt = stmt.where(ActiveMoiety.drug_id.in_(drug_ids)) if drug_ids else stmt.where(
            ActiveMoiety.moiety_name.ilike(f"%{therapy_area}%")
        )
    if months:
        stmt = stmt.where(ActiveMoiety.date_issued >= date.today() - timedelta(days=months * 31))
    rows = session.scalars(stmt.order_by(desc(ActiveMoiety.date_issued)).limit(limit))
    return [
        {
            "moiety_name": r.moiety_name,
            "sponsor_name": r.sponsor_name,
            "date_issued": r.date_issued.isoformat() if r.date_issued else None,
        }
        for r in rows
    ]


def tool_paragraph_iv(
    session: Session, *, therapy_area: str | None = None, drug: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    stmt = select(FtfRecord).where(FtfRecord.is_active.is_(True))
    if drug:
        stmt = stmt.where(FtfRecord.drug_name.ilike(f"%{drug}%"))
    if therapy_area:
        drug_ids = [
            d.id
            for d in session.scalars(
                select(Drug).where(func.lower(Drug.therapy_area) == therapy_area.casefold())
            )
        ]
        if drug_ids:
            stmt = stmt.where(FtfRecord.drug_id.in_(drug_ids))
    rows = session.scalars(stmt.order_by(desc(FtfRecord.date_of_submission)).limit(limit))
    return [
        {
            "drug_name": r.drug_name,
            "nda_number": r.nda_number,
            "rld_brand_name": r.rld_brand_name,
            "date_of_submission": r.date_of_submission.isoformat() if r.date_of_submission else None,
            "exclusivity_status": r.exclusivity_status,
            "number_of_andas": r.number_of_andas,
            "last_qualifying_patent_expiry": r.last_qualifying_patent_expiry.isoformat()
            if r.last_qualifying_patent_expiry
            else None,
        }
        for r in rows
    ]


def tool_pte_sponsors(session: Session, *, months: int = 24, limit: int = 25) -> list[dict[str, Any]]:
    cutoff = date.today() - timedelta(days=months * 31)
    rows = session.execute(
        select(PteCertificate.trade_name, PteCertificate.patent_number, PteCertificate.extension_days)
        .where(PteCertificate.is_active.is_(True))
        .order_by(desc(PteCertificate.created_at))
        .limit(limit)
    ).all()
    apps = session.execute(
        select(PteApplication.trade_name, PteApplication.patent_number, PteApplication.filing_date)
        .where(PteApplication.is_active.is_(True), PteApplication.filing_date >= cutoff)
        .order_by(desc(PteApplication.filing_date))
        .limit(limit)
    ).all()
    return {
        "recent_certificates": [
            {"trade_name": r[0], "patent_number": r[1], "extension_days": r[2]} for r in rows
        ],
        "recent_applications": [
            {
                "trade_name": r[0],
                "patent_number": r[1],
                "filing_date": r[2].isoformat() if r[2] else None,
            }
            for r in apps
        ],
    }


def tool_compare_supplements(session: Session) -> dict[str, Any]:
    """Compare the two most recent Orange Book supplements."""
    rows = list(
        session.scalars(
            select(OrangeBookSupplement)
            .order_by(
                desc(OrangeBookSupplement.publication_year),
                desc(OrangeBookSupplement.publication_month),
            )
            .limit(2)
        )
    )
    if not rows:
        return {"available": False, "message": "No Orange Book supplements recorded yet."}
    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    return {
        "available": True,
        "latest": {
            "supplement_number": latest.supplement_number,
            "publication_month": latest.publication_month,
            "publication_year": latest.publication_year,
            "products_added": latest.products_added,
            "products_removed": latest.products_removed,
            "products_modified": latest.products_modified,
        },
        "previous": {
            "supplement_number": previous.supplement_number,
            "publication_month": previous.publication_month,
            "publication_year": previous.publication_year,
        }
        if previous
        else None,
    }


def tool_high_priority_insights(session: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(Insight).order_by(desc(Insight.priority_score), desc(Insight.created_at)).limit(limit)
    )
    return [
        {
            "title": r.title,
            "module": r.module,
            "priority_label": r.priority_label,
            "priority_score": r.priority_score,
            "what_changed": r.what_changed,
            "recommended_action": r.recommended_action,
        }
        for r in rows
    ]


def tool_generic_opportunities(session: Session, *, year: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Products whose nearest listed patent expires in the requested year."""
    if year:
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        rows = session.execute(
            select(
                OrangeBookProduct.trade_name,
                OrangeBookProduct.ingredient,
                OrangeBookProduct.applicant_full_name,
                OrangeBookProduct.appl_type,
                OrangeBookProduct.appl_no,
                func.min(OrangeBookPatent.expiration_date),
                func.count(OrangeBookPatent.id),
            )
            .join(
                OrangeBookPatent,
                (OrangeBookPatent.appl_no == OrangeBookProduct.appl_no)
                & (OrangeBookPatent.appl_type == OrangeBookProduct.appl_type),
            )
            .where(
                OrangeBookProduct.is_active.is_(True),
                OrangeBookPatent.is_active.is_(True),
                OrangeBookPatent.expiration_date >= start,
                OrangeBookPatent.expiration_date <= end,
            )
            .group_by(
                OrangeBookProduct.trade_name,
                OrangeBookProduct.ingredient,
                OrangeBookProduct.applicant_full_name,
                OrangeBookProduct.appl_type,
                OrangeBookProduct.appl_no,
            )
            .order_by(func.min(OrangeBookPatent.expiration_date))
            .limit(limit)
        ).all()
        today = date.today()
        result = []
        for trade, ingredient, applicant, appl_type, appl_no, expiry, patent_count in rows:
            days = (expiry - today).days if expiry else None
            result.append(
                {
                    "product": trade or ingredient,
                    "ingredient": ingredient,
                    "applicant": applicant,
                    "application": f"{appl_type}{appl_no}",
                    "nearest_patent_expiry": expiry.isoformat() if expiry else None,
                    "days_to_expiry": days,
                    "listed_patents": patent_count,
                    "opportunity_score": 90,
                }
            )
        return result
    return generic_opportunity_heatmap(session, limit=limit)


def tool_patents_expiring(session: Session, *, months: int = 24, limit: int = 50) -> list[dict[str, Any]]:
    return patents_expiring_soon(session, months=months, limit=limit)


def tool_platform_overview(session: Session) -> dict[str, Any]:
    return {
        "kpis": executive_kpis(session),
        "alerts": alert_summary(session),
        "pte": pte_summary(session),
        "pde": pde_summary(session),
        "top_pde_sponsors": pde_top_sponsors(session, limit=10),
    }


TOOLS: dict[str, Callable[..., Any]] = {
    "new_pte_applications": tool_new_pte_applications,
    "new_pte_certificates": tool_new_pte_certificates,
    "active_moieties": tool_active_moieties,
    "paragraph_iv": tool_paragraph_iv,
    "pte_sponsors": tool_pte_sponsors,
    "compare_supplements": tool_compare_supplements,
    "high_priority_insights": tool_high_priority_insights,
    "generic_opportunities": tool_generic_opportunities,
    "patents_expiring": tool_patents_expiring,
    "platform_overview": tool_platform_overview,
}


# ===========================================================================
# Intent routing
# ===========================================================================

THERAPY_AREAS = [
    "oncology", "immunology", "antiviral", "cardiovascular", "diabetes",
    "neurology", "anti-infective", "respiratory", "ophthalmology",
    "gastroenterology", "rare disease",
]


def route_intent(question: str) -> tuple[str, dict[str, Any]]:
    """Map a natural-language question onto a tool + arguments."""
    q = question.casefold()
    args: dict[str, Any] = {}

    therapy_area = next((a for a in THERAPY_AREAS if a in q), None)
    if therapy_area:
        args["therapy_area"] = therapy_area.title()

    month_match = re.search(r"(?:last|past|next)?\s*(\d+)\s*month", q)
    if month_match:
        args["months"] = int(month_match.group(1))
    if "this month" in q:
        args["months"] = 1
    elif "this year" in q:
        args["months"] = 12

    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        args["year"] = int(year_match.group(1))

    if ("compare" in q or "vs" in q or "versus" in q) and "supplement" in q:
        return "compare_supplements", {}
    if "orange book" in q and ("update" in q or "supplement" in q):
        return "compare_supplements", {}
    if "paragraph iv" in q or "first to file" in q or "first-to-file" in q or "piv" in q or "ftf" in q:
        return "paragraph_iv", args
    if "pte" in q or "patent term extension" in q or "term extension" in q:
        if "certificate" in q or "grant" in q or "granted" in q or "issued" in q:
            return "new_pte_certificates", args
        if "sponsor" in q or "compan" in q:
            return "pte_sponsors", args
        return "new_pte_applications", args
    if "active moiety" in q or "active moieties" in q or "moiety" in q or "moieties" in q or "pde" in q:
        return "active_moieties", args
    if "expir" in q and ("patent" in q or "patents" in q):
        return "patents_expiring", args
    if "generic" in q and ("opportunit" in q or "entry" in q):
        return "generic_opportunities", args
    if "alert" in q or "high risk" in q or "critical" in q:
        return "high_priority_insights", args
    if any(
        token in q
        for token in ("how many", "total", "overview", "summary", "dashboard", "kpi", "status")
    ):
        return "platform_overview", {}
    return "knowledge_search", {}


# ===========================================================================
# Agent
# ===========================================================================


def _render_tool_answer(intent: str, data: Any, question: str) -> str:
    """Deterministic narrative for a tool result (used as the grounded answer)."""
    if intent == "new_pte_applications":
        if not data:
            return "No new patent term extension applications were filed in that window."
        lines = [f"{len(data)} patent term extension application(s) found:", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('trade_name') or item.get('generic_name') or '—'} "
                f"(patent {item.get('patent_number')}) filed {item.get('filing_date')}"
            )
        return "\n".join(lines)
    if intent == "new_pte_certificates":
        if not data:
            return "No PTE certificates were newly recorded in that window."
        lines = [f"{len(data)} PTE certificate(s) found:", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('trade_name') or '—'} (patent {item.get('patent_number')}) — "
                f"extension {item.get('extension_days')} days, original expiry "
                f"{item.get('original_expiration_date')}"
            )
        return "\n".join(lines)
    if intent == "active_moieties":
        if not data:
            return "No approved active moieties matched that filter."
        lines = [f"{len(data)} approved active moiety record(s):", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('moiety_name')} — {item.get('sponsor_name') or 'sponsor n/a'} "
                f"({item.get('date_issued')})"
            )
        return "\n".join(lines)
    if intent == "paragraph_iv":
        if not data:
            return "No Paragraph IV filings matched that filter."
        lines = [f"{len(data)} Paragraph IV filing(s):", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('drug_name')} ({item.get('rld_brand_name') or ''} "
                f"{item.get('nda_number') or ''}) submitted {item.get('date_of_submission')} — "
                f"status {item.get('exclusivity_status') or 'n/a'}, "
                f"{item.get('number_of_andas') or '?'} ANDA(s)"
            )
        return "\n".join(lines)
    if intent == "compare_supplements":
        if not data.get("available"):
            return data.get("message", "No supplement data available.")
        latest = data["latest"]
        previous = data.get("previous")
        lines = [
            f"Latest Orange Book cumulative supplement: #{latest.get('supplement_number')} "
            f"({latest.get('publication_month')}/{latest.get('publication_year')}).",
        ]
        if previous:
            lines.append(
                f"Previous: #{previous.get('supplement_number')} "
                f"({previous.get('publication_month')}/{previous.get('publication_year')})."
            )
        else:
            lines.append("No earlier supplement is recorded, so no comparison is possible yet.")
        lines.append(
            f"Latest edition deltas — added {latest.get('products_added', 0)}, "
            f"removed {latest.get('products_removed', 0)}, "
            f"modified {latest.get('products_modified', 0)}."
        )
        return "\n".join(lines)
    if intent == "pte_sponsors":
        certs = data.get("recent_certificates", [])
        apps = data.get("recent_applications", [])
        lines = [
            f"{len(certs)} recent PTE certificate(s) and {len(apps)} recent application(s).",
            "",
        ]
        for item in certs[:10]:
            lines.append(
                f"• Certificate: {item.get('trade_name') or '—'} (patent {item.get('patent_number')}, "
                f"+{item.get('extension_days')} days)"
            )
        for item in apps[:10]:
            lines.append(
                f"• Application: {item.get('trade_name') or '—'} (patent {item.get('patent_number')}, "
                f"filed {item.get('filing_date')})"
            )
        return "\n".join(lines)
    if intent == "patents_expiring":
        if not data:
            return "No patents expire in that window."
        lines = [f"{len(data)} patent(s) expiring in the window:", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('patent_number')} expires {item.get('expiration_date')} "
                f"({item.get('days_remaining')} days) — assignee {item.get('assignee') or 'n/a'}"
                + (" [PTE granted]" if item.get("has_pte") else "")
                + (" [Paragraph IV]" if item.get("has_paragraph_iv") else "")
            )
        return "\n".join(lines)
    if intent == "generic_opportunities":
        if not data:
            return "No generic opportunities matched that filter."
        lines = [f"{len(data)} product(s) with near-term patent expiry:", ""]
        for item in data[:15]:
            lines.append(
                f"• {item.get('product')} ({item.get('application')}) — nearest patent expiry "
                f"{item.get('nearest_patent_expiry')}, opportunity score "
                f"{item.get('opportunity_score')}/100"
            )
        return "\n".join(lines)
    if intent == "high_priority_insights":
        if not data:
            return "There are no generated insights yet."
        lines = [f"{len(data)} highest-priority insight(s):", ""]
        for item in data[:12]:
            lines.append(
                f"• [{item.get('priority_label').upper()} {item.get('priority_score')}] "
                f"{item.get('title')}\n  {item.get('recommended_action') or ''}"
            )
        return "\n".join(lines)
    if intent == "platform_overview":
        kpis = data.get("kpis", {})
        alerts = data.get("alerts", {})
        return (
            "Platform overview:\n\n"
            f"• Drugs monitored: {kpis.get('drugs_monitored', 0)}\n"
            f"• Patents expiring within 24 months: {kpis.get('patents_expiring_soon', 0)}\n"
            f"• New Paragraph IV records (30d): {kpis.get('new_ftf_records', 0)}\n"
            f"• New PTE applications (30d): {kpis.get('new_pte_applications', 0)}\n"
            f"• New PTE grants (30d): {kpis.get('new_pte_grants', 0)}\n"
            f"• New active moieties (30d): {kpis.get('new_active_moieties', 0)}\n"
            f"• Orange Book updates (30d): {kpis.get('orange_book_updates', 0)}\n"
            f"• Open alerts: {alerts.get('open_total', 0)}\n"
            f"• High-risk opportunities: {kpis.get('high_risk_opportunities', 0)}"
        )
    return ""


def ask(
    session: Session,
    question: str,
    *,
    use_llm: bool = True,
    conversation_context: str | None = None,
) -> CopilotAnswer:
    """Answer a question end-to-end: route -> execute -> retrieve -> synthesize."""
    started = time.time()
    intent, args = route_intent(question)
    tool_calls: list[ToolCall] = []
    data: Any = None

    if intent in TOOLS:
        call = ToolCall(name=intent, arguments=args)
        try:
            call.result = TOOLS[intent](session, **args)
            data = call.result
        except TypeError:
            # Arguments did not match the tool signature; call with defaults.
            try:
                call.result = TOOLS[intent](session)
                data = call.result
            except Exception as exc:
                call.error = str(exc)
        except Exception as exc:
            call.error = str(exc)
        tool_calls.append(call)
    else:
        intent = "knowledge_search"
        call = ToolCall(name="global_search", arguments={"query": question})
        call.result = global_search(session, question, limit=10).to_dict()
        data = call.result
        tool_calls.append(call)

    # Retrieval for grounding and citations.
    chunks = retrieve(session, question, top_k=8)
    citations = [c.citation() for c in chunks]
    context_block = build_context_block(chunks)

    grounded = _render_tool_answer(intent, data, question)

    llm = get_llm()
    answer_text = grounded
    model = "rule-engine"
    provider = "offline"

    if use_llm and llm.available:
        messages = [
            ChatMessage(
                role="system",
                content=(
                    f"{SYSTEM_PROMPT}\n\n{context_block}\n\n"
                    f"STRUCTURED TOOL RESULT (authoritative, use this first):\n{grounded}"
                ),
            ),
            ChatMessage(role="user", content=question),
        ]
        if conversation_context:
            messages.insert(1, ChatMessage(role="system", content=f"Conversation so far:\n{conversation_context}"))
        try:
            response = llm.complete(messages)
            answer_text = response.content
            model = response.model
            provider = response.provider
        except Exception as exc:
            log.warning("llm completion failed (%s); using deterministic answer", exc)

    if not answer_text:
        answer_text = (
            "I could not map that question onto a supported query. Try naming a drug, patent "
            "number, NDA/ANDA number, sponsor, active moiety, or ask about Paragraph IV filings, "
            "PTE applications, Orange Book supplements or generic opportunities."
        )

    return CopilotAnswer(
        question=question,
        answer=answer_text,
        intent=intent,
        tool_calls=tool_calls,
        citations=citations,
        model=model,
        provider=provider,
        latency_ms=int((time.time() - started) * 1000),
        data=data if isinstance(data, dict) else {"items": data} if isinstance(data, list) else {},
    )


SUGGESTED_QUESTIONS: list[str] = [
    "Show all new PTE applications this month.",
    "Compare the latest Orange Book supplement with the previous one.",
    "Show active moieties approved in oncology.",
    "Show Paragraph IV filings for diabetes products.",
    "List patents expiring in the next 24 months.",
    "Which sponsors received PTE approvals recently?",
    "Find generic opportunities for 2028.",
    "What are the highest priority alerts right now?",
    "Give me a platform overview.",
]
