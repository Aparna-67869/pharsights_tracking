"""Shared pytest fixtures.

Every test runs against a throwaway SQLite file so nothing touches the real
``data/pharma.db``. The DATABASE_URL override happens before any application
module is imported, because the engine is built at import time in
``app.db.session``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP_DIR = Path(tempfile.mkdtemp(prefix="pharma-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR / 'test.db'}"
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("VECTOR_BACKEND", "numpy")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("ALERT_MIN_PRIORITY_TO_NOTIFY", "40")

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import Role, hash_password
from app.db.base import Base
from app.db.models import User  # importing this module registers every table
from app.db.session import SessionLocal, engine, reconcile_schema


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    Base.metadata.create_all(bind=engine)
    reconcile_schema()


@pytest.fixture()
def session():
    """A session wrapped in a transaction that is rolled back after the test."""
    connection = engine.connect()
    transaction = connection.begin()
    db = SessionLocal(bind=connection)
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


def _create_user(email: str, full_name: str, password: str, role: Role) -> None:
    """Seed a user through the app's own session factory and commit it.

    API tests cannot share the transactional ``session`` fixture: the app opens
    its own connections, and SQLite will deadlock against an uncommitted writer.
    """
    db = SessionLocal()
    try:
        existing = db.scalars(select(User).where(User.email == email)).first()
        if existing is None:
            db.add(
                User(
                    email=email,
                    full_name=full_name,
                    hashed_password=hash_password(password),
                    role=role.value,
                    is_active=True,
                )
            )
        db.commit()
    finally:
        db.close()


def _delete_users(*emails: str) -> None:
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email.in_(emails)))
        db.commit()
    finally:
        db.close()


TEST_USERS = {
    "tester@pharma-intel.local": ("Test Analyst", "TestPass!234", Role.ADMIN),
    "viewer@pharma-intel.local": ("Viewer", "ViewerPass!234", Role.VIEWER),
}


@pytest.fixture()
def client() -> TestClient:
    for email, (name, password, role) in TEST_USERS.items():
        _create_user(email, name, password, role)

    from app.main import app

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        _delete_users(*TEST_USERS)
