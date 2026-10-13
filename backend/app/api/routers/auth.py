"""Authentication and user administration."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.deps import Principal, PrincipalDep, SessionDep, audit
from app.api.schemas import (
    RegisterRequest,
    RegisterResponse,
    TokenRequest,
    TokenResponse,
    UserOut,
    UserProfile,
    UserUpdate,
)
from app.core.config import settings
from app.core.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.security import Role, create_access_token, hash_password, verify_password
from app.db.models import User
from app.services import audit_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Provision an account (administrator only)",
)
def register(
    payload: RegisterRequest,
    session: SessionDep,
    request: Request,
    principal: PrincipalDep,
) -> RegisterResponse:
    """Provision a platform account.

    This is a company-internal platform with no public sign-up, so the endpoint
    requires an authenticated administrator. The new account gets the least
    privilege ``viewer`` role until an administrator elevates it.
    """
    if settings.restrict_login:
        raise AuthorizationError("Account creation is disabled on this deployment")
    if principal.role is not Role.ADMIN:
        raise AuthorizationError("Only an administrator can create accounts")

    email = payload.email.strip().casefold()
    existing = session.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        raise ConflictError("An account with that email already exists")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role=Role.VIEWER.value,
        is_active=True,
    )
    session.add(user)
    session.flush()
    audit_service.record(
        session,
        actor=email,
        action="register",
        resource_type="user",
        resource_id=user.id,
        detail={"role": user.role},
        request=request,
    )
    session.commit()
    return RegisterResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role)


@router.post("/token", response_model=TokenResponse, summary="Obtain a JWT access token")
def login(payload: TokenRequest, session: SessionDep, request: Request) -> TokenResponse:
    """Authenticate with email + password and receive a scoped access token."""
    try:
        user = session.scalars(select(User).where(User.email == payload.username)).first()
        authenticated = user is not None and verify_password(payload.password, user.hashed_password)
    except OperationalError:
        # SQLite raises "database is locked" when a concurrent write blocked the
        # read snapshot. Report it as transient (503) rather than a 500.
        session.rollback()
        raise ServiceUnavailableError("Database is busy, please retry") from None

    # Locked-down deployment: only the single authorized account may sign in.
    if settings.restrict_login and payload.username != settings.allowed_login_email.strip().casefold():
        audit_service.record_detached(
            actor=payload.username,
            action="login_blocked",
            resource_type="user",
            detail={"reason": "account not authorized on this deployment"},
            request=request,
        )
        raise AuthenticationError("Invalid credentials")

    if not authenticated:
        audit_service.record_detached(
            actor=payload.username,
            action="login_failed",
            resource_type="user",
            detail={"reason": "invalid credentials"},
            request=request,
        )
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        raise AuthenticationError("Account is disabled")

    role = Role(user.role)
    token = create_access_token(user.email, role, extra={"name": user.full_name})
    # Both writes are telemetry (last-login timestamp + audit row). They share
    # the account row with real state (password/role/active), so a lock here must
    # never fail the login: do them best-effort in a single retrying session
    # rather than on the request session, whose read snapshot cannot be upgraded.
    from app.db.session import resilient_write

    entry = audit_service.build_entry(
        actor=user.email,
        action="login",
        resource_type="user",
        resource_id=user.id,
        request=request,
    )

    def _record_login(s: Session) -> None:
        s.query(User).filter(User.id == user.id).update({"last_login_at": datetime.now(UTC)})
        s.add(entry)

    resilient_write(_record_login)
    return TokenResponse(
        access_token=token,
        expires_in=settings.access_token_ttl_minutes * 60,
        role=role.value,
        username=user.email,
    )


@router.get("/me", response_model=UserProfile, summary="Current user profile")
def me(principal: PrincipalDep) -> UserProfile:
    return UserProfile(
        username=principal.username,
        role=principal.role.value,
        permissions=principal.scopes,
    )


# ---- Administration: user management (administrator only) ------------------


def _require_admin(principal: Principal) -> None:
    if principal.role is not Role.ADMIN:
        raise AuthorizationError("Administrator role required")


@router.get("/users", response_model=list[UserOut], summary="List platform accounts (admin)")
def list_users(session: SessionDep, principal: PrincipalDep) -> list[User]:
    _require_admin(principal)
    return list(session.scalars(select(User).order_by(User.full_name, User.email)))


@router.patch("/users/{user_id}", response_model=UserOut, summary="Update an account (admin)")
def update_user(
    user_id: str,
    payload: UserUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> User:
    _require_admin(principal)
    user = session.get(User, user_id)
    if user is None:
        from app.core.errors import NotFoundError

        raise NotFoundError("User not found")
    if payload.role is not None:
        try:
            Role(payload.role)
        except ValueError:
            raise ValidationError(f"Unknown role {payload.role!r}") from None
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    audit(
        session,
        actor=principal.username,
        action="update_user",
        resource_type="user",
        resource_id=user.id,
        detail=payload.model_dump(exclude_unset=True),
        request=request,
    )
    session.commit()
    return user
