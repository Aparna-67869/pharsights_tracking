"""Authentication and user administration."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep, audit
from app.api.schemas import (
    RegisterRequest,
    RegisterResponse,
    TokenRequest,
    TokenResponse,
    UserProfile,
)
from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError, ConflictError
from app.core.security import Role, create_access_token, hash_password, verify_password
from app.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=201,
    summary="Create a self-service account",
)
def register(payload: RegisterRequest, session: SessionDep, request: Request) -> RegisterResponse:
    """Create a read-only account.

    Self-registration always grants the least-privilege ``viewer`` role, so a new
    account can read the modules but cannot run the pipeline, change alerts or use
    the copilot until an administrator elevates it. This keeps the open signup
    path from becoming a privilege-escalation route.
    """
    if not settings.allow_self_registration:
        raise AuthorizationError("Self-registration is disabled")

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
    audit(
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
    user = session.scalars(select(User).where(User.email == payload.username)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        audit(
            session,
            actor=payload.username,
            action="login_failed",
            resource_type="user",
            detail={"reason": "invalid credentials"},
            request=request,
        )
        session.commit()
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        raise AuthenticationError("Account is disabled")

    role = Role(user.role)
    token = create_access_token(user.email, role, extra={"name": user.full_name})
    user.last_login_at = datetime.now(UTC)
    audit(
        session,
        actor=user.email,
        action="login",
        resource_type="user",
        resource_id=user.id,
        request=request,
    )
    session.commit()
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
