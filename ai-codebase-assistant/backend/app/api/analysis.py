from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deadcode import find_dead_code
from app.core.llm import LLMUnavailable, get_llm
from app.core.storage.graph_store import get_graph_store
from app.db.session import get_session
from app.models.db import Repo, SecurityFindingRecord, SymbolRecord
from app.models.schemas import (
    AnalysisOut,
    CodeReviewRequest,
    CodeReviewResponse,
    ComplexityHotspotOut,
    DeadCodeFindingOut,
    SecurityFindingOut,
    SymbolOut,
)

router = APIRouter(prefix="/api/repos/{repo_id}", tags=["analysis"])

CODE_REVIEW_SYSTEM_PROMPT = (
    "You are a precise, constructive senior code reviewer. Review the given "
    "snippet for correctness, readability, potential bugs, and complexity. "
    "Be specific and reference line content, not line numbers (the snippet "
    "may not include them). Keep it to a few short paragraphs or a short "
    "bullet list -- prioritize the two or three things that matter most "
    "rather than listing everything you notice."
)


async def _get_repo_or_404(repo_id: str, session: AsyncSession) -> Repo:
    repo = await session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.get("/analysis", response_model=AnalysisOut)
async def get_analysis(repo_id: str, session: AsyncSession = Depends(get_session)):
    await _get_repo_or_404(repo_id, session)

    symbol_records = (
        (await session.execute(select(SymbolRecord).where(SymbolRecord.repo_id == repo_id))).scalars().all()
    )
    by_id = {s.id: s for s in symbol_records}
    decorators_by_id = {s.id: (s.decorators or []) for s in symbol_records}

    dead = await find_dead_code(get_graph_store(), repo_id, decorators_by_id)
    dead_out = [
        DeadCodeFindingOut(symbol=SymbolOut.model_validate(by_id[f.node.id]), reason=f.reason)
        for f in dead
        if f.node.id in by_id
    ]

    hotspots = sorted(
        (s for s in symbol_records if s.complexity is not None), key=lambda s: -s.complexity
    )[:15]
    hotspots_out = [
        ComplexityHotspotOut(symbol=SymbolOut.model_validate(s), complexity=s.complexity, line_count=s.end_line - s.start_line + 1)
        for s in hotspots
    ]

    findings = (
        (await session.execute(select(SecurityFindingRecord).where(SecurityFindingRecord.repo_id == repo_id)))
        .scalars()
        .all()
    )
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings_sorted = sorted(findings, key=lambda f: severity_rank.get(f.severity, 3))
    findings_out = [
        SecurityFindingOut(file_path=f.file_path, line=f.line, severity=f.severity,
                            confidence=f.confidence, rule=f.rule, message=f.message)
        for f in findings_sorted
    ]

    return AnalysisOut(dead_code=dead_out, complexity_hotspots=hotspots_out, security_findings=findings_out)


@router.post("/review", response_model=CodeReviewResponse)
async def review_code(repo_id: str, body: CodeReviewRequest, session: AsyncSession = Depends(get_session)):
    await _get_repo_or_404(repo_id, session)
    llm = get_llm()
    lang_hint = f" ({body.language})" if body.language else ""
    prompt = f"Review this code{lang_hint}:\n\n```\n{body.code}\n```"
    try:
        review = llm.generate(system=CODE_REVIEW_SYSTEM_PROMPT, prompt=prompt, max_tokens=800)
        mode = "generated"
    except LLMUnavailable:
        review = (
            "No LLM is configured for this deployment, so automated review isn't available. "
            "Set ANTHROPIC_API_KEY to enable it."
        )
        mode = "unavailable"
    return CodeReviewResponse(review=review, mode=mode)
