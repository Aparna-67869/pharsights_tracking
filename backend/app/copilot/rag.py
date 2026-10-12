"""RAG retrieval over the indexed corpus.

Vector search is executed in-process over the ``document_chunks`` table. On
Postgres the embedding column can be swapped for ``pgvector`` and the same
interface used; the ``vector_backend`` setting documents that path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.copilot.embeddings import cosine_similarity, get_embedder
from app.core.logging import get_logger
from app.db.models import DocumentChunk

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_type: str
    source_id: str
    module: str | None
    entity_key: str | None
    title: str | None
    content: str
    score: float
    metadata: dict[str, Any]

    def citation(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "module": self.module,
            "entity_key": self.entity_key,
            "title": self.title,
            "score": round(self.score, 4),
        }

    def render(self) -> str:
        label = self.title or self.source_type
        return f"[{self.source_type}] {label} — {self.content.strip()}"


def retrieve(
    session: Session,
    query: str,
    *,
    top_k: int = 8,
    modules: list[str] | None = None,
    source_types: list[str] | None = None,
    min_score: float = 0.05,
) -> list[RetrievedChunk]:
    """Semantic search over the chunk corpus, with optional filters."""
    if not query or not query.strip():
        return []

    embedder = get_embedder()
    query_vector = embedder.embed_one(query)

    stmt = select(DocumentChunk)
    if modules:
        stmt = stmt.where(DocumentChunk.module.in_(modules))
    if source_types:
        stmt = stmt.where(DocumentChunk.source_type.in_(source_types))

    rows = list(session.scalars(stmt))
    if not rows:
        return []

    scored: list[RetrievedChunk] = []
    for row in rows:
        embedding = row.embedding or []
        score = cosine_similarity(query_vector, embedding)
        if score < min_score:
            continue
        scored.append(
            RetrievedChunk(
                chunk_id=row.id,
                source_type=row.source_type,
                source_id=row.source_id or "",
                module=row.module,
                entity_key=row.entity_key,
                title=row.title,
                content=row.content,
                score=score,
                metadata=row.metadata_json or {},
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def build_context_block(chunks: list[RetrievedChunk], max_chars: int = 8000) -> str:
    """Render retrieved chunks into the system-prompt context section."""
    parts: list[str] = []
    total = 0
    for chunk in chunks:
        rendered = chunk.render()
        if total + len(rendered) > max_chars:
            break
        parts.append(rendered)
        total += len(rendered)
    body = "\n---\n".join(parts)
    return f"[[CONTEXT]]\n{body}\n[[/CONTEXT]]"
