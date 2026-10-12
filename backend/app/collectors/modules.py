"""Collector implementations for each monitored module.

Each collector pairs a :class:`SourceSpec` with the parser for its document
kind. ``collect_and_parse`` returns both the artifact lineage and the
normalized records ready for the change-detection stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectedDocument
from app.collectors.registry import (
    ALL_SOURCES,
    FTF_SOURCES,
    ORANGE_BOOK_SOURCES,
    PDE_SOURCES,
    PTE_SOURCES,
    SOURCES_BY_CODE,
    SourceSpec,
)
from app.core.errors import ParserError
from app.core.logging import get_logger
from app.parsers import ftf as ftf_parser
from app.parsers import orange_book as ob_parser
from app.parsers import pde as pde_parser
from app.parsers import pte as pte_parser

log = get_logger(__name__)


@dataclass
class ParseResult:
    """Parsed records plus any dataset-level metadata (e.g. supplement edition)."""

    records: list[dict[str, Any]]
    metadata: dict[str, Any]


class ModuleCollector(BaseCollector):
    """A collector bound to one module's parsing strategy."""

    def parse(self, data: bytes, *, filename: str = "") -> ParseResult:
        raise NotImplementedError


class FtfCollector(ModuleCollector):
    def parse(self, data: bytes, *, filename: str = "") -> ParseResult:
        if self.source.document_kind == "pdf":
            records = ftf_parser.parse_ftf_pdf(data)
            text = data[:0]  # PDF text already consumed by the parser
        else:
            records = ftf_parser.parse_ftf_excel(data, filename=filename)
        return ParseResult(records=records, metadata={"certification_type": "Paragraph IV"})


class PteCollector(ModuleCollector):
    def parse(self, data: bytes, *, filename: str = "") -> ParseResult:
        if self.source.entity_type == "pte_certificate":
            return ParseResult(
                records=pte_parser.parse_pte_certificates(data, filename=filename), metadata={}
            )
        return ParseResult(
            records=pte_parser.parse_pte_applications(data, filename=filename), metadata={}
        )


class PdeCollector(ModuleCollector):
    def parse(self, data: bytes, *, filename: str = "") -> ParseResult:
        return ParseResult(
            records=pde_parser.parse_active_moieties(data, filename=filename), metadata={}
        )


class OrangeBookCollector(ModuleCollector):
    def parse(self, data: bytes, *, filename: str = "") -> ParseResult:
        if self.source.document_kind == "zip":
            members = ob_parser.extract_zip_members(data)
            products = ob_parser.parse_products(members.get("products.txt", b""))
            patents = ob_parser.parse_patents(members.get("patent.txt", b""))
            exclusivity = ob_parser.parse_exclusivity(members.get("exclusivity.txt", b""))
            return ParseResult(
                records=products,
                metadata={"patents": patents, "exclusivity": exclusivity, "members": list(members)},
            )
        if self.source.document_kind == "pdf":
            metadata = ob_parser.parse_supplement_metadata(data)
            return ParseResult(records=[], metadata=metadata)
        return ParseResult(records=[], metadata={})


COLLECTOR_CLASSES: dict[str, type[ModuleCollector]] = {
    "fda_ftf_ppiv_excel": FtfCollector,
    "fda_ftf_ppiv_pdf": FtfCollector,
    "uspto_pte_applications": PteCollector,
    "uspto_pte_certificates": PteCollector,
    "fda_pde_approved_active_moiety": PdeCollector,
    "fda_ob_cumulative_supplement": OrangeBookCollector,
    "fda_ob_data_files": OrangeBookCollector,
    "fda_ob_reference_listed_drugs": OrangeBookCollector,
}


def build_collector(source: SourceSpec) -> ModuleCollector:
    cls = COLLECTOR_CLASSES.get(source.code)
    if cls is None:
        raise ParserError(f"No collector registered for source {source.code}")
    return cls(source)


def collect_source(session: Session, source_code: str) -> tuple[CollectedDocument | None, ParseResult | None]:
    """Collect and parse a single source. Returns ``(None, None)`` when unchanged."""
    source = SOURCES_BY_CODE.get(source_code)
    if source is None:
        raise ParserError(f"Unknown source code: {source_code}")

    collector = build_collector(source)
    try:
        collected = collector.collect(session)
        if collected is None or not collected.is_new_version:
            return collected, None
        parsed = collector.parse(collected.data, filename=collected.document.filename)
        collected.document.record_count = len(parsed.records)
        collected.document.parse_status = "ok"
        session.flush()
        return collected, parsed
    except Exception as exc:
        log.exception("collect/parse failed for %s", source_code)
        if session.dirty:
            session.rollback()
        raise
    finally:
        collector.close()


def all_sources() -> tuple[SourceSpec, ...]:
    return ALL_SOURCES
