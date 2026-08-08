"""
Embeddings are behind an interface so the storage layer never knows which
provider produced a vector -- it just gets back a fixed-length list[float].

Two implementations ship:

- HashingEmbedder: pure numpy, no network calls, no model download. Uses
  the feature-hashing trick (à la Vowpal Wabbit) over code identifiers,
  keywords, and docstring tokens, TF-weighted and L2-normalized, then
  smoothed with a random projection so nearby tokens land in overlapping
  dimensions instead of one-hot slots. This is the default -- it's what
  makes `docker compose up` (or even just `uvicorn app.main:app`) produce
  a working semantic search with no API keys and no multi-GB model
  download. It rewards shared identifiers and words, which is a
  surprisingly strong signal for code search specifically (a call to
  `authenticate_user` and a question about "authentication" already share
  the token `auth*`-ish surface area).
- OpenAIEmbedder: calls a real embedding model over HTTP for production use.
  Requires OPENAI_API_KEY. Swap in Voyage AI, Cohere, or a local
  sentence-transformers model the same way -- implement EmbeddingProvider
  and register it in `get_embedder()`.

Both providers must agree on `dimension` at index time; changing providers
after indexing a repo requires re-indexing (embeddings from different
providers aren't comparable).
"""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")


def _split_identifier(token: str) -> list[str]:
    """Splits camelCase / snake_case / PascalCase identifiers into words,
    so `authenticateUser` contributes both "authenticate" and "user"."""
    token = token.replace("_", " ")
    token = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token)
    return [w.lower() for w in token.split() if w]


def tokenize_code(text: str) -> list[str]:
    words: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        words.extend(_split_identifier(raw))
    return [w for w in words if len(w) > 1]


class EmbeddingProvider(ABC):
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch-embeds strings, returning one vector per input, in order."""


@dataclass
class HashingEmbedder(EmbeddingProvider):
    dimension: int = 512
    _seed: int = 1337

    def __post_init__(self) -> None:
        # A fixed random projection matrix (token-hash-bucket -> dense dims)
        # makes semantically-unrelated tokens partially overlap in a
        # reproducible way instead of every token getting an orthogonal
        # one-hot slot, which otherwise makes cosine similarity almost
        # useless outside of exact-token overlap.
        n_buckets = 4096
        rng = np.random.default_rng(self._seed)
        self._projection = rng.normal(size=(n_buckets, self.dimension)).astype(np.float32)
        self._n_buckets = n_buckets

    def _bucket(self, token: str) -> int:
        h = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(h, "little") % self._n_buckets

    def _weighted_buckets(self, text: str) -> dict[int, float]:
        """Whole tokens get full weight; character 4-grams of each token get
        partial weight. The n-grams are what let "authentication" (in a
        question) and "authenticate" (in a function name) land in
        overlapping buckets despite being different words -- pure whole-
        token hashing missed this exact case in testing (a query about
        "authentication" failed to retrieve `authenticate_user`), which is
        the flagship example query for this product, so it was worth fixing
        rather than footnoting."""
        weights: dict[int, float] = {}
        for tok in tokenize_code(text):
            weights[self._bucket("w:" + tok)] = weights.get(self._bucket("w:" + tok), 0.0) + 1.0
            if len(tok) > 4:
                for i in range(len(tok) - 3):
                    gram = tok[i : i + 4]
                    b = self._bucket("g:" + gram)
                    weights[b] = weights.get(b, 0.0) + 0.25
        return weights

    def _embed_one(self, text: str) -> list[float]:
        weights = self._weighted_buckets(text)
        if not weights:
            return [0.0] * self.dimension
        vec = np.zeros(self.dimension, dtype=np.float32)
        for bucket, weight in weights.items():
            tf = (1.0 + np.log(weight)) if weight >= 1.0 else weight
            vec += tf * self._projection[bucket]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class OpenAIEmbedder(EmbeddingProvider):
    """Production option: real embedding model over HTTP. Not exercised in
    this build's automated tests (no network access to api.openai.com from
    this sandbox) -- reviewed carefully instead. Swap the base_url/model to
    point at any OpenAI-compatible embeddings endpoint (Voyage, local
    Ollama, etc.)."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dimension: int = 1536):
        import httpx

        self.dimension = dimension
        self._model = model
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.post(
            "/embeddings", json={"model": self._model, "input": texts, "dimensions": self.dimension}
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]


_embedder_cache: EmbeddingProvider | None = None


def get_embedder() -> EmbeddingProvider:
    global _embedder_cache
    if _embedder_cache is not None:
        return _embedder_cache

    from app.config import get_settings

    settings = get_settings()
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        _embedder_cache = OpenAIEmbedder(settings.openai_api_key, dimension=settings.embedding_dim)
    else:
        _embedder_cache = HashingEmbedder(dimension=settings.embedding_dim)
    return _embedder_cache
