"""
Dependency graph storage behind an interface, same pattern as vector_store.py:

- InMemoryGraphStore: networkx.MultiDiGraph, zero setup. Default, and what
  the test suite runs against (no Neo4j server available in CI without extra
  infra).
- Neo4jGraphStore: real Neo4j over Bolt, for large repos and for the graph
  visualization queries to run as actual Cypher instead of a Python loop.
  Used by docker-compose.yml.

Nodes are symbols (function/method/class/interface); edges are CALLS,
IMPORTS, INHERITS, and CONTAINS (class -> its methods). Call edges carry a
`confidence` (exact | same_file | heuristic) set by graph_builder.py, since
callee names are resolved by name-matching, not a type checker.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import networkx as nx


@dataclass(frozen=True)
class GraphNode:
    id: str
    repo_id: str
    kind: str  # function | method | class | interface | file
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    kind: str  # CALLS | IMPORTS | INHERITS | CONTAINS
    confidence: str = "exact"  # exact | same_file | heuristic


class GraphStore(ABC):
    @abstractmethod
    async def upsert_nodes(self, nodes: list[GraphNode]) -> None: ...

    @abstractmethod
    async def upsert_edges(self, repo_id: str, edges: list[GraphEdge]) -> None: ...

    @abstractmethod
    async def delete_repo(self, repo_id: str) -> None: ...

    @abstractmethod
    async def get_subgraph(self, repo_id: str) -> tuple[list[GraphNode], list[GraphEdge]]: ...

    @abstractmethod
    async def callers_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        """Who calls this symbol."""

    @abstractmethod
    async def callees_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        """What this symbol calls."""

    @abstractmethod
    async def unreferenced_symbols(self, repo_id: str) -> list[GraphNode]:
        """Functions/methods with zero incoming CALLS edges -- candidates for
        dead code (see core/deadcode.py, which adds entrypoint heuristics on
        top of this raw signal)."""

    @abstractmethod
    async def shortest_path(self, repo_id: str, source_id: str, target_id: str) -> list[GraphNode] | None: ...


@dataclass
class InMemoryGraphStore(GraphStore):
    _graphs: dict[str, nx.MultiDiGraph] = field(default_factory=dict)
    _nodes: dict[str, dict[str, GraphNode]] = field(default_factory=dict)

    def _graph_for(self, repo_id: str) -> nx.MultiDiGraph:
        return self._graphs.setdefault(repo_id, nx.MultiDiGraph())

    async def upsert_nodes(self, nodes: list[GraphNode]) -> None:
        for n in nodes:
            g = self._graph_for(n.repo_id)
            g.add_node(n.id, **n.__dict__)
            self._nodes.setdefault(n.repo_id, {})[n.id] = n

    async def upsert_edges(self, repo_id: str, edges: list[GraphEdge]) -> None:
        # Symbol ids are content hashes (file+name+kind+line), not globally
        # unique across repos -- two different repos (or the same repo
        # re-indexed) can legitimately produce the same id. Scoping to one
        # repo's graph explicitly (rather than searching all graphs for
        # whichever happens to contain both endpoints) is what makes that
        # safe; searching by node existence alone previously picked
        # whichever repo's graph happened to contain a matching id first.
        g = self._graph_for(repo_id)
        for e in edges:
            if g.has_node(e.source_id) and g.has_node(e.target_id):
                g.add_edge(e.source_id, e.target_id, kind=e.kind, confidence=e.confidence)

    async def delete_repo(self, repo_id: str) -> None:
        self._graphs.pop(repo_id, None)
        self._nodes.pop(repo_id, None)

    async def get_subgraph(self, repo_id: str) -> tuple[list[GraphNode], list[GraphEdge]]:
        g = self._graphs.get(repo_id)
        if g is None:
            return [], []
        nodes = list(self._nodes.get(repo_id, {}).values())
        edges = [
            GraphEdge(u, v, data.get("kind", "CALLS"), data.get("confidence", "exact"))
            for u, v, data in g.edges(data=True)
        ]
        return nodes, edges

    async def callers_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        g = self._graphs.get(repo_id)
        if g is None or not g.has_node(symbol_id):
            return []
        node_lookup = self._nodes.get(repo_id, {})
        return [
            node_lookup[u]
            for u, v, data in g.in_edges(symbol_id, data=True)
            if data.get("kind") == "CALLS" and u in node_lookup
        ]

    async def callees_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        g = self._graphs.get(repo_id)
        if g is None or not g.has_node(symbol_id):
            return []
        node_lookup = self._nodes.get(repo_id, {})
        return [
            node_lookup[v]
            for u, v, data in g.out_edges(symbol_id, data=True)
            if data.get("kind") == "CALLS" and v in node_lookup
        ]

    async def unreferenced_symbols(self, repo_id: str) -> list[GraphNode]:
        g = self._graphs.get(repo_id)
        if g is None:
            return []
        node_lookup = self._nodes.get(repo_id, {})
        out = []
        for node_id, node in node_lookup.items():
            if node.kind not in ("function", "method"):
                continue
            incoming_calls = [
                1 for u, _, data in g.in_edges(node_id, data=True) if data.get("kind") == "CALLS"
            ]
            if not incoming_calls:
                out.append(node)
        return out

    async def shortest_path(self, repo_id: str, source_id: str, target_id: str) -> list[GraphNode] | None:
        g = self._graphs.get(repo_id)
        if g is None or not g.has_node(source_id) or not g.has_node(target_id):
            return None
        try:
            path_ids = nx.shortest_path(g, source_id, target_id)
        except nx.NetworkXNoPath:
            return None
        node_lookup = self._nodes.get(repo_id, {})
        return [node_lookup[i] for i in path_ids if i in node_lookup]


class Neo4jGraphStore(GraphStore):
    """Same contract as InMemoryGraphStore, backed by real Cypher. Reviewed
    against the neo4j Python driver's documented async API; not exercised
    against a live server in this build (no Neo4j reachable from this
    sandbox) -- treat this implementation as needing a first real smoke
    test against `docker compose up` before depending on it in prod."""

    def __init__(self, uri: str, user: str, password: str):
        from neo4j import AsyncGraphDatabase

        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        await self._driver.close()

    async def upsert_nodes(self, nodes: list[GraphNode]) -> None:
        if not nodes:
            return
        # MERGE keys on (id, repo_id) together, not id alone -- same
        # cross-repo collision risk as upsert_edges above, but worse if
        # missed here: merging on id alone would fold two different repos'
        # symbols that hash to the same id into one node and thrash its
        # repo_id back and forth instead of keeping them separate.
        query = """
        UNWIND $nodes AS n
        MERGE (s:Symbol {id: n.id, repo_id: n.repo_id})
        SET s.kind = n.kind, s.name = n.name,
            s.qualified_name = n.qualified_name, s.file_path = n.file_path,
            s.start_line = n.start_line, s.end_line = n.end_line
        """
        async with self._driver.session() as session:
            await session.run(query, nodes=[n.__dict__ for n in nodes])

    async def upsert_edges(self, repo_id: str, edges: list[GraphEdge]) -> None:
        if not edges:
            return
        by_kind: dict[str, list[GraphEdge]] = {}
        for e in edges:
            by_kind.setdefault(e.kind, []).append(e)
        async with self._driver.session() as session:
            for kind, group in by_kind.items():
                # Both endpoints are matched *within this repo_id* -- symbol
                # ids are content hashes, not globally unique across repos,
                # so an unscoped MATCH on id alone could silently attach an
                # edge to another repo's node of the same hash.
                query = f"""
                UNWIND $edges AS e
                MATCH (a:Symbol {{id: e.source_id, repo_id: $repo_id}}),
                      (b:Symbol {{id: e.target_id, repo_id: $repo_id}})
                MERGE (a)-[r:{kind}]->(b)
                SET r.confidence = e.confidence
                """
                await session.run(
                    query, repo_id=repo_id,
                    edges=[{"source_id": e.source_id, "target_id": e.target_id, "confidence": e.confidence} for e in group],
                )

    async def delete_repo(self, repo_id: str) -> None:
        async with self._driver.session() as session:
            await session.run("MATCH (s:Symbol {repo_id: $r}) DETACH DELETE s", r=repo_id)

    async def get_subgraph(self, repo_id: str) -> tuple[list[GraphNode], list[GraphEdge]]:
        async with self._driver.session() as session:
            node_result = await session.run("MATCH (s:Symbol {repo_id: $r}) RETURN s", r=repo_id)
            nodes = [self._to_node(record["s"]) async for record in node_result]
            edge_result = await session.run(
                "MATCH (a:Symbol {repo_id: $r})-[rel]->(b:Symbol {repo_id: $r}) "
                "RETURN a.id AS src, b.id AS tgt, type(rel) AS kind, rel.confidence AS confidence",
                r=repo_id,
            )
            edges = [
                GraphEdge(record["src"], record["tgt"], record["kind"], record["confidence"] or "exact")
                async for record in edge_result
            ]
        return nodes, edges

    async def callers_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (caller:Symbol {repo_id: $r})-[:CALLS]->(:Symbol {id: $sid}) RETURN caller",
                r=repo_id, sid=symbol_id,
            )
            return [self._to_node(record["caller"]) async for record in result]

    async def callees_of(self, repo_id: str, symbol_id: str) -> list[GraphNode]:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (:Symbol {id: $sid})-[:CALLS]->(callee:Symbol {repo_id: $r}) RETURN callee",
                r=repo_id, sid=symbol_id,
            )
            return [self._to_node(record["callee"]) async for record in result]

    async def unreferenced_symbols(self, repo_id: str) -> list[GraphNode]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (s:Symbol {repo_id: $r})
                WHERE s.kind IN ['function', 'method'] AND NOT (()-[:CALLS]->(s))
                RETURN s
                """,
                r=repo_id,
            )
            return [self._to_node(record["s"]) async for record in result]

    async def shortest_path(self, repo_id: str, source_id: str, target_id: str) -> list[GraphNode] | None:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Symbol {id: $src}), (b:Symbol {id: $tgt}),
                      p = shortestPath((a)-[:CALLS*..15]-(b))
                RETURN [n IN nodes(p) | n] AS path
                """,
                src=source_id, tgt=target_id,
            )
            record = await result.single()
            if record is None:
                return None
            return [self._to_node(n) for n in record["path"]]

    @staticmethod
    def _to_node(record) -> GraphNode:
        return GraphNode(
            id=record["id"], repo_id=record["repo_id"], kind=record["kind"], name=record["name"],
            qualified_name=record["qualified_name"], file_path=record["file_path"],
            start_line=record["start_line"], end_line=record["end_line"],
        )


_graph_store_cache: GraphStore | None = None


def get_graph_store() -> GraphStore:
    global _graph_store_cache
    if _graph_store_cache is not None:
        return _graph_store_cache

    from app.config import get_settings

    settings = get_settings()
    if settings.graph_provider == "neo4j":
        _graph_store_cache = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    else:
        _graph_store_cache = InMemoryGraphStore()
    return _graph_store_cache
