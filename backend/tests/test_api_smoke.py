"""API surface smoke tests.

These exercise the real FastAPI app (no mocks): health, authentication, the
scoped-protected executive endpoints, and the copilot's grounding path. They are
deliberately shallow on data volume — their job is to prove routing, auth and
serialisation hold together after a change.
"""

from __future__ import annotations


def _token(client, email: str, password: str, expect: int = 200) -> str:
    response = client.post("/api/v1/auth/token", json={"username": email, "password": password})
    assert response.status_code == expect, response.text
    return response.json().get("access_token", "") if expect == 200 else ""


def _admin_headers(client) -> dict[str, str]:
    """Provisioning is administrator-only, so sign-up tests act as an admin."""
    return {"Authorization": f"Bearer {_token(client, 'tester@pharma-intel.local', 'TestPass!234')}"}


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


def test_changes_export_route_is_not_shadowed_by_the_id_route(client):
    """``/changes/export`` must resolve to the export handler, not ``{change_id}``.

    Registering the dynamic ``/changes/{change_id}`` first used to swallow the
    literal path, so the Changes page's Export button hit a 404.
    """
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/changes/export", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")


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
    """An admin can provision a least-privilege (viewer) account."""
    email = "newcomer@pharma-intel.local"
    response = client.post(
        "/api/v1/auth/register",
        headers=_admin_headers(client),
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
        headers=_admin_headers(client),
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
        headers=_admin_headers(client),
        json={"full_name": "Shorty", "email": "shorty@pharma-intel.local", "password": "abc"},
    )
    assert response.status_code == 422


def test_restricted_login_blocks_other_accounts(client, monkeypatch):
    """With the lock-down on, only the one authorized account may sign in."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "restrict_login", True)
    monkeypatch.setattr(settings, "allowed_login_email", "tester@pharma-intel.local")

    # A valid seeded account that is not the authorized one is refused.
    blocked = client.post(
        "/api/v1/auth/token",
        json={"username": "viewer@pharma-intel.local", "password": "ViewerPass!234"},
    )
    assert blocked.status_code == 401, blocked.text

    # The authorized account, however cased or padded, still works.
    ok = client.post(
        "/api/v1/auth/token",
        json={"username": "  Tester@Pharma-Intel.Local ", "password": "TestPass!234"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["username"] == "tester@pharma-intel.local"


def test_restricted_login_disables_account_creation(client, monkeypatch):
    """With the lock-down on, even an administrator cannot create accounts."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "restrict_login", True)
    monkeypatch.setattr(settings, "allowed_login_email", "tester@pharma-intel.local")
    response = client.post(
        "/api/v1/auth/register",
        headers=_admin_headers(client),
        json={
            "full_name": "Should Not Exist",
            "email": "nope@pharma-intel.local",
            "password": "NopePass!234",
        },
    )
    assert response.status_code == 403, response.text



def test_ftf_records_default_to_published_order(client):
    """The default sort must follow the FDA document, not an alphabetical sort.

    Seeded non-alphabetically on purpose: ``Abacavir Sulfate`` (ordinal 0)
    precedes ``Abacavir`` (ordinal 1), while an A–Z sort would reverse them.
    """
    from app.db.models import FtfRecord
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.add_all(
            [
                FtfRecord(
                    source_code="fda_ftf_ppiv_pdf", source_key="k0", content_hash="h0",
                    source_ordinal=0, drug_name="Zzfirst", status="active",
                ),
                FtfRecord(
                    source_code="fda_ftf_ppiv_pdf", source_key="k1", content_hash="h1",
                    source_ordinal=1, drug_name="Aa_second", status="active",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    try:
        token = _token(client, "tester@pharma-intel.local", "TestPass!234")
        headers = {"Authorization": f"Bearer {token}"}

        default = client.get("/api/v1/ftf/records?page_size=5", headers=headers).json()
        assert [r["drug_name"] for r in default["items"]][:2] == ["Zzfirst", "Aa_second"]
        assert default["items"][0]["source_ordinal"] == 0

        alpha = client.get("/api/v1/ftf/records?sort=drug&page_size=5", headers=headers).json()
        assert [r["drug_name"] for r in alpha["items"]][:2] == ["Aa_second", "Zzfirst"]
    finally:
        db = SessionLocal()
        try:
            db.query(FtfRecord).filter(FtfRecord.source_key.in_(["k0", "k1"])).delete(
                synchronize_session=False
            )
            db.commit()
        finally:
            db.close()



def test_alert_summary_returns_the_keys_the_ui_reads(client):
    """The Alerts KPIs and the sidebar badge read these exact keys.

    Regression: ``alert_summary`` once returned only ``open_total``/``by_priority``,
    so every KPI card and the badge silently rendered zero.
    """
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/alerts/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("open", "critical", "high", "medium", "low", "total", "by_module"):
        assert key in body, f"alert summary is missing {key!r}: {body}"


def test_activity_today_reports_real_run_shape(client):
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    response = client.get("/api/v1/activity/today", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "sweeps" in body and "runs" in body["sweeps"]
    assert {"material", "baseline"} <= set(body["changes"])
    assert "created" in body["alerts"] and "open" in body["alerts"]
    assert isinstance(body["items"], list)


def test_module_document_content_never_fabricates_a_table(client):
    """``/sources/{module}/document/content`` returns real rows or says so.

    It must either give real parsed rows, or ``supported: false`` so the UI opens
    the raw file. It must never 500 on a format it cannot tabulate.
    """
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    headers = {"Authorization": f"Bearer {token}"}
    for module in ("ftf", "pte", "pde", "orange_book"):
        response = client.get(f"/api/v1/sources/{module}/document/content", headers=headers)
        assert response.status_code in {200, 404}, f"{module}: {response.status_code} {response.text}"
        if response.status_code != 200:
            continue
        body = response.json()
        assert "supported" in body
        if body["supported"]:
            assert isinstance(body.get("header"), list)
            assert isinstance(body.get("rows"), list)



def test_block_additional_accounts_rejects_other_emails(client, monkeypatch):
    """With the single-account lock-down on, only the allowed address is accepted."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "restrict_login", False)
    monkeypatch.setattr(settings, "block_additional_accounts", True)
    monkeypatch.setattr(settings, "allowed_login_email", "tester@pharma-intel.local")

    # The permitted address may be provisioned...
    allowed = client.post(
        "/api/v1/auth/register",
        headers=_admin_headers(client),
        json={
            "full_name": "Tester Again",
            "email": "tester@pharma-intel.local",
            "password": "TestPass!234",
        },
    )
    # ...but it already exists here, which is still a conflict, not an authorization error.
    assert allowed.status_code in {201, 409}, allowed.text

    # Any other address is refused outright.
    blocked = client.post(
        "/api/v1/auth/register",
        headers=_admin_headers(client),
        json={"full_name": "Someone Else", "email": "intruder@example.com", "password": "IntruderPass!234"},
    )
    assert blocked.status_code in {401, 403}, blocked.text


def test_block_additional_accounts_protects_the_single_account(client, monkeypatch):
    """The one permitted account cannot be deactivated when the lock-down is on."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "block_additional_accounts", True)
    monkeypatch.setattr(settings, "allowed_login_email", "viewer@pharma-intel.local")

    users = client.get("/api/v1/auth/users", headers=_admin_headers(client)).json()
    viewer = next(u for u in users if u["email"] == "viewer@pharma-intel.local")
    response = client.patch(
        f"/api/v1/auth/users/{viewer['id']}",
        headers=_admin_headers(client),
        json={"is_active": False},
    )
    assert response.status_code in {401, 403}, response.text


def test_profile_exposes_account_capability(client, monkeypatch):
    """/auth/me tells the UI whether further accounts may be created."""
    from app.core.config import settings

    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(settings, "block_additional_accounts", True)
    monkeypatch.setattr(settings, "allowed_login_email", "pharsightspatent@gmail.com")
    locked = client.get("/api/v1/auth/me", headers=headers).json()
    assert locked["can_create_accounts"] is False
    assert locked["allowed_login_email"] == "pharsightspatent@gmail.com"

    monkeypatch.setattr(settings, "block_additional_accounts", False)
    open_profile = client.get("/api/v1/auth/me", headers=headers).json()
    assert open_profile["can_create_accounts"] is True
    assert open_profile["allowed_login_email"] is None


def test_change_password_rotates_the_credential(client):
    """The signed-in account can rotate its password after confirming the old one."""
    token = _token(client, "tester@pharma-intel.local", "TestPass!234")
    headers = {"Authorization": f"Bearer {token}"}

    wrong = client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": "not-the-password", "new_password": "RotatedPass!234"},
    )
    assert wrong.status_code == 401, wrong.text

    ok = client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": "TestPass!234", "new_password": "RotatedPass!234"},
    )
    assert ok.status_code == 200, ok.text

    # The old password no longer works; the new one does.
    _token(client, "tester@pharma-intel.local", "TestPass!234", expect=401)
    _token(client, "tester@pharma-intel.local", "RotatedPass!234")

    # Restore the seeded credential so the fixture teardown and other tests agree.
    client.post(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": "RotatedPass!234", "new_password": "TestPass!234"},
    )

