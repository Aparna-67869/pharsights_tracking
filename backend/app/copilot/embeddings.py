"""Embedding providers.

Default is a deterministic, dependency-free hashing embedder so semantic search
and RAG work offline. When Azure OpenAI (or OpenAI) is configured, the real
embedding deployment is used instead and the same vectors are stored.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder:
    name: str = "base"
    dimension: int = settings.embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashingEmbedder(Embedder):
    """Signed feature-hashing embedder with sublinear TF weighting.

    Deterministic across processes (no random seed), so vectors persisted by the
    pipeline remain valid for the API. Not a substitute for a trained model, but
    it gives meaningful lexical-semantic recall for exact and near-exact terms,
    which is what regulatory lookups mostly are.
    """

    name = "local-hashing"

    def __init__(self, dimension: int | None = None, ngrams: int = 2) -> None:
        self.dimension = dimension or settings.embedding_dim
        self.ngrams = ngrams

    def _tokens(self, text: str) -> list[str]:
        tokens = _TOKEN_RE.findall(text.casefold())
        features = list(tokens)
        for size in range(2, self.ngrams + 1):
            features.extend(
                "_".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)
            )
        return features

    def _bucket(self, token: str) -> tuple[int, float]:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dimension
        sign = 1.0 if (value >> 63) & 1 == 0 else -1.0
        return index, sign

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            tokens = self._tokens(text or "")
            if not tokens:
                vectors.append(vector)
                continue
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, count in counts.items():
                index, sign = self._bucket(token)
                vector[index] += sign * (1.0 + math.log(count))
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors


class OpenAIEmbedder(Embedder):
    """Azure OpenAI or OpenAI embeddings."""

    name = "azure-openai"

    def __init__(self) -> None:
        self.dimension = settings.embedding_dim
        if settings.azure_openai_endpoint and settings.azure_openai_api_key:
            self.provider = "azure"
            self._url = (
                f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
                f"{settings.azure_openai_embedding_deployment}/embeddings"
                f"?api-version={settings.azure_openai_api_version}"
            )
            self._headers = {
                "api-key": settings.azure_openai_api_key,
                "Content-Type": "application/json",
            }
        else:
            self.provider = "openai"
            self._url = f"{settings.openai_base_url.rstrip('/')}/embeddings"
            self._headers = {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            }

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"input": texts}
        if self.provider == "openai":
            payload["model"] = settings.azure_openai_embedding_deployment
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(self._url, headers=self._headers, json=payload)
            response.raise_for_status()
            data = response.json()
        vectors = [item["embedding"] for item in data["data"]]
        if vectors:
            self.dimension = len(vectors[0])
        return vectors


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is not None:
        return _embedder
    if settings.azure_openai_api_key and settings.azure_openai_endpoint:
        try:
            _embedder = OpenAIEmbedder()
            log.info("embedder: azure openai (%s)", settings.azure_openai_embedding_deployment)
            return _embedder
        except Exception as exc:  # pragma: no cover
            log.warning("azure openai embedder unavailable (%s); using local embedder", exc)
    if settings.openai_api_key:
        try:
            _embedder = OpenAIEmbedder()
            log.info("embedder: openai")
            return _embedder
        except Exception as exc:  # pragma: no cover
            log.warning("openai embedder unavailable (%s); using local embedder", exc)
    _embedder = HashingEmbedder()
    log.info("embedder: local hashing (dim=%d)", _embedder.dimension)
    return _embedder


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(length))) or 1.0
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(length))) or 1.0
    return dot / (norm_a * norm_b)
