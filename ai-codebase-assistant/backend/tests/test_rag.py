from pathlib import Path

import pytest

from app.core.embeddings import HashingEmbedder
from app.core.extractor import extract
from app.core.graph_builder import build_graph
from app.core.ingestion import walk_repository
from app.core.llm import LLMProvider, NullProvider
from app.core.parser import parse_source
from app.core.rag import answer_question
from app.core.storage.graph_store import InMemoryGraphStore
from app.core.storage.vector_store import InMemoryVectorStore, VectorRecord

FIXTURES = Path(__file__).parent / "fixtures" / "sample_repo"
REPO_ID = "test-repo"


class RecordingFakeLLM(LLMProvider):
    """Returns a canned answer but records the prompt so tests can assert
    the right context was actually assembled and handed to it."""

    def __init__(self, canned_answer: str = "Here is the answer."):
        self.last_system = None
        self.last_prompt = None
        self._canned = canned_answer

    def generate(self, system, prompt, max_tokens=1024):
        self.last_system = system
        self.last_prompt = prompt
        return self._canned


async def _build_indexed_stores(embedder):
    files = walk_repository(FIXTURES)
    all_paths = [f.rel_path for f in files]
    extractions = []
    for f in files:
        if f.language is None:
            continue
        pf = parse_source(f.rel_path, f.abs_path.read_bytes())
        extractions.append(extract(pf))

    nodes, edges = build_graph(REPO_ID, extractions, all_paths)
    graph_store = InMemoryGraphStore()
    await graph_store.upsert_nodes(nodes)
    await graph_store.upsert_edges(REPO_ID, edges)

    vector_store = InMemoryVectorStore()
    records = []
    for ext in extractions:
        for sym in ext.symbols:
            text = f"{sym.signature}\n{sym.docstring or ''}"
            records.append(
                VectorRecord(
                    id=sym.id, repo_id=REPO_ID, file_path=sym.file_path, symbol_id=sym.id,
                    kind=sym.kind, name=sym.name, text=text,
                    embedding=embedder.embed([text])[0],
                    start_line=sym.start_line, end_line=sym.end_line,
                )
            )
    await vector_store.upsert(records)
    return graph_store, vector_store


@pytest.mark.asyncio
async def test_rag_retrieves_relevant_symbol_and_expands_graph_context():
    embedder = HashingEmbedder(dimension=256)
    graph_store, vector_store = await _build_indexed_stores(embedder)
    llm = RecordingFakeLLM("AuthService.authenticate_user handles login.")

    result = await answer_question(
        "How does user authentication work?", REPO_ID,
        vector_store=vector_store, graph_store=graph_store, embedder=embedder, llm=llm,
    )

    assert result.mode == "generated"
    assert result.answer == "AuthService.authenticate_user handles login."

    # The hashing embedder is a lexical/n-gram signal, not deep semantics, so
    # it correctly surfaces the *cluster* of auth-related code (the class and
    # its methods, which all share tokens like "user"/"password"/"session")
    # above unrelated code -- but doesn't guarantee perfect intra-cluster
    # ranking the way a trained embedding model would. Assert the property
    # that actually matters: authenticate_user is retrieved at all, and
    # unrelated payment/formatting code is not crowding it out entirely.
    retrieved_names = {c.symbol_name for c in result.citations}
    assert "authenticate_user" in retrieved_names
    assert "AuthService" in retrieved_names

    # graph expansion should have run and surfaced *some* real call-graph
    # relationship (not asserting a specific one -- which methods land in
    # the top-N expanded slots depends on embedding ranking details tested
    # separately; what matters here is that expansion happened at all and
    # pulled in real edges, not that a particular symbol made the cut).
    assert "Dependency relationships (from the call graph):" in llm.last_prompt
    assert " calls: " in llm.last_prompt or " is called by: " in llm.last_prompt


@pytest.mark.asyncio
async def test_graph_expansion_formats_real_caller_callee_names():
    """Deterministic version of the expansion check above: a single-record
    vector store removes any ranking ambiguity, so we can assert on the
    exact relationship text without depending on embedding rank order."""
    from app.core.storage.graph_store import GraphEdge, GraphNode, InMemoryGraphStore
    from app.core.storage.vector_store import InMemoryVectorStore, VectorRecord

    graph_store = InMemoryGraphStore()
    await graph_store.upsert_nodes([
        GraphNode("caller1", REPO_ID, "function", "login", "login", "main.py", 1, 5),
        GraphNode("target1", REPO_ID, "function", "authenticate_user", "authenticate_user", "auth.py", 1, 5),
        GraphNode("callee1", REPO_ID, "function", "hash_password", "hash_password", "auth.py", 10, 12),
    ])
    await graph_store.upsert_edges(REPO_ID, [
        GraphEdge("caller1", "target1", "CALLS"),
        GraphEdge("target1", "callee1", "CALLS"),
    ])

    embedder = HashingEmbedder(dimension=64)
    vector_store = InMemoryVectorStore()
    vec = embedder.embed(["authenticate_user"])[0]
    await vector_store.upsert([
        VectorRecord(id="target1", repo_id=REPO_ID, file_path="auth.py", symbol_id="target1",
                     kind="function", name="authenticate_user", text="authenticate_user",
                     embedding=vec, start_line=1, end_line=5)
    ])

    llm = RecordingFakeLLM()
    await answer_question(
        "authenticate_user", REPO_ID,
        vector_store=vector_store, graph_store=graph_store, embedder=embedder, llm=llm,
    )
    assert "authenticate_user is called by: login" in llm.last_prompt
    assert "authenticate_user calls: hash_password" in llm.last_prompt


@pytest.mark.asyncio
async def test_rag_falls_back_to_extractive_mode_without_llm():
    embedder = HashingEmbedder(dimension=256)
    graph_store, vector_store = await _build_indexed_stores(embedder)

    result = await answer_question(
        "How does user authentication work?", REPO_ID,
        vector_store=vector_store, graph_store=graph_store, embedder=embedder, llm=NullProvider(),
    )

    assert result.mode == "extractive"
    assert "No LLM is configured" in result.answer
    assert len(result.citations) > 0


@pytest.mark.asyncio
async def test_rag_handles_empty_repo_gracefully():
    embedder = HashingEmbedder(dimension=256)
    empty_vector_store = InMemoryVectorStore()
    empty_graph_store = InMemoryGraphStore()
    result = await answer_question(
        "anything?", "nonexistent-repo",
        vector_store=empty_vector_store, graph_store=empty_graph_store,
        embedder=embedder, llm=RecordingFakeLLM(),
    )
    assert result.citations == []
    assert "didn't find anything" in result.answer
