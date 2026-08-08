# AI Codebase Assistant

Upload a repo (or point it at a public GitHub URL) and ask questions about
how it actually works — in plain language, with answers grounded in a real
parse of the code, not a guess.

```
"Where is authentication implemented?"
"What calls UserService.authenticate_user?"
"Show me functions nothing else in the codebase calls."
```

---

## Why this exists

Understanding an unfamiliar codebase is one of the most common — and most
poorly-tooled — problems in software engineering. `grep` finds matching
text; it doesn't know that `login()` calls `AuthService.authenticate_user()`
two files away. This project builds the thing `grep` can't be: a static
parse of the codebase (via tree-sitter), a real call/import/inheritance
graph built from that parse, and a retrieval-augmented chat layer on top,
so answers can point at exact files and line numbers instead of sounding
plausible.

## Architecture

```
 GitHub URL / ZIP upload
          │
   ingestion (clone / unzip, walk files)
          │
   tree-sitter parse  ──────────────────────────┐
          │                                     │
   extractor.py                          security_scan.py
   (functions, classes,                  (bandit + heuristics)
    imports, call sites)
          │
   graph_builder.py
   (resolves call/import names → a whole-repo graph)
          │
   ┌──────┴──────┐
   ▼             ▼
 graph store   embeddings ──▶ vector store
 (calls,       (hashing or    (symbol text
  imports,      OpenAI)        + summary)
  inherits)
   │             │
   └──────┬──────┘
          ▼
   rag.py (question → vector search → graph
           expansion → LLM → cited answer)
          │
          ▼
   FastAPI  ──────▶  React (chat / file explorer /
                      dependency graph / analysis)
```

Every storage layer is behind an interface with two implementations: an
in-memory one (zero setup, what you get running the backend directly) and
a production one (Postgres+pgvector, Neo4j) used by `docker compose up`.
See [Design notes](#design-notes) for why.

## What's implemented

| Feature | Status |
|---|---|
| Repo import (GitHub URL clone, ZIP upload) | ✅ |
| Static parsing — Python, JavaScript, TypeScript, TSX | ✅ |
| Function/class/interface/import/call extraction | ✅ |
| Cross-file call graph, import graph, inheritance graph | ✅ |
| Dependency graph visualization (symbol-level and file-level) | ✅ |
| Semantic + graph-expanded chat (RAG) with citations | ✅ |
| AI-generated function/class summaries (batched, cached) | ✅ |
| Dead code detection (with entrypoint heuristics) | ✅ |
| Cyclomatic complexity hotspots | ✅ |
| Security scanning (real bandit for Python + heuristics elsewhere) | ✅ |
| Code review assistant (paste code, get feedback) | ✅ |
| Background indexing (in-process by default, Celery+Redis optional) | ✅ |
| Docker Compose (Postgres+pgvector, Neo4j, Redis, backend, worker, frontend) | ✅ written, ⚠️ see below |
| Multi-agent orchestration (LangGraph-style planner/retriever/synthesizer) | ❌ not built |
| GitHub webhook auto re-index on push, PR diff explanation | ❌ not built |
| Natural-language refactoring (generate a patch from a request) | ❌ not built |
| Semgrep-grade multi-language security scanning | ❌ Python only; other languages get a regex fallback |

The four ❌ rows were in the original spec's "stretch features" section.
Cutting them was a deliberate scope call, not an oversight — better to ship
a smaller set of things that actually work than a longer list of things
that don't. They're reasonably clean extension points; see below.

## Quick start

**Zero dependencies** (in-memory graph/vector store, no API key, nothing
to install beyond Python/Node):

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# in another terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Upload a ZIP or paste a GitHub URL — indexing,
search, the dependency graph, dead-code/complexity detection, and Python
security scanning all work immediately. Chat falls back to showing raw
search results ("extractive mode") until you add an LLM key.

**Full stack** (Postgres+pgvector, Neo4j, Redis+Celery, generated chat
answers):

```bash
cp .env.example .env
# edit .env, at minimum set ANTHROPIC_API_KEY
docker compose up --build
```

Frontend on `http://localhost:5173`, API on `http://localhost:8000` (interactive
docs at `/docs`), Neo4j browser at `http://localhost:7474`.

> **Honesty note on docker-compose.yml:** this sandbox couldn't run nested
> Docker, so the individual pieces (backend against a real local Postgres
> +pgvector I compiled and ran directly, the Anthropic client against the
> real API, the frontend build/serve) are genuinely tested — but the exact
> multi-container `docker compose up` orchestration, and the Neo4j graph
> store specifically, are not. Both were written carefully against
> documented APIs and I'd expect them to work, but "I'd expect" isn't
> "I confirmed," and I'd rather tell you that directly than have you
> discover it. If `docker compose up` hits a snag, it's most likely a
> service dependency/timing issue, not a logic error — the same
> `index_repository()` pipeline runs identically in both modes.

## Configuration

Every setting has a working default (see `backend/app/config.py`);
`.env.example` documents all of them. The one you'll actually want to set
is `ANTHROPIC_API_KEY` — everything else (which storage backend, which
embedding provider, Celery on/off) is an infrastructure choice with a
sensible default.

## Testing

```bash
cd backend
pip install -r requirements.txt
pytest -v
```

24 tests, no external services required — they run against the in-memory
graph/vector stores and a `HashingEmbedder`, with a `RecordingFakeLLM`
standing in for the network-dependent Anthropic path. Coverage includes:
tree-sitter extraction correctness (Python and TS, verified against real
parse trees rather than assumed node names), cross-file call/import
resolution, a 4-hop call-chain traversal, dead-code entrypoint heuristics,
a cyclomatic-complexity regression test (an earlier version silently gave
every method in a class the same wrong score — pinned so it can't come
back), summarizer batching/fallback behavior, the full RAG assembly
pipeline, and cross-repo ID isolation (symbol IDs are content hashes, not
globally unique — two repos with overlapping IDs must not collide).

`PgVectorStore` was additionally tested against a real local Postgres+pgvector
(compiled from source) during development — see git history / build notes —
but that's not part of the automated suite since it needs a live Postgres.

## Design notes

A few decisions worth knowing about if you're using this as an interview
talking point (which, per the original brief, was the point):

- **Pluggable storage, not a hard dependency on infra.** `VectorStore` and
  `GraphStore` are both ABCs with an in-memory implementation and a
  production one. This wasn't just convenience — it's what makes the test
  suite fast and CI-independent, and what lets someone try the product
  with zero setup before committing to running four extra containers.
- **Name-based call resolution, with confidence labels, not a type
  checker.** Resolving `x.save()` to a specific `Symbol` without full
  semantic analysis is inherently heuristic. Every `CALLS`/`INHERITS` edge
  is tagged `exact` / `same_file` / `heuristic` depending on how much
  disambiguation was needed, so the graph is honest about its own
  confidence instead of presenting a guess as a fact.
- **Dead code detection layers entrypoint heuristics on a raw graph
  signal**, because "zero incoming calls" alone flags every route handler,
  constructor, and test function as dead. Same category of tradeoff real
  tools (vulture, ts-prune) make.
- **Graceful LLM degradation.** With no API key, chat still returns ranked
  search results instead of failing; AI doc summaries fall back to
  signature+docstring. The system is useful before it's "smart," and
  doesn't hard-fail when a key is missing.
- **The embedder is a hashing/n-gram scheme, not a trained model** — no
  multi-GB download, works offline, and is honestly documented as a
  lexical proxy for semantics rather than the real thing. It was
  specifically tuned during development after a real test query
  ("authentication") failed to retrieve `authenticate_user` under naive
  whole-token hashing; character n-grams fixed it. Swap in a real
  embedding model (`OpenAIEmbedder` is included) for production semantic
  quality.

## Known limitations

- Call/inheritance resolution is name-based (see above) — a large repo
  with many same-named functions across files will produce more
  `heuristic`-confidence edges.
- Dead-code detection can't see calls that happen outside the indexed
  repo (a library's public API, dynamic dispatch, string-based routing).
- Security scanning is real (bandit) for Python; other languages get a
  small, explicitly-labeled regex fallback, not a Semgrep-grade scan.
- Neo4j support is implemented against the documented driver API but not
  live-tested in this build (see the honesty note above).
- Tree-sitter grammars are wired up for Python, JavaScript, TypeScript,
  and TSX. Adding a language means installing its `tree-sitter-<lang>`
  package and writing one extraction adapter in `extractor.py` — the
  parser/graph/storage layers don't need to change.

## Tech stack

Python, FastAPI, SQLAlchemy (async), tree-sitter, NetworkX, Neo4j, Postgres
+ pgvector, Redis, Celery, Anthropic/OpenAI SDKs, bandit — React 19,
TypeScript, Vite, Tailwind v4, `@xyflow/react`, Monaco Editor — Docker
Compose.

## License

MIT.
