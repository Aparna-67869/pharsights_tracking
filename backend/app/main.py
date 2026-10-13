"""FastAPI application factory.

Assembles the REST routers, the GraphQL endpoint, the WebSocket bridge, the
exception handlers, middleware (request logging, CORS, rate limiting, security
headers) and the OpenAPI documentation.
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import ws
from app.api.routers import (
    alerts as alerts_router,
)
from app.api.routers import (
    auth as auth_router,
)
from app.api.routers import (
    copilot as copilot_router,
)
from app.api.routers import (
    dashboard as dashboard_router,
)
from app.api.routers import (
    ftf as ftf_router,
)
from app.api.routers import (
    intelligence as intelligence_router,
)
from app.api.routers import (
    orange_book as ob_router,
)
from app.api.routers import (
    ops as ops_router,
)
from app.api.routers import (
    pde as pde_router,
)
from app.api.routers import (
    pte as pte_router,
)
from app.api.routers import (
    search as search_router,
)
from app.api.routers import (
    sources as sources_router,
)
from app.core.config import settings
from app.core.errors import PharmaError
from app.core.logging import configure_logging, get_logger
from app.db.session import create_all, reconcile_schema

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("starting %s (%s)", settings.app_name, settings.environment)

    if settings.environment in {"development", "test"}:
        # Dev convenience: ensure the schema exists. Production uses Alembic.
        create_all()
        reconcile_schema()

    # Automatic source monitoring: fetch, diff, analyse and alert on a cadence
    # with no user action. Runs only in the serving process, never under pytest.
    if settings.environment != "test":
        from app.services import scheduler
        from app.services.pipeline import reconcile_orphan_runs

        # Nothing can legitimately be mid-sweep this early, so any run still
        # marked "running" was orphaned by a previous process dying.
        reconcile_orphan_runs()
        scheduler.start()
    yield
    log.info("shutting down %s", settings.app_name)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attaches a request id and records latency."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = request_id
        response.headers["x-process-time-ms"] = f"{duration_ms:.1f}"
        if request.url.path.startswith(settings.api_prefix):
            log.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=()")
        if settings.environment == "production":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def _error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "Automated regulatory intelligence for FDA Paragraph IV certifications, "
            "USPTO patent term extensions, approved active moieties and the Orange Book. "
            "Collects, versions, diffs, analyses and alerts — with an AI copilot on top."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={"name": "Pharma Intelligence Platform"},
        openapi_tags=[
            {"name": "auth", "description": "Authentication and identity"},
            {"name": "first-to-file", "description": "FDA Paragraph IV certifications"},
            {"name": "patent-term-extension", "description": "USPTO patent term extensions"},
            {"name": "approved-active-moiety", "description": "FDA approved active moieties"},
            {"name": "orange-book", "description": "FDA Orange Book products, patents, exclusivity"},
            {"name": "intelligence", "description": "Changes, insights and audit trail"},
            {"name": "alerts", "description": "Real-time alert management"},
            {"name": "search", "description": "Global search and the 360-degree drug view"},
            {"name": "graph", "description": "Knowledge graph traversal"},
            {"name": "dashboard", "description": "Executive KPIs, charts and saved views"},
            {"name": "copilot", "description": "AI copilot and RAG"},
            {"name": "sources", "description": "Monitored source registry and collection history"},
            {"name": "pipeline", "description": "Pipeline orchestration"},
            {"name": "realtime", "description": "WebSocket event stream"},
            {"name": "system", "description": "Health and metadata"},
        ],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "x-process-time-ms"],
    )

    # ---- Exception handlers ----
    @app.exception_handler(PharmaError)
    async def platform_error_handler(request: Request, exc: PharmaError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(422, "validation_error", "Request validation failed", exc.errors())

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        message = str(exc) if settings.debug else "Internal server error"
        return _error_response(500, "internal_error", message)

    # ---- Routers ----
    prefix = settings.api_prefix
    app.include_router(auth_router.router, prefix=prefix)
    app.include_router(ftf_router.router, prefix=prefix)
    app.include_router(pte_router.router, prefix=prefix)
    app.include_router(pde_router.router, prefix=prefix)
    app.include_router(ob_router.router, prefix=prefix)
    app.include_router(ops_router.router, prefix=prefix)
    app.include_router(intelligence_router.router, prefix=prefix)
    app.include_router(alerts_router.router, prefix=prefix)
    app.include_router(search_router.router, prefix=prefix)
    app.include_router(dashboard_router.router, prefix=prefix)
    app.include_router(copilot_router.router, prefix=prefix)
    app.include_router(sources_router.router, prefix=prefix)
    app.include_router(sources_router.pipeline_router, prefix=prefix)
    app.include_router(ws.router)

    # ---- GraphQL ----
    try:
        from strawberry.fastapi import GraphQLRouter

        from app.api.graphql_schema import schema

        app.include_router(GraphQLRouter(schema), prefix="/graphql")
        log.info("graphql mounted at /graphql")
    except Exception as exc:  # pragma: no cover
        log.warning("graphql unavailable: %s", exc)

    # ---- System endpoints ----
    @app.get("/health", tags=["system"], summary="Liveness probe")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": settings.app_name, "environment": settings.environment}

    @app.get("/ready", tags=["system"], summary="Readiness probe")
    def ready() -> dict[str, Any]:
        from sqlalchemy import text

        from app.db.session import session_scope

        checks: dict[str, Any] = {}
        try:
            with session_scope() as session:
                session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"
        try:
            from app.core.cache import get_cache

            cache = get_cache()
            cache.set("__ready__", "1", ttl=5)
            checks["cache"] = "ok" if cache.get("__ready__") else "error"
        except Exception as exc:
            checks["cache"] = f"error: {exc}"
        status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return {"status": status, "checks": checks}

    @app.get(f"{prefix}/meta", tags=["system"], summary="Platform metadata")
    def meta() -> dict[str, Any]:
        from app.collectors.registry import ALL_SOURCES

        return {
            "name": settings.app_name,
            "version": "1.0.0",
            "environment": settings.environment,
            "modules": ["ftf", "pte", "pde", "orange_book", "patents", "copilot", "alerts"],
            "sources": [
                {
                    "code": s.code,
                    "name": s.name,
                    "module": s.module,
                    "url": s.url,
                    "cadence": s.cadence,
                }
                for s in ALL_SOURCES
            ],
            "llm_provider": settings.llm_provider,
            "vector_backend": settings.vector_backend,
        }

    return app


app = create_app()
