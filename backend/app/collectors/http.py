"""Resilient HTTP client used by every collector.

Features: retry with exponential backoff, polite rate limiting, conditional
requests (ETag / Last-Modified), browser-like headers, and an optional
Playwright fallback for JS-rendered pages.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.core.errors import CollectorError
from app.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": settings.http_user_agent,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf,application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


@dataclass
class FetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str = ""
    etag: str | None = None
    last_modified: str | None = None
    from_cache: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    @property
    def is_pdf(self) -> bool:
        return self.content[:5] == b"%PDF-" or "pdf" in self.content_type.lower()

    @property
    def is_zip(self) -> bool:
        return self.content[:2] == b"PK" and (
            "zip" in self.content_type.lower() or self.url.lower().endswith(".zip")
        )

    @property
    def is_excel(self) -> bool:
        lower = self.url.lower()
        return (
            self.content[:2] == b"PK"
            or self.content[:4] == b"\xd0\xcf\x11\xe0"
            or lower.endswith((".xlsx", ".xls"))
            or "spreadsheet" in self.content_type.lower()
            or "ms-excel" in self.content_type.lower()
        )


class HttpClient:
    """Synchronous HTTP client with retries and conditional GET support."""

    def __init__(self, *, timeout: int | None = None, user_agent: str | None = None) -> None:
        self.timeout = timeout or settings.http_timeout_seconds
        self._last_request_at = 0.0
        headers = dict(DEFAULT_HEADERS)
        if user_agent:
            headers["User-Agent"] = user_agent
        self._client = httpx.Client(
            headers=headers,
            timeout=self.timeout,
            follow_redirects=True,
            http2=False,
        )

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        wait = settings.collector_min_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> FetchResult:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        last_error: Exception | None = None
        for attempt in range(1, settings.http_max_retries + 1):
            self._throttle()
            try:
                response = self._client.get(url, headers=headers, params=params)
                self._last_request_at = time.time()

                if response.status_code == 304:
                    return FetchResult(
                        url=str(response.url),
                        status_code=304,
                        content=b"",
                        content_type=response.headers.get("content-type", ""),
                        etag=etag,
                        last_modified=last_modified,
                        from_cache=True,
                        headers=dict(response.headers),
                    )
                response.raise_for_status()
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    content=response.content,
                    content_type=response.headers.get("content-type", ""),
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                    headers=dict(response.headers),
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                # 4xx other than 429 are not worth retrying.
                if status < 500 and status != 429:
                    raise CollectorError(
                        f"HTTP {status} fetching {url}",
                        details={"url": url, "status": status},
                    ) from exc
                last_error = exc
            except Exception as exc:
                last_error = exc

            backoff = settings.http_backoff_seconds * (2 ** (attempt - 1))
            log.warning(
                "fetch attempt %d/%d failed for %s: %s (retry in %.1fs)",
                attempt,
                settings.http_max_retries,
                url,
                last_error,
                backoff,
            )
            if attempt < settings.http_max_retries:
                time.sleep(backoff)

        raise CollectorError(
            f"Failed to fetch {url} after {settings.http_max_retries} attempts",
            details={"url": url, "error": str(last_error)},
        )

    def get_html(self, url: str) -> FetchResult:
        return self.get(url)

    def resolve(self, base_url: str, href: str) -> str:
        return urljoin(base_url, href)

    def fetch_with_playwright(self, url: str, *, wait_selector: str | None = None) -> str:
        """JS-rendered fallback. Requires the optional ``playwright`` package."""
        try:
            from playwright.sync_api import sync_playwright  # optional dependency
        except ImportError as exc:  # pragma: no cover
            raise CollectorError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=settings.http_user_agent)
            page.goto(url, wait_until="networkidle", timeout=self.timeout * 1000)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=self.timeout * 1000)
            html = page.content()
            browser.close()
            return html


def parse_html(html: str) -> Any:
    """Parse HTML with lxml, falling back to the stdlib parser."""
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")
