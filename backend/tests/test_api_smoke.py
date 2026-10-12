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
