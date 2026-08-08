import pytest

from app.core.deadcode import find_dead_code
from app.core.storage.graph_store import GraphNode, InMemoryGraphStore


def _node(id_, name, file_path="app/x.py", kind="function"):
    return GraphNode(id=id_, repo_id="r1", kind=kind, name=name, qualified_name=name,
                      file_path=file_path, start_line=1, end_line=5)


@pytest.mark.asyncio
async def test_dunder_and_route_and_test_functions_are_excluded():
    store = InMemoryGraphStore()
    nodes = [
        _node("1", "__init__"),
        _node("2", "login_route"),
        _node("3", "test_something", file_path="tests/test_auth.py"),
        _node("4", "truly_dead_function"),
        _node("5", "main"),
        _node("6", "constructor", kind="method"),
    ]
    await store.upsert_nodes(nodes)
    # no CALLS edges at all -> everything looks "unreferenced" to the raw signal
    decorators = {"2": ["@app.route('/login')"]}

    findings = await find_dead_code(store, "r1", decorators)
    flagged_names = {f.node.name for f in findings}

    assert flagged_names == {"truly_dead_function"}
