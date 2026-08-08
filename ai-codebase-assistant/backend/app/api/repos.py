from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.ingestion import IngestionError, clone_github_repo, extract_zip, validate_github_url
from app.core.storage.graph_store import get_graph_store
from app.core.storage.vector_store import get_vector_store
from app.db.session import get_session
from app.models.db import Repo, SecurityFindingRecord, SymbolRecord
from app.models.schemas import CloneRepoRequest, RepoSummary
from app.worker.tasks import run_indexing_job

router = APIRouter(prefix="/api/repos", tags=["repos"])


def _new_repo_id() -> str:
    return uuid.uuid4().hex[:12]


async def _dispatch_indexing(repo_id: str, background_tasks: BackgroundTasks, settings: Settings) -> None:
    if settings.use_celery:
        from app.worker.tasks import index_repository_task

        index_repository_task.delay(repo_id)
    else:
        background_tasks.add_task(run_indexing_job, repo_id)


@router.post("/clone", response_model=RepoSummary)
async def clone_repo(
    body: CloneRepoRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    try:
        owner, name = validate_github_url(body.url)
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo_id = _new_repo_id()
    dest = Path(settings.repo_storage_path) / repo_id
    try:
        clone_github_repo(body.url, dest)
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = Repo(
        id=repo_id, name=f"{owner}/{name}", source_type="github", source=body.url,
        status="pending", local_path=str(dest),
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)

    await _dispatch_indexing(repo_id, background_tasks, settings)
    return repo


@router.post("/upload", response_model=RepoSummary)
async def upload_repo(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip file of the repository.")

    repo_id = _new_repo_id()
    storage_root = Path(settings.repo_storage_path)
    storage_root.mkdir(parents=True, exist_ok=True)
    zip_path = storage_root / f"{repo_id}_upload.zip"
    dest = storage_root / repo_id

    with zip_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        extract_zip(zip_path, dest)
    except IngestionError as exc:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        zip_path.unlink(missing_ok=True)

    repo = Repo(
        id=repo_id, name=file.filename.removesuffix(".zip"), source_type="zip", source=file.filename,
        status="pending", local_path=str(dest),
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)

    await _dispatch_indexing(repo_id, background_tasks, settings)
    return repo


@router.get("", response_model=list[RepoSummary])
async def list_repos(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Repo).order_by(Repo.created_at.desc()))
    return result.scalars().all()


@router.get("/{repo_id}", response_model=RepoSummary)
async def get_repo(repo_id: str, session: AsyncSession = Depends(get_session)):
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.delete("/{repo_id}", status_code=204)
async def delete_repo(repo_id: str, session: AsyncSession = Depends(get_session)):
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    await get_graph_store().delete_repo(repo_id)
    await get_vector_store().delete_repo(repo_id)
    await session.execute(SymbolRecord.__table__.delete().where(SymbolRecord.repo_id == repo_id))
    await session.execute(SecurityFindingRecord.__table__.delete().where(SecurityFindingRecord.repo_id == repo_id))
    shutil.rmtree(repo.local_path, ignore_errors=True)
    await session.delete(repo)
    await session.commit()
    return None
