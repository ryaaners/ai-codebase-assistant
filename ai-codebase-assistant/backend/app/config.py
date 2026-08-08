from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage backends -------------------------------------------------
    # "memory" needs nothing external and is the default so the app runs
    # immediately after `pip install -r requirements.txt`. Switch to the
    # real backends (used by docker-compose.yml) for persistence and scale.
    vector_provider: str = "memory"  # memory | pgvector
    graph_provider: str = "memory"  # memory | neo4j

    postgres_dsn: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/codebase_assistant"
    # Relational metadata (repo status, cached symbol/security data) is
    # separate from the vector store DSN above so local dev can run on
    # zero-config SQLite while docker-compose points both at the same
    # Postgres instance -- one extension (pgvector), two schemas.
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # --- Background indexing ----------------------------------------------
    use_celery: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # --- Local storage of cloned/uploaded repos ----------------------------
    repo_storage_path: str = "./data/repos"

    # --- LLM (answer generation + doc summaries) ---------------------------
    llm_provider: str = "anthropic"  # anthropic | openai | none
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # --- Embeddings ----------------------------------------------------------
    embedding_provider: str = "hashing"  # hashing | openai
    embedding_dim: int = 512

    # --- Indexing limits -----------------------------------------------------
    max_file_size_bytes: int = 500_000
    max_files_per_repo: int = 20_000

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
