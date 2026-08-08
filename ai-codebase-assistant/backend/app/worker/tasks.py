"""
One indexing job, two dispatch paths:

- USE_CELERY=false (default): the /repos endpoints hand this coroutine
  straight to FastAPI's BackgroundTasks. Zero extra infrastructure --
  works the moment you `uvicorn app.main:app`.
- USE_CELERY=true: `run_indexing_job_task.delay(repo_id)` puts it on Redis,
  a `celery -A app.worker.celery_app worker` process picks it up. Same
  underlying function either way (`_run`), so indexing behavior can't
  drift between the two paths.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.embeddings import get_embedder
from app.core.indexing import index_repository
from app.core.llm import get_llm
from app.core.storage.graph_store import get_graph_store
from app.core.storage.vector_store import get_vector_store
from app.db.session import get_session_factory
from app.models.db import Repo

logger = logging.getLogger(__name__)


async def _run(repo_id: str) -> None:
    from app.config import get_settings

    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        repo = await session.get(Repo, repo_id)
        if repo is None:
            logger.error("indexing job requested for unknown repo_id=%s", repo_id)
            return
        repo.status = "indexing"
        await session.commit()
        local_path = repo.local_path

    try:
        await index_repository(
            repo_id, Path(local_path),
            session_factory=session_factory,
            graph_store=get_graph_store(),
            vector_store=get_vector_store(),
            embedder=get_embedder(),
            llm=get_llm(),
            max_file_size_bytes=settings.max_file_size_bytes,
            max_files=settings.max_files_per_repo,
        )
    except Exception as exc:  # indexing failures must surface to the UI, not vanish in a worker log
        logger.exception("indexing failed for repo_id=%s", repo_id)
        async with session_factory() as session:
            repo = await session.get(Repo, repo_id)
            if repo is not None:
                repo.status = "failed"
                repo.error_message = str(exc)[:2000]
                await session.commit()


async def run_indexing_job(repo_id: str) -> None:
    """Entry point for the BackgroundTasks (non-Celery) path."""
    await _run(repo_id)


def run_indexing_job_sync(repo_id: str) -> None:
    """Entry point for Celery, which calls tasks synchronously."""
    asyncio.run(_run(repo_id))


# Registered at *module* level (not inside a function called lazily by the
# API process) specifically so that `celery -A app.worker.celery_app.celery_app
# worker` -- which imports this module via celery_app.py's trailing import,
# see celery_app.py -- ends up with the task registered in the worker
# process too, not just wherever `.delay()` happens to be called from.
from app.worker.celery_app import celery_app  # noqa: E402


@celery_app.task(name="index_repository")
def index_repository_task(repo_id: str) -> None:
    run_indexing_job_sync(repo_id)
