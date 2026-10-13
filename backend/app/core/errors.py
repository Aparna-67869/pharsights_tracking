"""Domain errors and the FastAPI exception handlers that render them."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)


class PharmaError(Exception):
    """Base class for all domain errors."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "pharma_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "details": self.details}


class NotFoundError(PharmaError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(PharmaError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class AuthenticationError(PharmaError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class AuthorizationError(PharmaError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class RateLimitError(PharmaError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class CollectorError(PharmaError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "collector_error"


class ServiceUnavailableError(PharmaError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service_unavailable"


class ParserError(PharmaError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "parser_error"


class ValidationError(PharmaError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PharmaError)
    async def _pharma_error(_: Request, exc: PharmaError) -> JSONResponse:
        if exc.status_code >= 500:
            log.exception("domain error: %s", exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "message": "Request payload failed validation",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled exception")
        # Never leak internals to clients.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred. The incident has been logged.",
                "details": {},
            },
        )
