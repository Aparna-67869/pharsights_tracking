"""Source-document access + lineage for the FTF, PTE, PDE and Orange Book pages.

Every monitored dataset has one *current* source document. This module resolves
the document that backs a module, exposes the official download endpoint, and
records access in the audit trail so SOP reviews can show who opened what and
when — without the user ever having to visit the regulator's site.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError
from app.db.models import SourceDefinition, SourceDocument
from app.services import audit_service

# Module -> the source whose current document backs the module's dashboard.
MODULE_SOURCE: dict[str, str] = {
    "ftf": "fda_ftf_ppiv_pdf",
    "pte": "uspto_pte_applications",
    "pde": "fda_pde_approved_active_moiety",
    "orange_book": "fda_ob_data_files",
}

# Module -> the public landing page on the regulator's own site.
OFFICIAL_SITE: dict[str, str] = {
    "ftf": "https://www.fda.gov/drugs/abbreviated-new-drug-application-anda/"
    "patent-certifications-and-suitability-petitions",
    "pte": "https://www.uspto.gov/patents/laws/patent-term-extension/"
    "patent-terms-extended-under-35-usc-156",
    "pde": "https://www.fda.gov/drugs/development-resources/written-requests-issued",
    "orange_book": "https://www.fda.gov/drugs/drug-approvals-and-databases/"
    "approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
}

# Module -> the source whose *official* artifact the page's primary "view the
# regulator document" action should open. The FDA publishes the Paragraph IV
# list as both an Excel workbook (loaded as fact rows) and a PDF; the FTF page
# wants the PDF, so it is pinned here. Other modules fall back to the current
# document when no explicit override is set.
OFFICIAL_DOCUMENT_SOURCE: dict[str, str] = {
    "ftf": "fda_ftf_ppiv_pdf",
}

# Human label for the primary official-document button, per module.
OFFICIAL_DOCUMENT_LABEL: dict[str, str] = {
    "ftf": "View Official FDA Paragraph IV Certifications List",
    "pte": "View Official USPTO Patent Term Extension register",
    "pde": "View Official FDA Approved Active Moieties list",
    "orange_book": "View Official FDA Orange Book data files",
}

_KIND_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "zip": "application/zip",
}


def document_kind(document: SourceDocument) -> str:
    name = (document.filename or document.url or "").lower()
    content_type = (document.content_type or "").lower()
    for kind in ("xlsx", "xls", "pdf", "zip"):
        if name.endswith(f".{kind}"):
            return kind
    if "spreadsheet" in content_type or "excel" in content_type:
        return "xlsx"
    if "pdf" in content_type:
        return "pdf"
    if "zip" in content_type:
        return "zip"
    return "bin"


def display_filename(document: SourceDocument, kind: str) -> str:
    """FDA serves several lists from opaque ``/media/…/download`` URLs; present
    the name a user would recognise on the regulator's site."""
    name = document.filename or ""
    if name and name.lower() not in {"download", "attachment"} and "." in name:
        return name
    if kind != "bin":
        return f"{document.source_code}.{kind}"
    return document.source_code


def current_document(session: Session, module: str) -> SourceDocument:
    source_code = MODULE_SOURCE.get(module)
    if source_code is None:
        raise NotFoundError(f"no monitored source mapped for module {module!r}")
    document = session.scalars(
        select(SourceDocument)
        .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
        .order_by(desc(SourceDocument.fetched_at))
    ).first()
    if document is None:
        raise NotFoundError(f"no current document recorded for module {module!r}")
    return document


def official_document(session: Session, module: str) -> SourceDocument | None:
    """The document the module's primary "view the regulator document" action opens.

    For FTF this is the official FDA PDF (cross-validated against the loaded
    Excel), not the workbook that supplies the fact rows.
    """
    source_code = OFFICIAL_DOCUMENT_SOURCE.get(module, MODULE_SOURCE.get(module))
    if source_code is None:
        return None
    return session.scalars(
        select(SourceDocument)
        .where(SourceDocument.source_code == source_code, SourceDocument.is_current.is_(True))
        .order_by(desc(SourceDocument.fetched_at))
    ).first()


def _artifact_path(document: SourceDocument) -> Path:
    if not document.storage_path:
        raise NotFoundError("the source document is recorded but no artifact was stored")
    path = Path(document.storage_path)
    if not path.is_absolute():
        # storage_path is a store-relative key, and the local store root is
        # ``artifacts_dir`` — not its parent.
        path = settings.artifacts_dir / path
    if not path.exists():
        raise NotFoundError("the stored source document is no longer on disk")
    return path


def source_document_payload(session: Session, document: SourceDocument) -> dict[str, Any]:
    kind = document_kind(document)
    definition = session.scalars(
        select(SourceDefinition).where(SourceDefinition.code == document.source_code)
    ).first()
    return {
        "module": document.module,
        "source_code": document.source_code,
        "source_name": definition.name if definition else document.source_code,
        "version": document.version,
        "filename": display_filename(document, kind),
        "content_type": document.content_type or _KIND_CONTENT_TYPE.get(kind),
        "document_kind": kind,
        "byte_size": document.byte_size,
        "record_count": document.record_count,
        "source_record_count": document.source_record_count,
        "publication_date": document.publication_date.isoformat() if document.publication_date else None,
        "publication_label": document.publication_label,
        "fetched_at": document.fetched_at.isoformat() if document.fetched_at else None,
        "download_url": document.url,
        "official_site_url": OFFICIAL_SITE.get(document.module),
        "official_document_label": OFFICIAL_DOCUMENT_LABEL.get(document.module),
        "official_document_available": _official_available(session, document.module),
        "official_view_endpoint": f"/api/v1/sources/{document.module}/document/official/view",
        "official_download_endpoint": f"/api/v1/sources/{document.module}/document/official/download",
        "document_id": document.id,
        "content_hash": document.content_hash,
        "storage_backend": "azure_blob" if settings.azure_storage_connection_string else "local",
    }


def _official_available(session: Session, module: str) -> bool:
    return official_document_file_path(session, module) is not None


def module_source_meta(session: Session, module: str) -> dict[str, Any]:
    """The provenance block every module page renders under its header."""
    return source_document_payload(session, current_document(session, module))


def document_file_path(session: Session, module: str) -> tuple[SourceDocument, Path]:
    document = current_document(session, module)
    return document, _artifact_path(document)


def document_bytes(session: Session, module: str) -> tuple[SourceDocument, bytes]:
    """Read the current source artifact into memory for inline inspection."""
    document, path = document_file_path(session, module)
    return document, path.read_bytes()


def document_rows(session: Session, module: str) -> dict[str, Any]:
    """Return the current source artifact as a real, inline-viewable table.

    Only formats the platform actually ingests (xlsx/xls and delimited text)
    can be rendered as rows; binary PDFs and zips are reported as unsupported
    so the UI can offer the raw file instead of fabricating a table.
    """
    document, path = document_file_path(session, module)
    kind = document_kind(document)
    if kind in ("xlsx", "xls"):
        from app.parsers import excel as xl

        rows = xl.sheet_rows(path.read_bytes(), filename=document.filename or "")
        grid = [[_cell_text(cell) for cell in row] for row in rows]
    elif kind in ("csv", "txt", "tsv"):
        delimiter = "\t" if kind == "tsv" else ","
        text = path.read_text(encoding="utf-8", errors="replace")
        import csv
        import io

        grid = [[_cell_text(cell) for cell in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    else:
        return {
            "supported": False,
            "document_kind": kind,
            "filename": display_filename(document, kind),
            "message": "This document format cannot be rendered as a table; open the file instead.",
        }

    grid = [row for row in grid if any(str(cell).strip() for cell in row)]
    header = grid[0] if grid else []
    body = grid[1:] if grid else []
    return {
        "supported": True,
        "document_kind": kind,
        "filename": display_filename(document, kind),
        "header": header,
        "rows": body[:1000],
        "total_rows": len(body),
        "truncated": len(body) > 1000,
    }


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def official_document_file_path(session: Session, module: str) -> tuple[SourceDocument, Path] | None:
    """File path for the module's official regulator document, if archived."""
    document = official_document(session, module)
    if document is None or not document.storage_path:
        return None
    try:
        return document, _artifact_path(document)
    except NotFoundError:
        return None


def record_access(
    session: Session,
    *,
    module: str,
    action: str,
    actor: str | None,
) -> None:
    audit_service.record(
        session,
        actor=actor,
        action=action,
        resource_type="source_document",
        resource_id=module,
        detail={"module": module},
    )
