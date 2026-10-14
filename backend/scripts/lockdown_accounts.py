"""Reduce the live database to the single authorized account.

The platform is a one-account deployment: only ``ALLOWED_LOGIN_EMAIL`` may sign
in. This reconciles an existing database that was seeded (or edited) before that
rule existed, so no stray account can authenticate and no foreign key dangles.

It never creates an account — the account is claimed on the sign-in page — so it
is safe to run against a fresh database.

Run with:  python -m scripts.lockdown_accounts
"""

from __future__ import annotations

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import Role
from app.db.models import (
    AlertSubscription,
    CopilotConversation,
    SavedView,
    User,
)
from app.db.session import create_all, session_scope

log = get_logger(__name__)


def main() -> None:
    create_all()
    allowed = settings.allowed_login_email.strip().casefold()

    with session_scope() as session:
        users = list(session.scalars(select(User)))
        keep = next((u for u in users if u.email == allowed), None)

        if keep is not None:
            keep.role = Role.ADMIN.value
            keep.is_active = True
            log.info("kept authorized account %s", allowed)

        removed = [u for u in users if u.email != allowed]
        if removed:
            removed_ids = [u.id for u in removed]
            # Reassign anything owned by the removed accounts so nothing dangles.
            session.execute(
                SavedView.__table__.update()
                .where(SavedView.owner_id.in_(removed_ids))
                .values(owner_id=keep.id if keep else None)
            )
            session.execute(
                AlertSubscription.__table__.update()
                .where(AlertSubscription.user_id.in_(removed_ids))
                .values(user_id=keep.id if keep else None)
            )
            session.execute(
                CopilotConversation.__table__.update()
                .where(CopilotConversation.user_id.in_(removed_ids))
                .values(user_id=keep.id if keep else None)
            )
            session.execute(delete(User).where(User.id.in_(removed_ids)))
            for user in removed:
                log.info("removed account %s (%s)", user.email, user.role)

        if keep is None:
            print(f"no account yet — create {allowed} on the sign-in page")
        else:
            print(f"authorized account: {keep.email} ({keep.role})")
        print(f"removed {len(removed)} other account(s)")


if __name__ == "__main__":
    main()
