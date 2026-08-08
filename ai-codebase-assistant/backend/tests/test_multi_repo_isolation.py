from pathlib import Path

import pytest

from app.core.extractor import extract
from app.core.graph_builder import build_graph
from app.core.ingestion import walk_repository
from app.core.parser import parse_source
from app.core.storage.graph_store import InMemoryGraphStore
from app.core.storage.vector_store import InMemoryVectorStore, VectorRecord
from app.core.embeddings import HashingEmbedder

FIXTURES = Path(__file__).parent / "fixtures" / "sample_repo"


def _extract_all():
    files = walk_repository(FIXTURES)
    extractions = []
    for f in files:
        if f.language is None:
            continue
        pf = parse_source(f.rel_path, f.abs_path.read_bytes())
        extractions.append(extract(pf))
    return extractions, [f.rel_path for f in files]


@pytest.mark.asyncio
async def test_same_content_indexed_under_two_repo_ids_does_not_collide():
    """Symbol ids are a hash of (file_path, qualified_name, kind, start_line)
    -- deliberately *not* including repo_id, so re-indexing unchanged code
    keeps stable ids. That means the exact same id can legitimately appear
    in two different repos (e.g. the same repo uploaded twice, or two repos
    sharing a vendored file). This pins that both storage layers keep them
    fully separate rather than colliding or cross-contaminating."""
    extractions, paths = _extract_all()

    graph_store = InMemoryGraphStore()
    vector_store = InMemoryVectorStore()
    embedder = HashingEmbedder(dimension=64)

    for repo_id in ("repo-a", "repo-b"):
        nodes, edges = build_graph(repo_id, extractions, paths)
        await graph_store.upsert_nodes(nodes)
        await graph_store.upsert_edges(repo_id, edges)

        records = [
            VectorRecord(
                id=n.id, repo_id=repo_id, file_path=n.file_path, symbol_id=n.id, kind=n.kind,
                name=n.name, text=n.name, embedding=embedder.embed([n.name])[0],
                start_line=n.start_line, end_line=n.end_line,
            )
            for n in nodes
            if n.kind != "file"
        ]
        await vector_store.upsert(records)

    # both repos report the full symbol count -- neither overwrote the other
    nodes_a, edges_a = await graph_store.get_subgraph("repo-a")
    nodes_b, edges_b = await graph_store.get_subgraph("repo-b")
    assert len(nodes_a) == len(nodes_b) and len(nodes_a) > 0
    assert len(edges_a) == len(edges_b) and len(edges_a) > 0

    assert await vector_store.count("repo-a") == await vector_store.count("repo-b") > 0

    # deleting one repo must not touch the other, even though they share ids
    await graph_store.delete_repo("repo-a")
    await vector_store.delete_repo("repo-a")
    nodes_a_after, _ = await graph_store.get_subgraph("repo-a")
    nodes_b_after, _ = await graph_store.get_subgraph("repo-b")
    assert nodes_a_after == []
    assert len(nodes_b_after) == len(nodes_b)
    assert await vector_store.count("repo-b") > 0
