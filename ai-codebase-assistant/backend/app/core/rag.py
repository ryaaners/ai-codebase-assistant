"""
The "ask a question about this codebase" pipeline:

  question --embed--> vector search (top-k relevant symbols)
                            |
                            v
              graph expansion (callers/callees of the top hits,
              so the model sees "who calls this" without it having
              to be textually similar to the question)
                            |
                            v
                 context assembly --> LLM --> answer + citations

If no LLM is configured, this still returns something useful: the ranked
search hits themselves, formatted as an answer, so the retrieval half of
the system is demonstrable without an API key. `mode` on the result tells
the caller (and the UI) which path produced the answer.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.embeddings import EmbeddingProvider
from app.core.llm import LLMProvider, LLMUnavailable
from app.core.storage.graph_store import GraphStore
from app.core.storage.vector_store import ScoredRecord, VectorStore

RAG_SYSTEM_PROMPT = (
    "You are a senior engineer explaining an unfamiliar codebase to a "
    "teammate. You will be given retrieved code snippets and call-graph "
    "relationships, then a question. Answer using ONLY the given context. "
    "Reference specific files and function names so the answer is "
    "verifiable. If the context doesn't fully answer the question, say "
    "plainly what's missing instead of guessing or inventing behavior."
)


@dataclass
class Citation:
    file_path: str
    symbol_name: str
    kind: str
    start_line: int
    end_line: int


@dataclass
class ChatAnswer:
    answer: str
    citations: list[Citation]
    mode: str  # "generated" | "extractive"


def _format_context_block(record) -> str:
    return f"### {record.name} ({record.kind}) — {record.file_path}:{record.start_line}-{record.end_line}\n{record.text}"


def _extractive_answer(hits: list[ScoredRecord]) -> str:
    if not hits:
        return (
            "I didn't find anything relevant in this repo. It may still be indexing, "
            "or try rephrasing -- search matches on identifiers and summaries."
        )
    lines = [
        "No LLM is configured for this deployment, so here's what semantic search "
        "found directly (set ANTHROPIC_API_KEY for a generated, synthesized answer):",
        "",
    ]
    for h in hits[:6]:
        r = h.record
        snippet = r.text.strip().replace("\n", " ")[:160]
        lines.append(f"- **{r.name}** ({r.kind}) — `{r.file_path}:{r.start_line}` — {snippet}")
    return "\n".join(lines)


async def answer_question(
    question: str,
    repo_id: str,
    *,
    vector_store: VectorStore,
    graph_store: GraphStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    top_k: int = 8,
    graph_expand_top_n: int = 3,
) -> ChatAnswer:
    query_embedding = embedder.embed([question])[0]
    hits = await vector_store.search(repo_id, query_embedding, top_k=top_k)

    citations = [
        Citation(
            file_path=h.record.file_path, symbol_name=h.record.name, kind=h.record.kind,
            start_line=h.record.start_line, end_line=h.record.end_line,
        )
        for h in hits
    ]

    if not hits:
        return ChatAnswer(answer=_extractive_answer(hits), citations=[], mode="extractive")

    context_blocks = [_format_context_block(h.record) for h in hits]

    graph_notes: list[str] = []
    for h in hits[:graph_expand_top_n]:
        symbol_id = h.record.symbol_id
        if not symbol_id:
            continue
        callers = await graph_store.callers_of(repo_id, symbol_id)
        callees = await graph_store.callees_of(repo_id, symbol_id)
        if callers:
            graph_notes.append(
                f"{h.record.name} is called by: " + ", ".join(c.qualified_name for c in callers[:6])
            )
        if callees:
            graph_notes.append(
                f"{h.record.name} calls: " + ", ".join(c.qualified_name for c in callees[:6])
            )

    context = "\n\n---\n\n".join(context_blocks)
    if graph_notes:
        context += "\n\nDependency relationships (from the call graph):\n" + "\n".join(graph_notes)

    prompt = f"Codebase context:\n\n{context}\n\n---\n\nQuestion: {question}"

    try:
        answer_text = llm.generate(system=RAG_SYSTEM_PROMPT, prompt=prompt, max_tokens=900)
        mode = "generated"
    except LLMUnavailable:
        answer_text = _extractive_answer(hits)
        mode = "extractive"

    return ChatAnswer(answer=answer_text, citations=citations, mode=mode)
