"""FastAPI dependencies: DB session, authentication, RBAC, rate limiting, audit."""

from __future__ import annotations

import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError, RateLimitError
from app.core.security import Role, assert_scope, decode_token, verify_password
from app.db.models import AuditLog, User
from app.db.session import get_session as _get_session

bearer_scheme = HTTPBearer(auto_error=False)


def get_session() -> Generator[Session, None, None]:
    yield from _get_session()


SessionDep = Annotated[Session, Depends(get_session)]


@dataclass
class Principal:
    username: str
    role: Role
    scopes: list[str]
    user_id: str | None = None

    def require(self, scope: str) -> None:
        assert_scope(self.scopes, scope)


def _principal_from_token(token: str, session: Session) -> Principal:
    payload = decode_token(token)
    if payload.get("typ") != "access":
        raise AuthenticationError("Not an access token")
    username = payload.get("sub")
    if not username:
        raise AuthenticationError("Token has no subject")
    role = Role(payload.get("role", Role.VIEWER.value))
    scopes = list(payload.get("scopes") or [])
    user = session.query(User).filter(User.email == username).first()
    if user is not None and not user.is_active:
        raise AuthenticationError("User account is disabled")
    return Principal(
        username=username,
        role=role,
        scopes=scopes,
        user_id=user.id if user else None,
    )


def get_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")
    return _principal_from_token(credentials.credentials, session)


def get_optional_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        return _principal_from_token(credentials.credentials, session)
    except Exception:
        return None


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require_scope(scope: str):
    """Dependency factory enforcing a required scope."""

    def _dependency(principal: PrincipalDep) -> Principal:
        principal.require(scope)
        return principal

    return _dependency


# ---- Rate limiting --------------------------------------------------------

_RATE_WINDOW_SECONDS = 60


def rate_limit(
    request: Request,
    session: SessionDep,
    principal: Annotated[Principal | None, Depends(get_optional_principal)] = None,
) -> None:
    """Fixed-window per-identity rate limit, backed by the configured cache."""
    identity = principal.username if principal else (request.client.host if request.client else "anonymous")
    key = f"ratelimit:{identity}:{int(time.time() // _RATE_WINDOW_SECONDS)}"
    try:
        from app.core.cache import get_cache

        cache = get_cache()
        count = cache.incr(key, ttl=_RATE_WINDOW_SECONDS)
    except Exception:
        return
    if count is not None and count > settings.rate_limit_per_minute:
        raise RateLimitError(
            "Rate limit exceeded",
            details={"limit": settings.rate_limit_per_minute, "window_seconds": _RATE_WINDOW_SECONDS},
        )


def audit(
    session: Session,
    *,
    actor: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Write an immutable audit log entry."""
    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    session.add(entry)
    session.flush()
    return entry
