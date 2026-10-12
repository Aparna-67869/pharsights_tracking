"""Registry of monitored regulatory sources.

The ``url`` values and locator strategies below were derived by inspecting the
live pages referenced in the SOP ("HYPERLINKS FOR the PTE, PDE, and FTF
Documents"). Each source is resolved dynamically at collection time so a
re-published document is picked up without a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODULE_FTF = "ftf"
MODULE_PTE = "pte"
MODULE_PDE = "pde"
MODULE_ORANGE_BOOK = "orange_book"


@dataclass(frozen=True)
class SourceSpec:
    code: str
    name: str
    module: str
    url: str
    document_kind: str  # pdf | xlsx | xls | zip | html
    cadence: str = "daily"
    description: str = ""
    # How the collector resolves the current document link from the landing page.
    locator: dict[str, Any] = field(default_factory=dict)
    # Direct document URL when the source is not discovered via a landing page.
    direct_url: str | None = None
    entity_type: str = "record"


# --- FTF: FDA Paragraph IV Certifications List ------------------------------
# Landing page hosts two links titled
# "Paragraph IV Patent Certifications (PPIV) as of <date>": an Excel workbook
# and a PDF. Both carry the publication date in the link text.

FTF_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        code="fda_ftf_ppiv_excel",
        name="FDA Paragraph IV Certifications List (Excel)",
        module=MODULE_FTF,
        url="https://www.fda.gov/drugs/abbreviated-new-drug-application-anda/"
        "patent-certifications-and-suitability-petitions",
        document_kind="xlsx",
        cadence="daily",
        entity_type="ftf_record",
        description="New Paragraph IV certifications, machine-readable workbook.",
        locator={
            "strategy": "media_link",
            "match_text": "paragraph iv patent certifications",
            "extension": ".xlsx",
            "media_ids": ["194880"],
            "publication_date_pattern": r"as of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        },
    ),
    SourceSpec(
        code="fda_ftf_ppiv_pdf",
        name="FDA Paragraph IV Certifications List (PDF)",
        module=MODULE_FTF,
        url="https://www.fda.gov/drugs/abbreviated-new-drug-application-anda/"
        "patent-certifications-and-suitability-petitions",
        document_kind="pdf",
        cadence="daily",
        entity_type="ftf_record",
        description="Same list published as PDF; used for cross-validation.",
        locator={
            "strategy": "media_link",
            "match_text": "paragraph iv patent certifications",
            "extension": ".pdf",
            "media_ids": ["166048"],
            "publication_date_pattern": r"as of\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        },
    ),
)

# --- PTE: USPTO patent term extension lists ---------------------------------
# Both lists live on one page as direct file links.

PTE_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        code="uspto_pte_applications",
        name="USPTO PTE Applications (last five years)",
        module=MODULE_PTE,
        url="https://www.uspto.gov/patents/laws/patent-term-extension/"
        "patent-terms-extended-under-35-usc-156",
        document_kind="xlsx",
        cadence="daily",
        entity_type="pte_application",
        description="Applications for patent term extension filed in the last five years.",
        locator={
            "strategy": "href_contains",
            "href_contains": "pte_past5years",
            "publication_date_pattern": r"updated through\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        },
        direct_url="https://www.uspto.gov/sites/default/files/documents/pte_past5years.xlsx",
    ),
    SourceSpec(
        code="uspto_pte_certificates",
        name="USPTO PTE Certificates Issued",
        module=MODULE_PTE,
        url="https://www.uspto.gov/patents/laws/patent-term-extension/"
        "patent-terms-extended-under-35-usc-156",
        document_kind="xls",
        cadence="daily",
        entity_type="pte_certificate",
        description="Patents for which a patent term extension certificate was issued.",
        locator={
            "strategy": "href_contains",
            "href_contains": "pte_certs",
            "publication_date_pattern": r"updated through\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        },
        direct_url="https://www.uspto.gov/sites/default/files/documents/pte_certs.xls",
    ),
)

# --- PDE: FDA Approved Active Moiety ---------------------------------------

PDE_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        code="fda_pde_approved_active_moiety",
        name="FDA Approved Active Moiety List",
        module=MODULE_PDE,
        url="https://www.fda.gov/drugs/development-resources/written-requests-issued",
        document_kind="xlsx",
        cadence="daily",
        entity_type="active_moiety",
        description="Approved active moieties, with the update date shown beside the link.",
        locator={
            "strategy": "media_link",
            "match_text": "approved active moiety",
            "media_ids": ["193712"],
            "publication_date_pattern": r"\(([^)]*(?:19|20)\d{2}[^)]*)\)",
        },
    ),
)

# --- Orange Book ------------------------------------------------------------

ORANGE_BOOK_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        code="fda_ob_cumulative_supplement",
        name="Orange Book Current Cumulative Supplement",
        module=MODULE_ORANGE_BOOK,
        url="https://www.fda.gov/drugs/drug-approvals-and-databases/"
        "approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
        document_kind="pdf",
        cadence="monthly",
        entity_type="orange_book_supplement",
        description="Monthly cumulative supplement; supplement number and month at the top.",
        locator={
            "strategy": "media_link",
            "match_text": "current cumulative supplement",
            "media_ids": ["72973"],
        },
    ),
    SourceSpec(
        code="fda_ob_data_files",
        name="Orange Book Data Files (products, patent, exclusivity)",
        module=MODULE_ORANGE_BOOK,
        url="https://www.fda.gov/drugs/drug-approvals-and-databases/"
        "approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
        document_kind="zip",
        cadence="monthly",
        entity_type="orange_book_product",
        description="Full Orange Book dataset: products.txt, patent.txt, exclusivity.txt.",
        locator={
            "strategy": "media_link",
            "match_text": "orange book data files",
            "media_ids": ["76860"],
        },
    ),
    SourceSpec(
        code="fda_ob_reference_listed_drugs",
        name="Orange Book Reference Listed Drugs by ANDA Reference Standard",
        module=MODULE_ORANGE_BOOK,
        url="https://www.fda.gov/drugs/drug-approvals-and-databases/"
        "approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
        document_kind="pdf",
        cadence="monthly",
        entity_type="orange_book_product",
        description="RLD list used to resolve ANDA reference standards.",
        locator={
            "strategy": "media_link",
            "match_text": "reference listed drugs by anda",
            "media_ids": ["103879"],
        },
    ),
)

ALL_SOURCES: tuple[SourceSpec, ...] = (
    *FTF_SOURCES,
    *PTE_SOURCES,
    *PDE_SOURCES,
    *ORANGE_BOOK_SOURCES,
)

SOURCES_BY_CODE: dict[str, SourceSpec] = {s.code: s for s in ALL_SOURCES}
SOURCES_BY_MODULE: dict[str, tuple[SourceSpec, ...]] = {
    MODULE_FTF: FTF_SOURCES,
    MODULE_PTE: PTE_SOURCES,
    MODULE_PDE: PDE_SOURCES,
    MODULE_ORANGE_BOOK: ORANGE_BOOK_SOURCES,
}

# Planned future sources (documented, not yet enabled).
FUTURE_SOURCES: tuple[dict[str, str], ...] = (
    {"code": "clinicaltrials_api", "name": "ClinicalTrials.gov API v2", "module": "clinical_trials"},
    {"code": "pubmed_eutils", "name": "PubMed E-utilities", "module": "literature"},
    {"code": "uspto_bulk", "name": "USPTO Bulk Data (PatentsView)", "module": "patents"},
    {"code": "espacenet_ops", "name": "Espacenet OPS", "module": "patents"},
    {"code": "wipo_patentscope", "name": "WIPO PATENTSCOPE", "module": "patents"},
    {"code": "ema_medicines", "name": "EMA Medicines", "module": "global_approvals"},
    {"code": "dailymed", "name": "DailyMed SPL", "module": "labeling"},
)
