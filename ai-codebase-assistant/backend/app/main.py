from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, chat, files, graph, repos
from app.config import get_settings
from app.core.storage.vector_store import PgVectorStore, get_vector_store
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()

    vector_store = get_vector_store()
    if isinstance(vector_store, PgVectorStore):
        await vector_store.ensure_schema()

    logger.info(
        "startup: vector_provider=%s graph_provider=%s llm_provider=%s use_celery=%s",
        settings.vector_provider, settings.graph_provider, settings.llm_provider, settings.use_celery,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Codebase Assistant",
        description="Upload or connect a repo; ask questions about how it works.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(repos.router)
    app.include_router(files.router)
    app.include_router(chat.router)
    app.include_router(graph.router)
    app.include_router(analysis.router)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "vector_provider": settings.vector_provider,
            "graph_provider": settings.graph_provider,
            "llm_provider": settings.llm_provider if settings.anthropic_api_key or settings.openai_api_key else "none",
        }

    return app


app = create_app()
