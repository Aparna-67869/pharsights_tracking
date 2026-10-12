"""LLM client.

Uses Azure OpenAI when configured, then OpenAI, then falls back to a
deterministic offline responder so the copilot always returns a useful,
grounded answer even with no model available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None


class LLMClient:
    provider = "offline"
    model = "offline-deterministic"

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        return self.provider != "offline"


class AzureOpenAIClient(LLMClient):
    provider = "azure_openai"

    def __init__(self) -> None:
        self.model = settings.azure_openai_chat_deployment
        self._url = (
            f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
            f"{settings.azure_openai_chat_deployment}/chat/completions"
            f"?api-version={settings.azure_openai_api_version}"
        )
        self._headers = {
            "api-key": settings.azure_openai_api_key or "",
            "Content-Type": "application/json",
        }

    def complete(self, messages, *, temperature=0.1, max_tokens=1200) -> LLMResponse:
        payload = {
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(self._url, headers=self._headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=self.model,
            provider=self.provider,
            usage=data.get("usage"),
        )


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self) -> None:
        self.model = settings.azure_openai_chat_deployment or "gpt-4o-mini"
        self._url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    def complete(self, messages, *, temperature=0.1, max_tokens=1200) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(self._url, headers=self._headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=self.model,
            provider=self.provider,
            usage=data.get("usage"),
        )


class OfflineClient(LLMClient):
    """Composes a grounded answer from retrieved context, with no model call.

    The copilot is a retrieval-first system: this responder turns the retrieved
    documents into a structured, cited answer, which is a correct (if less
    fluent) response when no LLM is configured.
    """

    provider = "offline"
    model = "offline-deterministic"

    def complete(self, messages, *, temperature=0.1, max_tokens=1200) -> LLMResponse:
        system = next((m.content for m in messages if m.role == "system"), "")
        context = ""
        question = ""
        for message in messages:
            if message.role == "user":
                question = message.content
            if message.role == "system" and "CONTEXT" in message.content:
                context = message.content

        # The retrieval layer embeds the context in the system prompt between
        # markers so the offline responder can present it verbatim with citations.
        blocks = []
        if "[[CONTEXT]]" in system:
            body = system.split("[[CONTEXT]]", 1)[1]
            body = body.split("[[/CONTEXT]]", 1)[0]
            for entry in body.split("\n---\n"):
                entry = entry.strip()
                if entry:
                    blocks.append(entry)

        if not blocks:
            return LLMResponse(
                content=(
                    "I could not find matching records for that question in the platform "
                    "knowledge base. Try naming a drug, patent number, NDA/ANDA number, "
                    "sponsor or active moiety."
                ),
                model=self.model,
                provider=self.provider,
            )

        lines = [f"Based on {len(blocks)} matching record(s) in the platform:", ""]
        for block in blocks[:6]:
            lines.append(f"• {block}")
            lines.append("")
        lines.append(
            "This answer was assembled directly from the stored regulatory records. "
            "Configure an LLM provider for a narrative synthesis."
        )
        return LLMResponse(content="\n".join(lines), model=self.model, provider=self.provider)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is not None:
        return _client

    preference = settings.llm_provider
    if preference in {"auto", "azure_openai"} and settings.azure_openai_api_key and settings.azure_openai_endpoint:
        try:
            _client = AzureOpenAIClient()
            log.info("llm: azure openai (%s)", _client.model)
            return _client
        except Exception as exc:  # pragma: no cover
            log.warning("azure openai unavailable (%s)", exc)
    if preference in {"auto", "openai"} and settings.openai_api_key:
        try:
            _client = OpenAIClient()
            log.info("llm: openai (%s)", _client.model)
            return _client
        except Exception as exc:  # pragma: no cover
            log.warning("openai unavailable (%s)", exc)

    _client = OfflineClient()
    log.info("llm: offline deterministic responder")
    return _client


def extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
    return None
