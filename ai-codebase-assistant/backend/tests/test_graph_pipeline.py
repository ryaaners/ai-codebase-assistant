import asyncio
from pathlib import Path

import pytest

from app.core.extractor import extract
from app.core.graph_builder import build_graph
from app.core.parser import parse_source
from app.core.ingestion import walk_repository
from app.core.storage.graph_store import InMemoryGraphStore

FIXTURES = Path(__file__).parent / "fixtures" / "sample_repo"


def _index_fixture_repo():
    files = walk_repository(FIXTURES)
    all_paths = [f.rel_path for f in files]
    extractions = []
    for f in files:
        if f.language is None:
            continue
        pf = parse_source(f.rel_path, f.abs_path.read_bytes())
        extractions.append(extract(pf))
    nodes, edges = build_graph("test-repo", extractions, all_paths)
    return nodes, edges


def _by_qualified_name(nodes, qname):
    return next(n for n in nodes if n.qualified_name == qname)


@pytest.mark.asyncio
async def test_full_pipeline_builds_expected_graph():
    nodes, edges = _index_fixture_repo()
    store = InMemoryGraphStore()
    await store.upsert_nodes(nodes)
    await store.upsert_edges("test-repo", edges)

    auth_method = _by_qualified_name(nodes, "AuthService.authenticate_user")
    check_password = _by_qualified_name(nodes, "AuthService._check_password")
    hash_password = _by_qualified_name(nodes, "hash_password")
    login_fn = _by_qualified_name(nodes, "login")
    auth_class = _by_qualified_name(nodes, "AuthService")

    # cross-file call resolution: main.py's login() calls
    # auth_service.authenticate_user(...) -- extractor only knew the name
    # "authenticate_user"; graph_builder had to find it in a *different*
    # file (auth.py) and link them.
    callees_of_login = await store.callees_of("test-repo", login_fn.id)
    assert auth_method.id in {n.id for n in callees_of_login}

    # multi-hop chain: login -> authenticate_user -> _check_password -> hash_password
    path = await store.shortest_path("test-repo", login_fn.id, hash_password.id)
    assert path is not None
    assert [n.qualified_name for n in path] == [
        "login", "AuthService.authenticate_user", "AuthService._check_password", "hash_password",
    ]

    # CONTAINS: class -> its methods
    callers_via_contains = [e for e in edges if e.kind == "CONTAINS" and e.source_id == auth_class.id]
    contained_names = set()
    for e in callers_via_contains:
        contained_names.add(next(n.qualified_name for n in nodes if n.id == e.target_id))
    assert "AuthService.authenticate_user" in contained_names
    assert "AuthService._check_password" in contained_names

    # dead code: unused_helper() is never called anywhere in the fixture repo
    unreferenced = await store.unreferenced_symbols("test-repo")
    unreferenced_names = {n.qualified_name for n in unreferenced}
    assert "unused_helper" in unreferenced_names
    # but authenticate_user (called from main.py) must NOT show up as dead
    assert "AuthService.authenticate_user" not in unreferenced_names


@pytest.mark.asyncio
async def test_imports_resolved_across_files():
    nodes, edges = _index_fixture_repo()
    import_edges = [e for e in edges if e.kind == "IMPORTS"]
    file_nodes = {n.id: n for n in nodes if n.kind == "file"}
    resolved_pairs = {
        (file_nodes[e.source_id].file_path, file_nodes[e.target_id].file_path) for e in import_edges
    }
    assert ("app/main.py", "app/auth.py") in resolved_pairs


@pytest.mark.asyncio
async def test_typescript_dead_code_detected():
    nodes, edges = _index_fixture_repo()
    store = InMemoryGraphStore()
    await store.upsert_nodes(nodes)
    await store.upsert_edges("test-repo", edges)
    unreferenced = await store.unreferenced_symbols("test-repo")
    names = {n.qualified_name for n in unreferenced}
    assert "unusedFormatter" in names
    # processPayment also has zero *in-repo* incoming calls in this fixture
    # (nothing in our tiny sample calls it) -- that's the known false-positive
    # shape of a pure call-graph signal for exported/public API methods.
    # core/deadcode.py layers entrypoint heuristics on top of this raw
    # signal specifically to filter these out; see test_deadcode.py.
    assert "PaymentService.processPayment" in names
