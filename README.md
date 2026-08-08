# AI Codebase Assistant

An AI-powered developer tool that helps engineers understand unfamiliar codebases through **static code analysis**, **hybrid RAG**, and **dependency-graph reasoning**.

Upload a ZIP file or provide a public GitHub repository, then ask questions such as:

- "Where is authentication implemented?"
- "What calls `UserService.authenticate_user`?"
- "Which functions are not called anywhere?"
- "Explain the flow from the API endpoint to the database."
- "Which files have the highest cyclomatic complexity?"

The assistant grounds responses in the indexed source code and provides file and symbol references rather than relying only on an LLM's general knowledge.

---

## Features

| Feature | Description |
|---|---|
| Repository Import | Import repositories from public GitHub URLs or ZIP uploads |
| Multi-Language Parsing | Parse Python, JavaScript, TypeScript, and TSX with Tree-sitter |
| Code Structure Extraction | Extract functions, classes, interfaces, imports, and call sites |
| Dependency Graph | Build symbol-level call, import, and inheritance relationships |
| Hybrid RAG | Combine vector retrieval with graph-based context expansion |
| Source Citations | Return file and symbol references with generated answers |
| AI Summarization | Generate summaries for functions and classes |
| Dead Code Detection | Identify potentially unused functions using graph analysis and entrypoint heuristics |
| Complexity Analysis | Detect functions with high cyclomatic complexity |
| Security Analysis | Run Bandit for Python and additional heuristic checks for other supported languages |
| Code Review | Submit code snippets and receive AI-assisted review feedback |
| Background Indexing | Support asynchronous indexing with Celery and Redis |
| Multiple Storage Backends | Use in-memory stores for development/testing or PostgreSQL/pgvector and Neo4j for production-style deployment |
| Docker Deployment | Run the full application stack with Docker Compose |

---

## Architecture

```text
                         GitHub URL / ZIP
                                │
                                ▼
                       ┌─────────────────┐
                       │    Ingestion    │
                       │ Clone / Unzip   │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │   Tree-sitter   │
                       │  AST Parsing    │
                       └────────┬────────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
          Symbol Extraction  Call Graph   Security Scan
                 │              │              │
                 └──────────────┼──────────────┘
                                ▼
                    ┌─────────────────────┐
                    │  Indexing Pipeline  │
                    └──────────┬──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │ Vector Storage  │         │  Graph Storage  │
        │ pgvector        │         │     Neo4j       │
        └────────┬────────┘         └────────┬────────┘
                 │                           │
                 └─────────────┬─────────────┘
                               ▼
                    ┌─────────────────────┐
                    │    Hybrid RAG       │
                    │ Vector Search +      │
                    │ Graph Expansion     │
                    └──────────┬──────────┘
                               │
                               ▼
                         ┌────────────┐
                         │    LLM     │
                         └─────┬──────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     FastAPI API     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    React Frontend   │
                    │ Chat / Graph / Code  │
                    │ Analysis / Explorer  │
                    └─────────────────────┘
```

### Retrieval Pipeline

When a user asks a question, the system:

1. Converts the question into a searchable representation.
2. Retrieves relevant code symbols from the vector store.
3. Expands the retrieved context using call/import relationships from the dependency graph.
4. Sends the combined context to the configured LLM.
5. Produces a grounded response with source references.

This allows the system to reason about both **semantic similarity** and **relationships between code elements**.

---

## Supported Languages

The parser currently supports:

- Python
- JavaScript
- TypeScript
- TSX

Tree-sitter provides the AST representation used by the extraction and analysis pipeline.

Adding another language primarily requires a language grammar and an extraction adapter while leaving the retrieval and storage layers unchanged.

---

## Tech Stack

### Backend

- Python
- FastAPI
- SQLAlchemy
- Tree-sitter
- NetworkX
- Celery
- Redis

### AI / Retrieval

- Anthropic SDK
- OpenAI SDK
- RAG
- Vector search
- LLM-generated code summaries
- Graph-based context expansion

### Databases

- PostgreSQL
- pgvector
- Neo4j

### Frontend

- React 19
- TypeScript
- Vite
- Tailwind CSS
- React Flow
- Monaco Editor

### Development & Deployment

- Docker
- Docker Compose
- Pytest
- Git

---

## Project Structure

```text
ai-codebase-assistant/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   └── worker/
│   │
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pytest.ini
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   ├── styles/
│   │   └── types/
│   ├── Dockerfile
│   └── package.json
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Getting Started

### Option 1: Local Development

The application can run without external databases using the in-memory graph and vector stores.

#### Backend

```bash
cd backend

pip install -r requirements.txt

uvicorn app.main:app --reload
```

#### Frontend

In a second terminal:

```bash
cd frontend

npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The FastAPI documentation is available at:

```text
http://localhost:8000/docs
```

Without an LLM API key, the application can still perform indexing and retrieval and return ranked search results.

---

## Option 2: Docker Compose

For the full infrastructure stack:

```bash
cp .env.example .env
```

Configure the required environment variables, then run:

```bash
docker compose up --build
```

The stack is designed to include:

- React frontend
- FastAPI backend
- PostgreSQL + pgvector
- Neo4j
- Redis
- Celery worker

Default endpoints:

| Service | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| FastAPI | `http://localhost:8000` |
| API Docs | `http://localhost:8000/docs` |
| Neo4j Browser | `http://localhost:7474` |

---

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

The application supports configurable:

- LLM provider
- API credentials
- Vector storage backend
- Graph storage backend
- Embedding provider
- Celery/Redis settings
- Database configuration

Never commit a real `.env` file or API credentials.

---

## Testing

Run the test suite with:

```bash
cd backend
pytest -v
```

The project includes **24 automated tests** covering:

- Tree-sitter extraction
- Python and TypeScript parsing
- Cross-file call resolution
- Import resolution
- Call-chain traversal
- Dead-code detection
- Cyclomatic complexity
- AI summarization behavior
- RAG pipeline assembly
- Cross-repository ID isolation

The automated tests use the in-memory graph/vector implementations and a fake LLM, so they do not require external services.

---

## Engineering Decisions

### Hybrid Retrieval

Pure vector search can retrieve code that is semantically similar without understanding how that code interacts with the rest of the application.

The assistant combines:

```text
Vector Search
     +
Graph Traversal
     ↓
Relevant Code Context
```

For example, retrieving `authenticate_user()` can be followed by graph relationships to identify its callers, dependencies, and related symbols.

### Pluggable Storage

Graph and vector storage are abstracted behind interfaces with both in-memory and external implementations.

This provides:

- Fast tests
- No infrastructure requirement for local development
- Easier CI execution
- A path toward production infrastructure

### Confidence-Aware Graph Relationships

Code relationships can be difficult to resolve without a full compiler/type system.

Graph relationships therefore include confidence levels such as:

```text
exact
same_file
heuristic
```

This avoids presenting heuristic relationships as guaranteed facts.

### Graceful LLM Degradation

The application remains usable without an LLM API key.

Without an LLM, retrieval can still return ranked code results, while AI-generated summaries fall back to available code metadata.

---

## Known Limitations

- Call and inheritance resolution is currently name-based rather than full compiler-level semantic analysis.
- Dynamic dispatch and calls outside the indexed repository may not be detected.
- Dead-code analysis uses heuristics and cannot identify every runtime entry point.
- Python security scanning uses Bandit; other supported languages use additional heuristic checks rather than a full Semgrep-style analysis.
- The included Neo4j and full multi-container Docker Compose configuration were implemented but were not fully live-tested in the development environment.
- The default hashing/n-gram embedder is a lightweight lexical approach rather than a trained semantic embedding model. A production embedding provider can be configured instead.

These limitations are intentionally documented rather than hidden behind a demo.

---

## Future Improvements

Potential extensions include:

- Multi-agent planning and retrieval with LangGraph
- Automatic GitHub re-indexing through webhooks
- Pull request diff analysis
- Natural-language code refactoring with generated patches
- Additional programming language parsers
- Improved neural embedding models and reranking
- Retrieval evaluation using Recall@K, MRR, and citation accuracy
- More advanced multi-language security analysis

---

## License

MIT
