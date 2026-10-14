"""Seed reference data: sponsors importance and demo saved views.

Run with:  python -m scripts.seed

The deployment's account is created on the sign-in page by claiming
``ALLOWED_LOGIN_EMAIL``, so this script no longer plants a default-password
account. Set ``SEED_ADMIN_PASSWORD`` to have it create the account here instead
(useful for non-interactive bootstrap).
"""

from __future__ import annotations

import os

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import Role, hash_password
from app.db.models import SavedView, User
from app.db.session import create_all, session_scope

log = get_logger(__name__)

DEFAULT_VIEWS = [
    (
        "High-priority Paragraph IV filings",
        "ftf",
        {"status": "eligible", "expiring_before": "+24m", "min_score": 70},
        "New PIV filings with 180-day exclusivity eligibility and near-term patent expiry.",
    ),
    (
        "PTE extensions over 3 years",
        "pte",
        {"min_extension_days": 1095},
        "Granted term extensions longer than three years.",
    ),
    (
        "Oncology active moieties",
        "pde",
        {"therapy_area": "Oncology"},
        "Approved active moieties in oncology.",
    ),
    (
        "Orange Book generic-entry watchlist",
        "orange_book",
        {"patent_expiry_within_months": 36},
        "Products whose listed patents expire within three years.",
    ),
]


def main() -> None:
    create_all()
    with session_scope() as session:
        admin = session.scalars(
            select(User).where(User.email == settings.allowed_login_email.strip().casefold())
        ).first()

        # Only create the account when a password is supplied explicitly; the
        # normal path is the sign-in page, so nothing ships with a known default.
        password = os.environ.get("SEED_ADMIN_PASSWORD")
        if admin is None and password:
            admin = User(
                email=settings.allowed_login_email.strip().casefold(),
                full_name="Pharsight Patent",
                hashed_password=hash_password(password),
                role=Role.ADMIN.value,
                is_active=True,
                preferences={},
            )
            session.add(admin)
            session.flush()
            print(f"  created user {admin.email} ({admin.role})")

        for name, module, filters, description in DEFAULT_VIEWS:
            exists = session.scalars(
                select(SavedView).where(SavedView.name == name, SavedView.module == module)
            ).first()
            if exists is None:
                session.add(
                    SavedView(
                        owner_id=admin.id if admin else None,
                        name=name,
                        module=module,
                        filters=filters,
                        is_shared=True,
                        description=description,
                    )
                )
                print(f"  created saved view {name!r}")

    print()
    print("Seed complete.")
    if admin is None:
        print(f"  create the account on the sign-in page as {settings.allowed_login_email}")


if __name__ == "__main__":
    main()
