"""
Answer generation and doc-summary generation both go through this
interface. The important design decision is `NullProvider`: with no API
key configured, the app doesn't error out or return empty responses --
summarizer.py and rag.py catch LLMUnavailable and fall back to an
extractive mode (signatures + docstrings + retrieved snippets, no
generated prose). That means `docker compose up` with zero configuration
still produces a working search-and-browse tool; add an API key and the
same endpoints start generating real answers, no restart-required code
path change.

Model default is claude-sonnet-5 -- current as of this build (Aug 2026);
Anthropic updates model strings over time, so this is read from
ANTHROPIC_MODEL and worth checking against
https://docs.claude.com/en/docs/about-claude/models before you deploy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMUnavailable(RuntimeError):
    """Raised when no LLM is configured, or the call fails. Callers should
    catch this and degrade gracefully rather than 500."""


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> str: ...


class NullProvider(LLMProvider):
    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        raise LLMUnavailable(
            "No LLM provider configured. Set ANTHROPIC_API_KEY (or OPENAI_API_KEY "
            "with LLM_PROVIDER=openai) to enable generated answers and summaries."
        )


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        import anthropic

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise LLMUnavailable(f"Anthropic API call failed: {exc}") from exc
        parts = [block.text for block in response.content if block.type == "text"]
        return "\n".join(parts).strip()


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import httpx

        self._model = model
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    def generate(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        import httpx

        try:
            resp = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"OpenAI API call failed: {exc}") from exc
        return resp.json()["choices"][0]["message"]["content"].strip()


_llm_cache: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _llm_cache
    if _llm_cache is not None:
        return _llm_cache

    from app.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        _llm_cache = AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        _llm_cache = OpenAIProvider(settings.openai_api_key, settings.openai_model)
    else:
        _llm_cache = NullProvider()
    return _llm_cache
