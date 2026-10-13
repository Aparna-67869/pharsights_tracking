"""Microsoft Teams delivery.

Posts an Adaptive Card to either a channel webhook (``TEAMS_WEBHOOK_URL``) or,
when a Microsoft Graph token and the user's Entra ID chat/conversation id are
available, directly to the signed-in user. The webhook path works with zero
extra configuration; the Graph path is what enables "send to Aparna's Teams
account" for a specific authenticated user.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"


@dataclass
class TeamsResult:
    status: str  # sent | skipped | failed
    target: str | None = None
    error: str | None = None


def build_card(alert: dict[str, Any]) -> dict[str, Any]:
    emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(
        str(alert.get("priority_label", "")), "⚪"
    )
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Medium",
                            "weight": "Bolder",
                            "wrap": True,
                            "text": f"{emoji} {alert.get('title', '')}",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Priority", "value": f"{alert.get('priority_label')} ({alert.get('priority_score')}/100)"},
                                {"title": "Module", "value": str(alert.get("module", "")).upper()},
                                {"title": "Drug", "value": str(alert.get("drug_name") or "—")},
                                {"title": "Sponsor", "value": str(alert.get("sponsor_name") or "—")},
                                {"title": "Patent", "value": str(alert.get("patent_number") or "—")},
                            ],
                        },
                        {"type": "TextBlock", "wrap": True, "text": alert.get("message", "")},
                    ],
                },
            }
        ],
    }


def send_teams(
    alert: dict[str, Any],
    *,
    user_email: str | None = None,
    graph_token: str | None = None,
) -> TeamsResult:
    """Deliver to a Teams channel webhook, or to a specific user via Graph."""
    card = build_card(alert)

    if user_email and graph_token:
        return _send_graph(user_email, card, graph_token)

    if settings.teams_webhook_url:
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(settings.teams_webhook_url, json=card)
                response.raise_for_status()
            return TeamsResult(status="sent", target="teams-webhook")
        except Exception as exc:
            log.warning("teams webhook delivery failed: %s", exc)
            return TeamsResult(status="failed", target="teams-webhook", error=str(exc)[:500])

    return TeamsResult(status="skipped", error="No Teams webhook and no Graph token")


def _send_graph(user_email: str, card: dict[str, Any], token: str) -> TeamsResult:
    """Create a 1:1 chat message to the user via Microsoft Graph."""
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        with httpx.Client(timeout=30) as client:
            chat = client.post(
                f"{GRAPH_ENDPOINT}/chats",
                headers=headers,
                json={
                    "chatType": "oneOnOne",
                    "members": [
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"{GRAPH_ENDPOINT}/users('{user_email}')",
                        }
                    ],
                },
            )
            chat.raise_for_status()
            chat_id = chat.json()["id"]
            message = client.post(
                f"{GRAPH_ENDPOINT}/chats/{chat_id}/messages",
                headers=headers,
                json={"body": {"contentType": "html", "content": _card_to_html(card)}},
            )
            message.raise_for_status()
        return TeamsResult(status="sent", target=user_email)
    except Exception as exc:
        log.warning("teams graph delivery failed for %s: %s", user_email, exc)
        return TeamsResult(status="failed", target=user_email, error=str(exc)[:500])


def _card_to_html(card: dict[str, Any]) -> str:
    body = card["attachments"][0]["content"]["body"]
    title = body[0]["text"]
    facts = body[1]["facts"]
    text = body[2]["text"]
    fact_rows = "".join(f"<li><b>{f['title']}:</b> {f['value']}</li>" for f in facts)
    return f"<h3>{title}</h3><ul>{fact_rows}</ul><p>{text}</p>"
