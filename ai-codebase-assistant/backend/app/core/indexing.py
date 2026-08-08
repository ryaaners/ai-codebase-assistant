"""
The pipeline every repo goes through, start to finish. This is what
worker/tasks.py calls, whether it's dispatched via FastAPI's BackgroundTasks
(default) or Celery (when USE_CELERY=true) -- both just call
`index_repository()` and differ only in *how* it gets scheduled.

    ingestion (already on disk by the time this runs)
        -> parse + extract every supported file      (parser.py, extractor.py)
        -> build the whole-repo graph                 (graph_builder.py)
        -> write nodes/edges                          (graph_store)
        -> summarize undocumented symbols              (summarizer.py)
        -> embed every symbol                          (embeddings.py)
        -> write vectors                                (vector_store)
        -> cache symbol/security/complexity facts       (SQL)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete

from app.core.complexity import compute_complexity
from app.core.embeddings import EmbeddingProvider
from app.core.extractor import FileExtraction, extract
from app.core.graph_builder import build_graph
from app.core.ingestion import detect_primary_languages, walk_repository
from app.core.llm import LLMProvider
from app.core.parser import ParsedFile, parse_source
from app.core.security_scan import scan_file
from app.core.storage.graph_store import GraphStore
from app.core.storage.vector_store import VectorRecord, VectorStore
from app.core.summarizer import summarize_symbols
from app.models.db import Repo, SecurityFindingRecord, SymbolRecord

logger = logging.getLogger(__name__)


@dataclass
class IndexingResult:
    repo_id: str
    file_count: int
    symbol_count: int
    languages: dict[str, int]
    security_finding_count: int


async def index_repository(
    repo_id: str,
    repo_root: Path,
    *,
    session_factory,
    graph_store: GraphStore,
    vector_store: VectorStore,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    max_file_size_bytes: int,
    max_files: int,
) -> IndexingResult:
    files = walk_repository(repo_root, max_file_size_bytes=max_file_size_bytes, max_files=max_files)
    all_paths = [f.rel_path for f in files]
    languages = detect_primary_languages(files)

    parsed_by_extraction: list[tuple[FileExtraction, ParsedFile]] = []
    security_findings = []
    for f in files:
        abs_path = f.abs_path
        if f.language is not None:
            try:
                source = abs_path.read_bytes()
                pf = parse_source(f.rel_path, source)
            except OSError:
                pf = None
            if pf is not None:
                parsed_by_extraction.append((extract(pf), pf))
        # security scanning runs on every readable file, not just parsed
        # ones (bandit needs valid python; the heuristic path is language-
        # agnostic and still worth running on config/env-ish files).
        try:
            security_findings.extend(scan_file(f.rel_path, abs_path, f.language))
        except Exception:  # a single bad file shouldn't abort indexing
            logger.exception("security scan failed for %s", f.rel_path)

    extractions = [e for e, _ in parsed_by_extraction]
    nodes, edges = build_graph(repo_id, extractions, all_paths)

    await graph_store.delete_repo(repo_id)
    await graph_store.upsert_nodes(nodes)
    await graph_store.upsert_edges(repo_id, edges)

    all_symbols = [s for ext in extractions for s in ext.symbols]
    snippets: dict[str, str] = {}
    for ext, pf in parsed_by_extraction:
        for s in ext.symbols:
            snippets[s.id] = pf.source[s.start_byte : s.end_byte].decode("utf-8", errors="replace")

    summaries = summarize_symbols(llm, all_symbols, snippets)

    complexity_by_symbol: dict[str, int] = {}
    for ext, pf in parsed_by_extraction:
        for result in compute_complexity(pf, ext.symbols):
            complexity_by_symbol[result.symbol_id] = result.complexity

    await vector_store.delete_repo(repo_id)
    embed_texts = [f"{s.signature}\n{summaries.get(s.id, '')}" for s in all_symbols]
    vectors = embedder.embed(embed_texts) if embed_texts else []
    records = [
        VectorRecord(
            id=s.id, repo_id=repo_id, file_path=s.file_path, symbol_id=s.id, kind=s.kind,
            name=s.name, text=text, embedding=vec, start_line=s.start_line, end_line=s.end_line,
        )
        for s, text, vec in zip(all_symbols, embed_texts, vectors)
    ]
    await vector_store.upsert(records)

    async with session_factory() as session:
        await session.execute(delete(SymbolRecord).where(SymbolRecord.repo_id == repo_id))
        await session.execute(delete(SecurityFindingRecord).where(SecurityFindingRecord.repo_id == repo_id))
        for s in all_symbols:
            session.add(
                SymbolRecord(
                    id=s.id, repo_id=repo_id, kind=s.kind, name=s.name, qualified_name=s.qualified_name,
                    file_path=s.file_path, language=s.language, start_line=s.start_line, end_line=s.end_line,
                    signature=s.signature, docstring=s.docstring, summary=summaries.get(s.id),
                    decorators=s.decorators, complexity=complexity_by_symbol.get(s.id),
                )
            )
        for finding in security_findings:
            session.add(
                SecurityFindingRecord(
                    repo_id=repo_id, file_path=finding.file_path, line=finding.line,
                    severity=finding.severity, confidence=finding.confidence,
                    rule=finding.rule, message=finding.message,
                )
            )
        result = await session.get(Repo, repo_id)
        if result is not None:
            result.status = "ready"
            result.primary_language = next(iter(languages), None)
            result.languages = languages
            result.file_count = len(files)
            result.symbol_count = len(all_symbols)
            from datetime import datetime, timezone

            result.indexed_at = datetime.now(timezone.utc)
        await session.commit()

    return IndexingResult(
        repo_id=repo_id, file_count=len(files), symbol_count=len(all_symbols),
        languages=languages, security_finding_count=len(security_findings),
    )
