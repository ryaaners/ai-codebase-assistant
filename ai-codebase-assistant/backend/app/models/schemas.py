from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CloneRepoRequest(BaseModel):
    url: str = Field(..., description="Public GitHub repo URL, e.g. https://github.com/owner/repo")


class RepoSummary(BaseModel):
    id: str
    name: str
    source_type: str
    source: str
    status: str
    error_message: str | None = None
    primary_language: str | None = None
    languages: dict[str, int] = {}
    file_count: int = 0
    symbol_count: int = 0
    created_at: datetime
    indexed_at: datetime | None = None

    class Config:
        from_attributes = True


class FileNode(BaseModel):
    path: str
    name: str
    is_dir: bool
    language: str | None = None
    children: list["FileNode"] = []


class FileContent(BaseModel):
    path: str
    language: str | None
    content: str
    symbols: list["SymbolOut"] = []


class SymbolOut(BaseModel):
    id: str
    kind: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str | None = None
    summary: str | None = None
    complexity: int | None = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class CitationOut(BaseModel):
    file_path: str
    symbol_name: str
    kind: str
    start_line: int
    end_line: int


class ChatResponse(BaseModel):
    answer: str
    mode: str  # "generated" | "extractive"
    citations: list[CitationOut]


class GraphNodeOut(BaseModel):
    id: str
    kind: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int


class GraphEdgeOut(BaseModel):
    source: str
    target: str
    kind: str
    confidence: str


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class SymbolNeighborsOut(BaseModel):
    symbol: SymbolOut
    callers: list[SymbolOut]
    callees: list[SymbolOut]


class DeadCodeFindingOut(BaseModel):
    symbol: SymbolOut
    reason: str


class ComplexityHotspotOut(BaseModel):
    symbol: SymbolOut
    complexity: int
    line_count: int


class SecurityFindingOut(BaseModel):
    file_path: str
    line: int
    severity: str
    confidence: str
    rule: str
    message: str


class AnalysisOut(BaseModel):
    dead_code: list[DeadCodeFindingOut]
    complexity_hotspots: list[ComplexityHotspotOut]
    security_findings: list[SecurityFindingOut]


class CodeReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=20_000)
    language: str | None = None


class CodeReviewResponse(BaseModel):
    review: str
    mode: str
