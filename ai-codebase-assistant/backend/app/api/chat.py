from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import get_embedder
from app.core.llm import get_llm
from app.core.rag import answer_question
from app.core.storage.graph_store import get_graph_store
from app.core.storage.vector_store import get_vector_store
from app.db.session import get_session
from app.models.db import Repo
from app.models.schemas import ChatRequest, ChatResponse, CitationOut

router = APIRouter(prefix="/api/repos/{repo_id}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(repo_id: str, body: ChatRequest, session: AsyncSession = Depends(get_session)):
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if repo.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Repo is not ready yet (status: {repo.status}). Wait for indexing to finish.",
        )

    result = await answer_question(
        body.question, repo_id,
        vector_store=get_vector_store(), graph_store=get_graph_store(),
        embedder=get_embedder(), llm=get_llm(),
    )
    return ChatResponse(
        answer=result.answer, mode=result.mode,
        citations=[
            CitationOut(file_path=c.file_path, symbol_name=c.symbol_name, kind=c.kind,
                        start_line=c.start_line, end_line=c.end_line)
            for c in result.citations
        ],
    )
