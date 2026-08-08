"""
Generates a one-sentence, plain-language summary per function/class, used
to (a) enrich what gets embedded for semantic search -- a docstring-free
function called `hp` is much easier to find once its summary says "computes
a SHA-256 password hash" -- and (b) show in the UI next to the signature.

Batches many symbols into one LLM call asking for a JSON array back, rather
than one call per symbol: for a repo with a few hundred undocumented
functions that's the difference between ~1 API call and ~300. If the LLM
is unavailable or returns something we can't parse, every symbol in the
batch falls back to an extractive summary (signature + existing docstring,
no generation) -- indexing never fails because summarization did.
"""
from __future__ import annotations

import json

from app.core.extractor import Symbol
from app.core.llm import LLMProvider, LLMUnavailable

BATCH_SIZE = 20
MAX_SNIPPET_CHARS = 600

SYSTEM_PROMPT = (
    "You are a precise code documentation assistant. You will be given short "
    "code snippets from a real codebase. For each one, write exactly one "
    "sentence (max 25 words) in plain language describing what it does, for "
    "an engineer who has never seen this codebase. Do not restate the name. "
    "Respond with ONLY a JSON array like "
    '[{"id": "abc123", "summary": "..."}], no other text, no markdown fences.'
)


def _extractive_summary(symbol: Symbol) -> str:
    if symbol.docstring:
        first_sentence = symbol.docstring.strip().split(". ")[0].rstrip(".") + "."
        return first_sentence
    return f"{symbol.kind.capitalize()} `{symbol.name}` ({symbol.signature})."


def _needs_ai_summary(symbol: Symbol) -> bool:
    return symbol.kind in ("function", "method", "class") and (
        not symbol.docstring or len(symbol.docstring) < 12
    )


def _parse_llm_json(raw: str) -> dict[str, str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("expected a JSON array")
    return {
        item["id"]: str(item["summary"]).strip()
        for item in parsed
        if isinstance(item, dict) and "id" in item and "summary" in item
    }


def summarize_symbols(
    llm: LLMProvider, symbols: list[Symbol], snippets: dict[str, str], max_symbols: int = 300
) -> dict[str, str]:
    """Returns symbol_id -> summary for every symbol passed in (AI-generated
    where possible, extractive otherwise). `max_symbols` bounds LLM spend on
    very large repos -- symbols beyond the cap just get the extractive
    version; there's no quality cliff, only a documentation-richness one."""
    summaries: dict[str, str] = {}
    ai_eligible = [s for s in symbols if _needs_ai_summary(s)][:max_symbols]
    ai_eligible_ids = {s.id for s in ai_eligible}

    for i in range(0, len(ai_eligible), BATCH_SIZE):
        batch = ai_eligible[i : i + BATCH_SIZE]
        items = [
            {"id": s.id, "signature": s.signature, "code": snippets.get(s.id, "")[:MAX_SNIPPET_CHARS]}
            for s in batch
        ]
        prompt = "Summarize each of these:\n\n" + json.dumps(items, indent=2)
        try:
            raw = llm.generate(system=SYSTEM_PROMPT, prompt=prompt, max_tokens=60 * len(batch))
            summaries.update(_parse_llm_json(raw))
        except (LLMUnavailable, json.JSONDecodeError, ValueError, KeyError):
            pass  # this batch's symbols fall through to the extractive summary below

    for s in symbols:
        if s.id not in summaries:
            summaries[s.id] = _extractive_summary(s)
    return summaries
