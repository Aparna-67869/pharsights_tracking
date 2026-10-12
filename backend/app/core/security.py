"""Authentication primitives: password hashing, JWT, RBAC roles and scopes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError

try:
    import bcrypt as _bcrypt
except Exception:  # pragma: no cover
    _bcrypt = None  # type: ignore[assignment]


class Role(StrEnum):
    """Enterprise roles. Scopes are derived from the role."""

    ADMIN = "admin"
    ANALYST = "analyst"
    REGULATORY_AFFAIRS = "regulatory_affairs"
    IP_COUNSEL = "ip_counsel"
    EXECUTIVE = "executive"
    VIEWER = "viewer"


ROLE_SCOPES: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.ANALYST: {
        "read:*",
        "write:views",
        "write:alerts",
        "run:pipeline",
        "use:copilot",
        "export:data",
    },
    Role.REGULATORY_AFFAIRS: {
        "read:*",
        "write:alerts",
        "write:views",
        "use:copilot",
        "export:data",
    },
    Role.IP_COUNSEL: {
        "read:*",
        "write:alerts",
        "use:copilot",
        "export:data",
        "write:patent_notes",
    },
    Role.EXECUTIVE: {"read:*", "use:copilot", "export:data"},
    Role.VIEWER: {"read:data"},
}


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt.

    bcrypt truncates at 72 bytes; we pre-hash longer inputs with SHA-256 so the
    full password contributes and the 72-byte limit is never a surprise.
    """
    if _bcrypt is None:  # pragma: no cover
        raise RuntimeError("bcrypt is required for password hashing")
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        import hashlib

        raw = hashlib.sha256(raw).hexdigest().encode("ascii")
    return _bcrypt.hashpw(raw, _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if _bcrypt is None or not hashed:  # pragma: no cover
        return False
    raw = plain.encode("utf-8")
    if len(raw) > 72:
        import hashlib

        raw = hashlib.sha256(raw).hexdigest().encode("ascii")
    try:
        return _bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except Exception:
        return False


def scopes_for_role(role: Role) -> list[str]:
    return sorted(ROLE_SCOPES.get(role, set()))


def create_access_token(
    subject: str,
    role: Role,
    *,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    ttl = expires_minutes or settings.access_token_ttl_minutes
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "scopes": scopes_for_role(role),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, role: Role) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.refresh_token_ttl_days)).timestamp()),
        "jti": str(uuid.uuid4()),
        "typ": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token", details={"reason": str(exc)}) from exc


def has_scope(granted: list[str], required: str) -> bool:
    if "*" in granted or required in granted:
        return True
    namespace = required.split(":", 1)[0]
    return f"{namespace}:*" in granted


def assert_scope(granted: list[str], required: str) -> None:
    if not has_scope(granted, required):
        raise AuthorizationError(
            "Insufficient permissions for this operation",
            details={"required_scope": required},
        )
