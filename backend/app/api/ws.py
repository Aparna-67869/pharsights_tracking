"""WebSocket endpoints for real-time dashboard updates.

The platform publishes domain events on the in-process bus (or Kafka when
configured). This bridge forwards them to connected clients so the dashboard
updates the moment a change, insight or alert is created.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import DomainEvent, get_bus
from app.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["realtime"])

# Topics the dashboard subscribes to.
FORWARDED_TOPICS = [
    "pharma.ftf.record_added",
    "pharma.ftf.record_updated",
    "pharma.ftf.record_removed",
    "pharma.pte.application_added",
    "pharma.pte.certificate_added",
    "pharma.pte.record_updated",
    "pharma.pde.moiety_added",
    "pharma.pde.record_updated",
    "pharma.orangebook.supplement_published",
    "pharma.orangebook.product_changed",
    "pharma.patent.changed",
    "pharma.alert.created",
    "pharma.insight.created",
    "pharma.pipeline.run",
]


class ConnectionManager:
    """Tracks live WebSocket clients and broadcasts events to them."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribed = False

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            self._loop = asyncio.get_running_loop()
            if self._queue is None:
                self._queue = asyncio.Queue(maxsize=2000)
            if not self._subscribed:
                bus = get_bus()
                for topic in FORWARDED_TOPICS:
                    bus.subscribe(topic, self._on_event)
                self._subscribed = True
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._drain())
        log.info("websocket client connected (%d live)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            if not self._connections and self._task is not None:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
                self._task = None
        log.info("websocket client disconnected (%d live)", len(self._connections))

    def _on_event(self, event: DomainEvent) -> None:
        """Called synchronously from the (possibly non-async) publisher thread."""
        if self._queue is None or self._loop is None:
            return
        message = {"topic": event.topic, "event_type": event.event_type, "payload": event.payload}
        try:
            self._loop.call_soon_threadsafe(self._enqueue, message)
        except RuntimeError:
            pass

    def _enqueue(self, message: dict[str, Any]) -> None:
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            log.warning("websocket queue full; dropping event %s", message.get("topic"))

    async def _drain(self) -> None:
        assert self._queue is not None
        while True:
            message = await self._queue.get()
            await self.broadcast(message)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._connections:
            return
        text = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for connection in list(self._connections):
            try:
                await connection.send_text(text)
            except Exception:
                dead.append(connection)
        for connection in dead:
            await self.disconnect(connection)


manager = ConnectionManager()


@router.websocket("/ws/events")
async def events_socket(websocket: WebSocket) -> None:
    """Stream domain events (changes, insights, alerts, pipeline status)."""
    await manager.connect(websocket)
    try:
        await websocket.send_text(
            json.dumps({"topic": "system.connected", "payload": {"status": "subscribed"}})
        )
        while True:
            # Keep the connection open; ignore inbound messages beyond pings.
            raw = await websocket.receive_text()
            if raw.strip().lower() in {"ping", '"ping"'}:
                await websocket.send_text(json.dumps({"topic": "system.pong", "payload": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        log.debug("websocket error", exc_info=True)
    finally:
        await manager.disconnect(websocket)
