"""Domain event bus.

Kafka is the production transport; when ``KAFKA_BOOTSTRAP_SERVERS`` is unset the
bus degrades to a synchronous in-process dispatcher so the pipeline is fully
runnable in development and CI.

Topic naming: ``{prefix}.{domain}.{event}`` e.g. ``pharma.ftf.record_added``.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class DomainEvent:
    topic: str
    event_type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str = "pipeline"
    version: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: str) -> DomainEvent:
        return cls(**json.loads(raw))


class EventTransport(Protocol):
    def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, topic: str, handler: Callable[[DomainEvent], None]) -> None: ...


class InProcessBus:
    """Synchronous fan-out used when Kafka is not configured."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}
        self._lock = threading.RLock()
        self._history: list[DomainEvent] = []
        self._max_history = 5000

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
            handlers = list(self._handlers.get(event.topic, []))
            handlers += list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # pragma: no cover - handler isolation
                log.exception("event handler failed", extra={"topic": event.topic})

    def subscribe(self, topic: str, handler: Callable[[DomainEvent], None]) -> None:
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    def history(self, topic: str | None = None, limit: int = 100) -> list[DomainEvent]:
        with self._lock:
            items = self._history
            if topic:
                items = [e for e in items if e.topic == topic]
            return list(reversed(items[-limit:]))


class KafkaBus:
    """Thin Kafka producer/consumer wrapper (confluent-kafka or kafka-python)."""

    def __init__(self, bootstrap: str) -> None:
        try:
            from kafka import KafkaProducer  # type: ignore

            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap.split(","),
                value_serializer=lambda v: v.encode("utf-8"),
                acks="all",
                retries=5,
            )
        except Exception as exc:  # pragma: no cover
            log.warning("kafka unavailable (%s); falling back to in-process bus", exc)
            raise
        self._handlers: dict[str, list[Callable[[DomainEvent], None]]] = {}
        self._bootstrap = bootstrap

    def publish(self, event: DomainEvent) -> None:
        self._producer.send(event.topic, event.to_json())

    def subscribe(self, topic: str, handler: Callable[[DomainEvent], None]) -> None:
        from kafka import KafkaConsumer  # type: ignore

        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self._bootstrap.split(","),
            value_deserializer=lambda v: DomainEvent.from_json(v.decode("utf-8")),
            group_id=f"pharma-{topic}",
            auto_offset_reset="latest",
        )

        def _run() -> None:
            for message in consumer:
                try:
                    handler(message.value)
                except Exception:
                    log.exception("kafka handler failed", extra={"topic": topic})

        threading.Thread(target=_run, daemon=True, name=f"kafka-{topic}").start()


_bus: EventTransport | None = None


def get_bus() -> EventTransport:
    global _bus
    if _bus is None:
        if settings.kafka_bootstrap_servers:
            try:
                _bus = KafkaBus(settings.kafka_bootstrap_servers)
                log.info("event bus: kafka")
                return _bus
            except Exception:
                pass
        _bus = InProcessBus()
        log.info("event bus: in-process")
    return _bus


# ---- Topic constants -------------------------------------------------------

class Topics:
    FTF_ADDED = "pharma.ftf.record_added"
    FTF_UPDATED = "pharma.ftf.record_updated"
    FTF_REMOVED = "pharma.ftf.record_removed"
    PTE_APP_ADDED = "pharma.pte.application_added"
    PTE_CERT_ADDED = "pharma.pte.certificate_added"
    PTE_UPDATED = "pharma.pte.record_updated"
    PDE_ADDED = "pharma.pde.moiety_added"
    PDE_UPDATED = "pharma.pde.record_updated"
    OB_SUPPLEMENT = "pharma.orangebook.supplement_published"
    OB_CHANGED = "pharma.orangebook.product_changed"
    PATENT_CHANGED = "pharma.patent.changed"
    ALERT_CREATED = "pharma.alert.created"
    INSIGHT_CREATED = "pharma.insight.created"
    COLLECTION_RUN = "pharma.collection.run"
    PIPELINE_RUN = "pharma.pipeline.run"


def publish_event(topic: str, event_type: str, payload: dict[str, Any], source: str = "pipeline") -> DomainEvent:
    event = DomainEvent(topic=topic, event_type=event_type, payload=payload, source=source)
    get_bus().publish(event)
    return event
