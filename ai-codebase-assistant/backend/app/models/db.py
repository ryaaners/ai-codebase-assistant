"""
Relational storage for everything that isn't a vector or a graph:
- Repo: one row per indexed repository, tracks status through the pipeline.
- SymbolRecord: denormalized per-symbol data (signature, docstring, AI
  summary, decorators, complexity) computed once at index time. The graph
  store holds *relationships*; this holds the *facts* the UI displays and
  that dead-code/complexity/security views are built from, so the API
  layer doesn't need to re-parse source on every request.
- SecurityFinding: one row per finding from core/security_scan.py.

SQLite locally (zero config), Postgres in docker-compose (DATABASE_URL) --
same models either way via SQLAlchemy's async engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(16))  # "github" | "zip"
    source: Mapped[str] = mapped_column(Text)  # URL or original filename
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|indexing|ready|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str] = mapped_column(Text)
    primary_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    languages: Mapped[dict] = mapped_column(JSON, default=dict)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SymbolRecord(Base):
    __tablename__ = "symbol_records"
    __table_args__ = (
        # Composite PK, not a bare `id`: symbol ids are content hashes
        # (file+name+kind+line), unique *within* one repo's extraction but
        # not guaranteed unique *across* repos -- re-indexing the same repo
        # or two repos sharing a vendored file can produce the same id.
        # (Caught by literally uploading the same fixture repo twice in
        # testing, which threw a UNIQUE constraint error before this fix.)
        PrimaryKeyConstraint("repo_id", "id"),
        Index("ix_symbol_records_repo_id", "repo_id"),
    )

    id: Mapped[str] = mapped_column(String(32))
    repo_id: Mapped[str] = mapped_column(String(32), ForeignKey("repos.id"))
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(255))
    qualified_name: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(16))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(Text)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decorators: Mapped[list] = mapped_column(JSON, default=list)
    complexity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SecurityFindingRecord(Base):
    __tablename__ = "security_findings"
    __table_args__ = (Index("ix_security_findings_repo_id", "repo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str] = mapped_column(Text)
    line: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(16))
    rule: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
