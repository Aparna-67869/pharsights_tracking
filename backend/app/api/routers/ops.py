"""Enterprise operations endpoints: audit trail, opportunities, comparisons,
source-document access and per-user alert subscriptions."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import PrincipalDep, SessionDep
from app.api.schemas import (
    AlertSubscriptionIn,
    AlertSubscriptionOut,
    AuditLogEntryOut,
)
from app.core.errors import NotFoundError
from app.db.models import AlertSubscription
from app.services import (
    audit_service,
    comparison_service,
    document_actions,
    opportunity_engine,
)

router = APIRouter(tags=["operations"])

_MODULES = ("ftf", "pte", "pde", "orange_book")


@router.get("/sources/{module}/document", summary="Current source document metadata for a module")
def module_document(module: str, session: SessionDep, principal: PrincipalDep) -> dict:
    """Everything the module header needs: source name, file name, version,
    publication date, download date, last processed date and both links."""
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    meta = document_actions.module_source_meta(session, module)
    processed = audit_service.last_processed_at(session, module)
    meta["last_processed_at"] = processed
    meta["view_url"] = f"/api/v1/sources/{module}/document/view"
    meta["download_endpoint"] = f"/api/v1/sources/{module}/document/download"
    return meta


@router.get("/sources/{module}/document/view", summary="View the current source document inline")
def module_document_view(module: str, session: SessionDep, principal: PrincipalDep) -> FileResponse:
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    document, path = document_actions.document_file_path(session, module)
    kind = document_actions.document_kind(document)
    document_actions.record_access(session, module=module, action="view_source", actor=principal.username)
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document_actions.display_filename(document, kind),
        content_disposition_type="inline",
    )


@router.get("/sources/{module}/document/download", summary="Download the current source document")
def module_document_download(module: str, session: SessionDep, principal: PrincipalDep) -> FileResponse:
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    document, path = document_actions.document_file_path(session, module)
    kind = document_actions.document_kind(document)
    document_actions.record_access(session, module=module, action="download_source", actor=principal.username)
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document_actions.display_filename(document, kind),
        content_disposition_type="attachment",
    )


@router.get(
    "/sources/{module}/document/official/view",
    summary="View the official regulator document for a module inline",
)
def module_official_document_view(module: str, session: SessionDep, principal: PrincipalDep) -> FileResponse:
    """Open the platform-archived copy of the regulator's own document.

    FTF maps to the official FDA Paragraph IV PDF; other modules map to their
    current source artifact. Opening it never leaves the platform, so the SOP's
    "view the regulator document" action works even behind a firewalled desktop.
    """
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    resolved = document_actions.official_document_file_path(session, module)
    if resolved is None:
        raise NotFoundError("no official document is archived for this module")
    document, path = resolved
    kind = document_actions.document_kind(document)
    document_actions.record_access(
        session, module=module, action="view_official_source", actor=principal.username
    )
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document_actions.display_filename(document, kind),
        content_disposition_type="inline",
    )


@router.get(
    "/sources/{module}/document/official/download",
    summary="Download the official regulator document for a module",
)
def module_official_document_download(
    module: str, session: SessionDep, principal: PrincipalDep
) -> FileResponse:
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    resolved = document_actions.official_document_file_path(session, module)
    if resolved is None:
        raise NotFoundError("no official document is archived for this module")
    document, path = resolved
    kind = document_actions.document_kind(document)
    document_actions.record_access(
        session, module=module, action="download_official_source", actor=principal.username
    )
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document_actions.display_filename(document, kind),
        content_disposition_type="attachment",
    )


@router.get("/audit", response_model=list[AuditLogEntryOut], summary="Recent audit trail")
def list_audit(
    session: SessionDep,
    principal: PrincipalDep,
    limit: int = Query(50, ge=1, le=500),
    actor: str | None = None,
) -> list[dict]:
    return audit_service.recent(session, limit=limit, actor=actor)


@router.get("/opportunities", summary="Generic-opportunity watchlist")
def opportunities(session: SessionDep, limit: int = Query(25, ge=1, le=200)) -> dict:
    return opportunity_engine.opportunity_summary(session)


@router.get("/delivery-channels", summary="Configured alert delivery channels")
def delivery_channels(principal: PrincipalDep) -> dict:
    """Report which notification channels are actually wired up server-side.

    The dashboard channel is always available; email, Teams and Slack are
    enabled per deployment via SMTP / webhook settings. The authenticated
    identity is the email target, so the UI can show exactly where mail goes.
    """
    from app.alerts.channels import all_channels

    return {
        "identity_email": principal.username,
        "channels": [{"name": c.name, "configured": c.configured()} for c in all_channels()],
    }


@router.post("/delivery-channels/test", summary="Send a test notification to the signed-in user")
def test_delivery(principal: PrincipalDep) -> dict:
    """Dispatch a test alert over every configured channel.

    Proves email/Teams delivery end-to-end without waiting for a real source
    change. Records each attempt in the notification log like a live alert.
    """
    from app.alerts.channels import all_channels

    alert = {
        "id": None,
        "title": "Test notification from Pharma Intelligence",
        "message": "This is a delivery test sent from the Administration page.",
        "module": "platform",
        "event_type": "test_notification",
        "priority_label": "low",
        "priority_score": 10,
        "drug_name": None,
        "sponsor_name": None,
        "patent_number": None,
        "recipient_email": principal.username,
    }
    results = []
    for channel in all_channels():
        if not channel.configured():
            results.append({"channel": channel.name, "status": "skipped", "error": "not configured"})
            continue
        result = channel.send(alert)
        results.append(
            {
                "channel": result.channel,
                "status": result.status,
                "recipient": result.recipient,
                "error": result.error,
            }
        )
    return {"sent_to": principal.username, "results": results}


@router.get("/comparison/documents/{before_id}/{after_id}", summary="Diff two source document versions")
def compare_documents(before_id: str, after_id: str, session: SessionDep) -> dict:
    return comparison_service.diff_between_documents(session, before_id, after_id)


@router.get("/comparison/{module}", summary="Previous vs current version for a module")
def compare_module(
    module: str,
    session: SessionDep,
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    if module not in _MODULES:
        raise NotFoundError(f"unknown module {module!r}")
    return comparison_service.module_comparison(session, module, limit=limit)


# ---- Alert subscriptions (per authenticated user) ----


@router.get("/subscriptions", response_model=list[AlertSubscriptionOut], summary="My alert subscriptions")
def list_subscriptions(session: SessionDep, principal: PrincipalDep) -> list[AlertSubscription]:
    return list(
        session.scalars(
            select(AlertSubscription)
            .where(AlertSubscription.user_email == principal.username)
            .order_by(AlertSubscription.created_at.desc())
        )
    )


@router.post(
    "/subscriptions",
    response_model=AlertSubscriptionOut,
    status_code=201,
    summary="Create an alert subscription",
)
def create_subscription(
    payload: AlertSubscriptionIn,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> AlertSubscription:
    subscription = AlertSubscription(
        user_id=principal.user_id or principal.username,
        user_email=principal.username,
        name=payload.name,
        modules=payload.modules,
        sponsors=payload.sponsors,
        drugs=payload.drugs,
        patents=payload.patents,
        therapy_areas=payload.therapy_areas,
        min_priority=payload.min_priority,
        channels=payload.channels,
        is_active=payload.is_active,
    )
    session.add(subscription)
    session.flush()
    audit_service.record(
        session,
        actor=principal.username,
        action="create_subscription",
        resource_type="alert_subscription",
        resource_id=subscription.id,
        detail={"modules": payload.modules},
        request=request,
    )
    session.commit()
    return subscription


@router.delete("/subscriptions/{subscription_id}", summary="Delete an alert subscription")
def delete_subscription(
    subscription_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> dict:
    subscription = session.get(AlertSubscription, subscription_id)
    if subscription is None or subscription.user_email != principal.username:
        raise NotFoundError("Subscription not found")
    session.delete(subscription)
    audit_service.record(
        session,
        actor=principal.username,
        action="delete_subscription",
        resource_type="alert_subscription",
        resource_id=subscription_id,
        request=request,
    )
    session.commit()
    return {"deleted": True}
