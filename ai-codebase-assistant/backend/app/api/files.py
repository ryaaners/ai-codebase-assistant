from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ingestion import walk_repository
from app.db.session import get_session
from app.models.db import Repo, SymbolRecord
from app.models.schemas import FileContent, FileNode, SymbolOut

router = APIRouter(prefix="/api/repos/{repo_id}/files", tags=["files"])

MAX_INLINE_FILE_BYTES = 1_000_000


async def _get_repo_or_404(repo_id: str, session: AsyncSession) -> Repo:
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


def _build_tree(rel_paths: list[str]) -> list[FileNode]:
    tree: dict = {}
    for rel_path in rel_paths:
        parts = rel_path.split("/")
        node = tree
        for i, part in enumerate(parts):
            is_leaf = i == len(parts) - 1
            node = node.setdefault(part, {"__leaf__": is_leaf, "__kids__": {}})
            node = node["__kids__"]

    def to_nodes(subtree: dict, prefix: str) -> list[FileNode]:
        out = []
        for name in sorted(subtree.keys(), key=lambda n: (subtree[n]["__leaf__"], n.lower())):
            entry = subtree[name]
            path = f"{prefix}/{name}" if prefix else name
            if entry["__leaf__"]:
                out.append(FileNode(path=path, name=name, is_dir=False))
            else:
                out.append(FileNode(path=path, name=name, is_dir=True, children=to_nodes(entry["__kids__"], path)))
        return out

    return to_nodes(tree, "")


@router.get("", response_model=list[FileNode])
async def get_file_tree(repo_id: str, session: AsyncSession = Depends(get_session)):
    repo = await _get_repo_or_404(repo_id, session)
    files = walk_repository(Path(repo.local_path))
    return _build_tree([f.rel_path for f in files])


@router.get("/content", response_model=FileContent)
async def get_file_content(
    repo_id: str, path: str = Query(...), session: AsyncSession = Depends(get_session)
):
    repo = await _get_repo_or_404(repo_id, session)
    root = Path(repo.local_path).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > MAX_INLINE_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large to display inline")

    from app.core.parser import detect_language

    content = target.read_text(encoding="utf-8", errors="replace")
    result = await session.execute(
        select(SymbolRecord).where(SymbolRecord.repo_id == repo_id, SymbolRecord.file_path == path)
    )
    symbols = [SymbolOut.model_validate(s) for s in result.scalars().all()]
    return FileContent(path=path, language=detect_language(path), content=content, symbols=symbols)
