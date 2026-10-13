"""Application-facing event bus.

Re-exports the transport-agnostic publish helpers from :mod:`app.core.events`
so domain services have a single import surface, and adds a small in-process
buffer used to power the WebSocket "recent events" replay.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.core.events import DomainEvent, Topics, publish_event  # noqa: F401
from app.core.logging import get_logger

log = get_logger(__name__)

_RECENT: deque[dict[str, Any]] = deque(maxlen=200)


def emit(topic: str, event_type: str, payload: dict[str, Any]) -> DomainEvent:
    event = publish_event(topic, event_type, payload)
    _RECENT.append(
        {
            "topic": event.topic,
            "event_type": event.event_type,
            "payload": event.payload,
            "event_id": event.event_id,
            "occurred_at": event.occurred_at,
        }
    )
    return event


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    return list(_RECENT)[-limit:][::-1]
