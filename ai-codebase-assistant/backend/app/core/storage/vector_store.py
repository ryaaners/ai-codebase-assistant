"""
Vector storage behind an interface with two implementations:

- InMemoryVectorStore: numpy, process-local, gone on restart. Zero setup,
  used by default and in tests.
- PgVectorStore: Postgres + the pgvector extension, for persistence and
  repos too large to hold comfortably in memory. Used by docker-compose.yml.

Same contract either way: upsert chunks with a repo/file scope, similarity-
search within a repo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class VectorRecord:
    id: str  # matches a Symbol.id from extractor.py, or a synthetic chunk id
    repo_id: str
    file_path: str
    symbol_id: str | None
    kind: str  # "function" | "method" | "class" | "interface" | "doc"
    name: str
    text: str  # the text that was embedded (signature + docstring/summary)
    embedding: list[float]
    start_line: int
    end_line: int


@dataclass
class ScoredRecord:
    record: VectorRecord
    score: float


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    async def search(self, repo_id: str, query_embedding: list[float], top_k: int = 8) -> list[ScoredRecord]: ...

    @abstractmethod
    async def delete_repo(self, repo_id: str) -> None: ...

    @abstractmethod
    async def count(self, repo_id: str) -> int: ...


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


@dataclass
class InMemoryVectorStore(VectorStore):
    _by_repo: dict[str, dict[str, VectorRecord]] = field(default_factory=dict)

    async def upsert(self, records: list[VectorRecord]) -> None:
        for r in records:
            bucket = self._by_repo.setdefault(r.repo_id, {})
            bucket[r.id] = r

    async def search(self, repo_id: str, query_embedding: list[float], top_k: int = 8) -> list[ScoredRecord]:
        bucket = self._by_repo.get(repo_id, {})
        if not bucket:
            return []
        q = np.array(query_embedding, dtype=np.float32)
        scored = [
            ScoredRecord(record=r, score=_cosine_sim(q, np.array(r.embedding, dtype=np.float32)))
            for r in bucket.values()
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    async def delete_repo(self, repo_id: str) -> None:
        self._by_repo.pop(repo_id, None)

    async def count(self, repo_id: str) -> int:
        return len(self._by_repo.get(repo_id, {}))


class PgVectorStore(VectorStore):
    """Postgres + pgvector. Schema is created by db/init.sql (see
    docker-compose.yml, which runs it automatically on first boot of the
    postgres container) or by calling `ensure_schema()` once at startup."""

    def __init__(self, dsn: str, dimension: int):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        self._dimension = dimension
        self._engine = create_async_engine(dsn, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def ensure_schema(self) -> None:
        from sqlalchemy import text

        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS symbol_embeddings (
                        id TEXT NOT NULL,
                        repo_id TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        symbol_id TEXT,
                        kind TEXT NOT NULL,
                        name TEXT NOT NULL,
                        text TEXT NOT NULL,
                        start_line INTEGER NOT NULL,
                        end_line INTEGER NOT NULL,
                        embedding vector({self._dimension}),
                        PRIMARY KEY (repo_id, id)
                    )
                    """
                    # Composite PK, not just `id`: symbol ids are content
                    # hashes (file+name+kind+line), which are only unique
                    # *within* one repo's extraction -- re-indexing the same
                    # repo, or two different repos sharing a vendored file,
                    # can legitimately produce the same id. A bare-id PK
                    # would throw a duplicate-key error the second time
                    # (caught during testing by literally uploading the same
                    # fixture repo twice).
                )
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS symbol_embeddings_repo_idx ON symbol_embeddings (repo_id)")
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS symbol_embeddings_ivfflat_idx "
                    "ON symbol_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
                )
            )

    async def upsert(self, records: list[VectorRecord]) -> None:
        from sqlalchemy import text

        if not records:
            return
        stmt = text(
            """
            INSERT INTO symbol_embeddings
                (id, repo_id, file_path, symbol_id, kind, name, text, start_line, end_line, embedding)
            VALUES
                (:id, :repo_id, :file_path, :symbol_id, :kind, :name, :text, :start_line, :end_line, :embedding)
            ON CONFLICT (repo_id, id) DO UPDATE SET
                file_path = EXCLUDED.file_path, kind = EXCLUDED.kind, name = EXCLUDED.name,
                text = EXCLUDED.text, start_line = EXCLUDED.start_line, end_line = EXCLUDED.end_line,
                embedding = EXCLUDED.embedding
            """
        )
        async with self._session_factory() as session:
            for r in records:
                await session.execute(
                    stmt,
                    {
                        "id": r.id, "repo_id": r.repo_id, "file_path": r.file_path,
                        "symbol_id": r.symbol_id, "kind": r.kind, "name": r.name, "text": r.text,
                        "start_line": r.start_line, "end_line": r.end_line,
                        "embedding": str(r.embedding),
                    },
                )
            await session.commit()

    async def search(self, repo_id: str, query_embedding: list[float], top_k: int = 8) -> list[ScoredRecord]:
        from sqlalchemy import text

        stmt = text(
            """
            SELECT id, repo_id, file_path, symbol_id, kind, name, text, start_line, end_line,
                   1 - (embedding <=> :query) AS score
            FROM symbol_embeddings
            WHERE repo_id = :repo_id
            ORDER BY embedding <=> :query
            LIMIT :top_k
            """
        )
        async with self._session_factory() as session:
            result = await session.execute(
                stmt, {"repo_id": repo_id, "query": str(query_embedding), "top_k": top_k}
            )
            rows = result.mappings().all()
        return [
            ScoredRecord(
                record=VectorRecord(
                    id=row["id"], repo_id=row["repo_id"], file_path=row["file_path"],
                    symbol_id=row["symbol_id"], kind=row["kind"], name=row["name"], text=row["text"],
                    embedding=[], start_line=row["start_line"], end_line=row["end_line"],
                ),
                score=float(row["score"]),
            )
            for row in rows
        ]

    async def delete_repo(self, repo_id: str) -> None:
        from sqlalchemy import text

        async with self._session_factory() as session:
            await session.execute(text("DELETE FROM symbol_embeddings WHERE repo_id = :r"), {"r": repo_id})
            await session.commit()

    async def count(self, repo_id: str) -> int:
        from sqlalchemy import text

        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM symbol_embeddings WHERE repo_id = :r"), {"r": repo_id}
            )
            return int(result.scalar_one())


_vector_store_cache: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store_cache
    if _vector_store_cache is not None:
        return _vector_store_cache

    from app.config import get_settings

    settings = get_settings()
    if settings.vector_provider == "pgvector":
        _vector_store_cache = PgVectorStore(settings.postgres_dsn, settings.embedding_dim)
    else:
        _vector_store_cache = InMemoryVectorStore()
    return _vector_store_cache
