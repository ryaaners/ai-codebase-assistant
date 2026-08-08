from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.graph_store import get_graph_store
from app.db.session import get_session
from app.models.db import Repo, SymbolRecord
from app.models.schemas import GraphEdgeOut, GraphNodeOut, GraphOut, SymbolNeighborsOut, SymbolOut

router = APIRouter(prefix="/api/repos/{repo_id}/graph", tags=["graph"])


async def _get_repo_or_404(repo_id: str, session: AsyncSession) -> Repo:
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


async def _symbol_out(repo_id: str, symbol_id: str, session: AsyncSession) -> SymbolOut | None:
    # Composite PK (repo_id, id) -- see models/db.py for why a bare id isn't
    # safe to key on across repos.
    record = await session.get(SymbolRecord, (repo_id, symbol_id))
    if record is None:
        return None
    return SymbolOut.model_validate(record)


@router.get("", response_model=GraphOut)
async def get_graph(
    repo_id: str,
    kind: str | None = Query(None, description="Filter to one node kind, e.g. 'file' for a module-level view"),
    session: AsyncSession = Depends(get_session),
):
    await _get_repo_or_404(repo_id, session)
    nodes, edges = await get_graph_store().get_subgraph(repo_id)
    if kind:
        nodes = [n for n in nodes if n.kind == kind]
        keep_ids = {n.id for n in nodes}
        edges = [e for e in edges if e.source_id in keep_ids and e.target_id in keep_ids]
    return GraphOut(
        nodes=[GraphNodeOut(id=n.id, kind=n.kind, name=n.name, qualified_name=n.qualified_name,
                             file_path=n.file_path, start_line=n.start_line, end_line=n.end_line) for n in nodes],
        edges=[GraphEdgeOut(source=e.source_id, target=e.target_id, kind=e.kind, confidence=e.confidence) for e in edges],
    )


@router.get("/symbols/{symbol_id}/neighbors", response_model=SymbolNeighborsOut)
async def get_symbol_neighbors(repo_id: str, symbol_id: str, session: AsyncSession = Depends(get_session)):
    await _get_repo_or_404(repo_id, session)
    symbol = await _symbol_out(repo_id, symbol_id, session)
    if symbol is None:
        raise HTTPException(status_code=404, detail="Symbol not found")

    graph_store = get_graph_store()
    caller_nodes = await graph_store.callers_of(repo_id, symbol_id)
    callee_nodes = await graph_store.callees_of(repo_id, symbol_id)

    async def hydrate(nodes):
        out = []
        for n in nodes:
            s = await _symbol_out(repo_id, n.id, session)
            if s is not None:
                out.append(s)
        return out

    return SymbolNeighborsOut(symbol=symbol, callers=await hydrate(caller_nodes), callees=await hydrate(callee_nodes))


@router.get("/path", response_model=list[SymbolOut])
async def get_path(
    repo_id: str, source: str = Query(...), target: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await _get_repo_or_404(repo_id, session)
    path = await get_graph_store().shortest_path(repo_id, source, target)
    if path is None:
        raise HTTPException(status_code=404, detail="No path found between these symbols")
    out = []
    for n in path:
        s = await _symbol_out(repo_id, n.id, session)
        if s is not None:
            out.append(s)
    return out
