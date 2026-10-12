"""MCP server exposing the platform to LLM agents as callable tools.

This is what makes the platform composable: an external agent (Claude Desktop,
an OpenHands conversation, an internal assistant) can query Paragraph IV
filings, patent term extensions, active moieties, Orange Book records and the
copilot itself through the Model Context Protocol.

Transport: stdio by default (``python -m app.mcp.server``), so it plugs into any
MCP client. Every tool returns JSON-serialisable data.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    FastMCP = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False


def _json(data: Any) -> str:
    return json.dumps(data, default=str, indent=2)


if _MCP_AVAILABLE:
    mcp = FastMCP("pharma-intelligence")

    @mcp.tool()
    def platform_overview() -> str:
        """Executive KPIs: drugs monitored, patents expiring, new filings, open alerts."""
        from app.copilot.agent import tool_platform_overview
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_platform_overview(session))

    @mcp.tool()
    def search_regulatory_records(query: str, limit: int = 15) -> str:
        """Search drugs, patents, NDA/ANDA numbers, sponsors and active moieties.

        Args:
            query: a drug name, patent number, NDA/ANDA number, sponsor or moiety.
            limit: maximum number of hits to return.
        """
        from app.db.session import session_scope
        from app.search.global_search import search

        with session_scope() as session:
            return _json(search(session, query, limit=limit).to_dict())

    @mcp.tool()
    def paragraph_iv_filings(
        drug: str | None = None, therapy_area: str | None = None, limit: int = 25
    ) -> str:
        """Paragraph IV (first-to-file) certifications, optionally filtered.

        Args:
            drug: filter by drug name substring.
            therapy_area: filter by therapy area, e.g. Oncology, Diabetes.
            limit: maximum number of filings to return.
        """
        from app.copilot.agent import tool_paragraph_iv
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_paragraph_iv(session, drug=drug, therapy_area=therapy_area, limit=limit))

    @mcp.tool()
    def pte_applications(months: int = 12, limit: int = 25) -> str:
        """Patent term extension applications filed in the last N months."""
        from app.copilot.agent import tool_new_pte_applications
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_new_pte_applications(session, months=months, limit=limit))

    @mcp.tool()
    def pte_certificates(months: int = 12, limit: int = 25) -> str:
        """Granted patent term extension certificates, with extension length in days."""
        from app.copilot.agent import tool_new_pte_certificates
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_new_pte_certificates(session, months=months, limit=limit))

    @mcp.tool()
    def approved_active_moieties(
        therapy_area: str | None = None, months: int | None = None, limit: int = 25
    ) -> str:
        """Approved active moieties (five-year NCE exclusivity candidates)."""
        from app.copilot.agent import tool_active_moieties
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(
                tool_active_moieties(
                    session, therapy_area=therapy_area, months=months, limit=limit
                )
            )

    @mcp.tool()
    def patents_expiring(months: int = 24, limit: int = 25) -> str:
        """Patents expiring within the next N months, with PTE and Paragraph IV flags."""
        from app.copilot.agent import tool_patents_expiring
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_patents_expiring(session, months=months, limit=limit))

    @mcp.tool()
    def generic_opportunities(year: int | None = None, limit: int = 25) -> str:
        """Products whose nearest listed patent expires in the given year (or soonest)."""
        from app.copilot.agent import tool_generic_opportunities
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_generic_opportunities(session, year=year, limit=limit))

    @mcp.tool()
    def orange_book_supplement_comparison() -> str:
        """Compare the latest Orange Book cumulative supplement with the previous one."""
        from app.copilot.agent import tool_compare_supplements
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_compare_supplements(session))

    @mcp.tool()
    def recent_changes(module: str | None = None, limit: int = 25) -> str:
        """Regulatory changes detected since the last snapshot (added/updated/removed).

        Args:
            module: one of ftf, pte, pde, orange_book.
            limit: maximum number of changes to return.
        """
        from sqlalchemy import desc, select

        from app.db.models import DetectedChange
        from app.db.session import session_scope

        with session_scope() as session:
            stmt = select(DetectedChange).where(DetectedChange.is_baseline.is_(False))
            if module:
                stmt = stmt.where(DetectedChange.module == module)
            rows = session.scalars(stmt.order_by(desc(DetectedChange.detected_at)).limit(limit))
            return _json(
                [
                    {
                        "detected_at": r.detected_at.isoformat(),
                        "module": r.module,
                        "entity_type": r.entity_type,
                        "change_type": r.change_type,
                        "source_key": r.source_key,
                        "field_changes": r.field_changes,
                    }
                    for r in rows
                ]
            )

    @mcp.tool()
    def high_priority_alerts(limit: int = 20) -> str:
        """Open alerts ranked by AI priority score (critical, high, medium)."""
        from app.copilot.agent import tool_high_priority_insights
        from app.db.session import session_scope

        with session_scope() as session:
            return _json(tool_high_priority_insights(session, limit=limit))

    @mcp.tool()
    def ask_copilot(question: str) -> str:
        """Ask the platform copilot a natural-language regulatory question."""
        from app.copilot.agent import ask
        from app.db.session import session_scope

        with session_scope() as session:
            answer = ask(session, question)
            return _json(answer.to_dict())


def main() -> None:
    if not _MCP_AVAILABLE:
        raise SystemExit(
            "The 'mcp' package is required to run the MCP server. Install it with: pip install mcp"
        )
    log.info("starting pharma-intelligence MCP server on stdio")
    mcp.run()


if __name__ == "__main__":
    main()
