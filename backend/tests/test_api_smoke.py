"""API surface smoke tests.

These exercise the real FastAPI app (no mocks): health, authentication, the
scoped-protected executive endpoints, and the copilot's grounding path. They are
deliberately shallow on data volume — their job is to prove routing, auth and
serialisation hold together after a change.
"""

from __future__ import annotations


def _token(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/token", json={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}


def test_protected_endpoint_requires_a_token(client):
    response = client.get("/api/v1/dashboard/kpis")
    assert response.status_code in {401, 403}


def test_login_and_read_dashboard_kpis(client):
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get(
        "/api/v1/dashboard/kpis", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The KPI strip contract the dashboard depends on.
    assert isinstance(body["kpis"], dict)
    assert isinstance(body["alerts"], dict)


def test_sources_endpoint_exposes_health_fields(client):
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/sources", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    sources = response.json()
    assert isinstance(sources, list)
    if sources:
        # These are the columns the Sources page renders; their absence was the
        # regression this suite exists to prevent.
        assert "last_checked_at" in sources[0]
        assert "last_success_at" in sources[0]
        assert "last_error" in sources[0]


def test_wrong_password_is_rejected(client):
    response = client.post(
        "/api/v1/auth/token",
        json={"username": "tester@pharma-intel.local", "password": "not-the-password"},
    )
    assert response.status_code in {400, 401}


def test_viewer_role_cannot_trigger_pipeline(client):
    """RBAC: a read-only viewer must not be able to start a pipeline run."""
    token = _token(client, "viewer@pharma-intel.local", "ViewerPass!234")
    response = client.post(
        "/api/v1/pipeline/run", headers={"Authorization": f"Bearer {token}"}, json={}
    )
    assert response.status_code in {401, 403}


def test_opportunity_engine_returns_watchlist(client):
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/opportunities", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "total" in body and "by_band" in body and "top" in body


def test_audit_trail_records_logins(client):
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    entries = response.json()
    assert isinstance(entries, list)
    if entries:
        assert {"actor", "action", "resource_type"} <= set(entries[0].keys())


def test_alert_subscription_lifecycle(client):
    """Create -> list -> delete a subscription scoped to the authenticated user."""
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/subscriptions",
        headers=headers,
        json={
            "name": "Oncology FTF",
            "modules": ["ftf"],
            "therapy_areas": ["oncology"],
            "min_priority": 60,
            "channels": ["dashboard", "email", "teams"],
        },
    )
    assert created.status_code == 201, created.text
    subscription = created.json()
    assert subscription["user_email"] == "tester@pharma-intel.local"
    assert subscription["channels"] == ["dashboard", "email", "teams"]

    listed = client.get("/api/v1/subscriptions", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == subscription["id"] for item in listed.json())

    deleted = client.delete(f"/api/v1/subscriptions/{subscription['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_viewer_role_can_read_every_module(client):
    """A read-only viewer must reach the module endpoints, not get 'insufficient
    permissions' on them. Regression: the viewer role held only ``read:public``
    while every module required ``read:data``, so every module page 403'd."""
    token = _token(client, "viewer@pharma-intel.local", "ViewerPass!234")
    headers = {"Authorization": f"Bearer {token}"}
    for path in (
        "/api/v1/ftf/records",
        "/api/v1/ftf/summary",
        "/api/v1/pte/applications",
        "/api/v1/pte/certificates",
        "/api/v1/pde/moieties",
        "/api/v1/orange-book/products",
        "/api/v1/dashboard/kpis",
        "/api/v1/changes",
        "/api/v1/alerts",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 200, f"{path} -> {response.status_code}: {response.text}"


def test_viewer_role_cannot_use_copilot(client):
    """The copilot is an entitlement, not a read — viewers must not reach it."""
    token = _token(client, "viewer@pharma-intel.local", "ViewerPass!234")
    response = client.post(
        "/api/v1/copilot/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "hello"},
    )
    assert response.status_code in {401, 403}


def test_signup_creates_least_privilege_account(client):
    """Self-registration must create a working, read-only (viewer) account."""
    email = "newcomer@pharma-intel.local"
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "New Comer", "email": email, "password": "NewComerPass!234"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "viewer"

    # The new account can immediately log in and read a module.
    token = _token(client, email, "NewComerPass!234")
    ok = client.get("/api/v1/ftf/records", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200, ok.text

    # ...but stays out of the privileged copilot/entitlement surface.
    gated = client.post(
        "/api/v1/copilot/ask",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "hello"},
    )
    assert gated.status_code in {401, 403}


def test_signup_rejects_duplicate_email(client):
    """Registering an email that already exists must conflict, not silently succeed."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Tester Again",
            "email": "tester@pharma-intel.local",
            "password": "TestPass!234",
        },
    )
    assert response.status_code == 409


def test_signup_rejects_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Shorty", "email": "shorty@pharma-intel.local", "password": "abc"},
    )
    assert response.status_code == 422
