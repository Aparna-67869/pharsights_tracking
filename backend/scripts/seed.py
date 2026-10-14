"""Seed reference data: users, sponsors importance, and demo saved views.

Run with:  python -m scripts.seed
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.logging import get_logger
from app.core.security import Role, hash_password
from app.db.models import SavedView, User
from app.db.session import create_all, session_scope

log = get_logger(__name__)

DEFAULT_USERS = [
    ("pharsightspatent@gmail.com", "Pharsight Patent", "AdminPass!234", Role.ADMIN),
]

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
        for email, full_name, password, role in DEFAULT_USERS:
            existing = session.scalars(select(User).where(User.email == email)).first()
            if existing is None:
                session.add(
                    User(
                        email=email,
                        full_name=full_name,
                        hashed_password=hash_password(password),
                        role=role.value,
                        is_active=True,
                        preferences={},
                    )
                )
                print(f"  created user {email} ({role.value})")

        admin = session.scalars(select(User).where(User.email == DEFAULT_USERS[0][0])).first()
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
    print("Seed complete. Development credentials:")
    for email, _, password, role in DEFAULT_USERS:
        print(f"  {email:34s} {password:18s} ({role.value})")


if __name__ == "__main__":
    main()
