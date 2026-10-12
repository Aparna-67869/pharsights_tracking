"""Base collector: resolve the current document link, fetch it, version it.

The collector is responsible only for *acquisition and lineage*. Parsing and
change detection happen downstream so a parser bug never corrupts the stored
source artifact.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collectors.http import HttpClient, parse_html
from app.collectors.registry import SourceSpec
from app.collectors.storage import artifact_key, content_hash, get_store
from app.core.errors import CollectorError
from app.core.events import Topics, publish_event
from app.core.logging import get_logger
from app.core.text import parse_date_flexible
from app.db.base import utcnow
from app.db.models import CollectionRun, SourceDefinition, SourceDocument

log = get_logger(__name__)


@dataclass
class CollectedDocument:
    """Result of a collection attempt."""

    source: SourceSpec
    document: SourceDocument
    data: bytes
    is_new_version: bool
    publication_date: date | None
    publication_label: str | None
    resolved_url: str


class BaseCollector:
    """Resolves and fetches one monitored source document."""

    def __init__(self, source: SourceSpec, *, client: HttpClient | None = None) -> None:
        self.source = source
        self._client = client
        self._owns_client = client is None

    # -- HTTP plumbing ------------------------------------------------------

    @property
    def client(self) -> HttpClient:
        if self._client is None:
            self._client = HttpClient()
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> BaseCollector:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- Document URL resolution -------------------------------------------

    def resolve_document_url(self) -> tuple[str, str | None]:
        """Return ``(document_url, publication_label)``.

        Strategy is driven by the source spec's locator so a re-published
        document is picked up automatically. Falls back to the last known
        direct URL if the landing page cannot be parsed.
        """
        locator = self.source.locator or {}
        strategy = locator.get("strategy")

        if strategy in {"media_link", "href_contains"}:
            try:
                return self._resolve_from_landing_page(locator)
            except Exception as exc:
                log.warning("locator failed for %s (%s); using fallback", self.source.code, exc)
                if self.source.direct_url:
                    return self.source.direct_url, None
                raise

        if self.source.direct_url:
            return self.source.direct_url, None
        return self.source.url, None

    def _resolve_from_landing_page(self, locator: dict[str, Any]) -> tuple[str, str | None]:
        response = self.client.get(self.source.url)
        soup = parse_html(response.text)

        candidates: list[tuple[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "/media/" not in href and "download" not in href.lower() and not href.lower().endswith(
                (".pdf", ".xlsx", ".xls", ".zip")
            ):
                continue
            label = " ".join(anchor.get_text(" ", strip=True).split())
            title = anchor.get("title") or ""
            candidates.append((self.client.resolve(self.source.url, href), f"{label} {title}".strip()))

        if not candidates:
            raise CollectorError(f"No document links found on {self.source.url}")

        match_text = (locator.get("match_text") or "").casefold()
        media_ids = [str(m) for m in locator.get("media_ids", [])]
        href_contains = (locator.get("href_contains") or "").casefold()
        extension = (locator.get("extension") or "").casefold()

        def score(candidate: tuple[str, str]) -> int:
            url, label = candidate
            value = 0
            lowered = label.casefold()
            if match_text and match_text in lowered:
                value += 10
            if href_contains and href_contains in url.casefold():
                value += 20
            if any(f"/media/{mid}/" in url for mid in media_ids):
                value += 15
            if extension and url.casefold().split("?")[0].endswith(extension):
                value += 8
            return value

        ranked = sorted(candidates, key=score, reverse=True)
        best_url, best_label = ranked[0]
        if score((best_url, best_label)) <= 0:
            raise CollectorError(
                f"Could not identify the target document on {self.source.url}",
                details={"candidates": [u for u, _ in candidates[:10]]},
            )

        publication_label = None
        pattern = locator.get("publication_date_pattern")
        if pattern:
            import re

            for _, label in ranked[:5]:
                match = re.search(pattern, label, re.IGNORECASE)
                if match:
                    publication_label = match.group(1) if match.groups() else match.group(0)
                    break
        return best_url, publication_label

    # -- Collection --------------------------------------------------------

    def collect(self, session: Session) -> CollectedDocument | None:
        """Fetch the current document, storing a new version only when content changed."""
        started = time.time()
        run = CollectionRun(source_code=self.source.code, status="running")
        session.add(run)
        session.flush()

        try:
            resolved_url, publication_label = self.resolve_document_url()
            log.info("collecting %s from %s", self.source.code, resolved_url)

            previous = self._current_document(session)
            fetch = self.client.get(
                resolved_url,
                etag=previous.etag if previous else None,
                last_modified=previous.last_modified if previous else None,
            )

            if fetch.from_cache and previous is not None:
                run.status = "unchanged"
                run.document_id = previous.id
                run.new_version = False
                run.records_parsed = previous.record_count
                run.details = {"reason": "304 not modified"}
                self._finish(session, run, started)
                return CollectedDocument(
                    source=self.source,
                    document=previous,
                    data=b"",
                    is_new_version=False,
                    publication_date=previous.publication_date,
                    publication_label=previous.publication_label,
                    resolved_url=resolved_url,
                )

            digest = content_hash(fetch.content)
            if previous is not None and previous.content_hash == digest:
                run.status = "unchanged"
                run.document_id = previous.id
                run.records_parsed = previous.record_count
                previous.last_modified = fetch.last_modified or previous.last_modified
                previous.etag = fetch.etag or previous.etag
                run.details = {"reason": "identical content hash", "bytes": len(fetch.content)}
                self._finish(session, run, started)
                return CollectedDocument(
                    source=self.source,
                    document=previous,
                    data=fetch.content,
                    is_new_version=False,
                    publication_date=previous.publication_date,
                    publication_label=previous.publication_label,
                    resolved_url=resolved_url,
                )

            # New version: persist artifact and mark the prior version superseded.
            store = get_store()
            filename = resolved_url.split("?")[0].rsplit("/", 1)[-1] or self.source.document_kind
            key = artifact_key(self.source.module, self.source.code, filename, fetch.content)
            store.put(key, fetch.content)

            version = (previous.version + 1) if previous else 1
            if previous is not None:
                previous.is_current = False

            pub_date = parse_date_flexible(publication_label)
            document = SourceDocument(
                source_code=self.source.code,
                module=self.source.module,
                url=resolved_url,
                filename=filename,
                content_hash=digest,
                byte_size=len(fetch.content),
                content_type=fetch.content_type,
                storage_path=key,
                version=version,
                is_current=True,
                publication_date=pub_date,
                publication_label=publication_label,
                http_status=fetch.status_code,
                etag=fetch.etag,
                last_modified=fetch.last_modified,
                parse_status="pending",
                extra={"resolved_from": self.source.url},
            )
            session.add(document)
            session.flush()

            run.status = "success"
            run.document_id = document.id
            run.new_version = True
            run.details = {
                "version": version,
                "bytes": len(fetch.content),
                "publication_label": publication_label,
                "resolved_url": resolved_url,
            }
            self._finish(session, run, started)

            publish_event(
                Topics.COLLECTION_RUN,
                "new_version",
                {
                    "source_code": self.source.code,
                    "module": self.source.module,
                    "document_id": document.id,
                    "version": version,
                    "publication_date": str(pub_date) if pub_date else None,
                },
            )

            return CollectedDocument(
                source=self.source,
                document=document,
                data=fetch.content,
                is_new_version=True,
                publication_date=pub_date,
                publication_label=publication_label,
                resolved_url=resolved_url,
            )
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)[:2000]
            self._finish(session, run, started)
            log.exception("collection failed for %s", self.source.code)
            raise

    def _current_document(self, session: Session) -> SourceDocument | None:
        return session.scalars(
            select(SourceDocument)
            .where(SourceDocument.source_code == self.source.code, SourceDocument.is_current.is_(True))
            .order_by(SourceDocument.version.desc())
            .limit(1)
        ).first()

    def _finish(self, session: Session, run: CollectionRun, started: float) -> None:
        run.finished_at = utcnow()
        run.duration_ms = int((time.time() - started) * 1000)
        self._record_source_health(session, run)

    def _record_source_health(self, session: Session, run: CollectionRun) -> None:
        """Mirror the collection outcome onto the source registry row."""
        definition = session.scalars(
            select(SourceDefinition).where(SourceDefinition.code == self.source.code)
        ).first()
        if definition is None:
            return
        definition.last_checked_at = run.finished_at or utcnow()
        if run.status == "failed":
            definition.last_error = (run.error or "collection failed")[:2000]
        else:
            definition.last_success_at = definition.last_checked_at
            definition.last_error = None


def ensure_source_definition(session: Session, source: SourceSpec) -> SourceDefinition:
    """Upsert the ``source_definitions`` row for a spec."""
    definition = session.scalars(
        select(SourceDefinition).where(SourceDefinition.code == source.code)
    ).first()
    if definition is None:
        definition = SourceDefinition(
            code=source.code,
            name=source.name,
            module=source.module,
            url=source.url,
            document_kind=source.document_kind,
            cadence=source.cadence,
            description=source.description,
            locator=dict(source.locator),
            enabled=True,
        )
        session.add(definition)
    else:
        definition.name = source.name
        definition.url = source.url
        definition.module = source.module
        definition.document_kind = source.document_kind
        definition.cadence = source.cadence
        definition.description = source.description
        definition.locator = dict(source.locator)
    session.flush()
    return definition
