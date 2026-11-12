# Technical Specification — CodeExplorer

## 1. System Architecture

CodeExplorer is a web application with a backend analysis pipeline and a frontend visualization layer.

Frontend (React + Vite) communicates with Backend (FastAPI) over HTTP APIs.

---

## 2. High-Level Flow

1. User submits a public GitHub repository URL
2. Backend initiates a **Streaming Pipeline** with a unique session ID
3. Repository metadata is fetched via GitHub API
4. Backend clones the repository temporarily using a background task
5. **Concurrent Scanner** watches the clone directory and processes files as they appear
6. Static analysis results are streamed to the client via **Server-Sent Events (SSE)**
7. Deep analysis (call graph, architecture) is performed concurrently after cloning completes
8. AI-generated architecture report is produced as the final stage
9. Results are rendered incrementally on the frontend dashboard
10. Cloned repository is cleaned up after the pipeline finishes

---

## 3. Backend Components

- **Streaming Pipeline**: Orchestrates the analysis lifecycle, broadcasting real-time events via SSE. Manages stages from ingestion to AI reporting.
- **Concurrent Executor**: A `ThreadPoolExecutor` based system that parallelizes file analysis, enabling high-speed scanning of large codebases.
- **Repo Ingestor**: Clones public GitHub repositories using GitPython and returns a temporary path.
- **Repo Scanner**: Performs basic repository scanning and file enumeration.
- **Code Analyzer**: Comprehensive static analysis engine that extracts:
  - Imports and dependencies per file
  - Functions and their signatures
  - Classes and their methods
  - Entry points and key files
  - Language detection (19+ languages supported)
  - Call graph (function-to-function call relationships)
  - File-level dependency graph with circular dependency detection
  - Framework and database detection
- **Architecture Analyzer**: Generates high-level layered architecture diagrams by classifying files into layers.
- **AI Analyzer**: Generates automated architectural summaries and insights using LLMs (Groq API).
- **Streaming Pipeline**: Clones (with live progress), analyzes files in parallel, then runs deep analysis while building the vector index concurrently. Emits batched SSE events with monotonic progress; non-fatal problems are `warning` events, only fatal failures are `error`. Sessions are kept in a TTL-evicted store so clients can reconnect (history is replayed) and search/chat can reuse server-side data.
- **Code Chunker**: Splits source into symbol-level chunks — exact function/class/method boundaries for Python (via `ast`), definition-regex split points for other languages, overlapping windows for oversized segments.
- **Vector Index**: Embeds chunks locally with fastembed (`BAAI/bge-small-en-v1.5`, 384-dim, ONNX, no API key) into an in-memory numpy matrix per session; brute-force cosine search. Searchable incrementally while it builds.
- **Semantic Search Service**: Hybrid retrieval — concept-expanded keyword matching (50+ concept categories) fused with vector similarity via weighted reciprocal rank fusion. Identifier-like queries lean on keywords, natural-language queries lean on vectors; tests/examples are mildly down-ranked unless asked for. Falls back to keyword-only when no index is available.
- **Chat Service (RAG)**: Groq-powered chat (`GROQ_MODEL`, default `openai/gpt-oss-120b`). Each question gets a compact repo overview plus code retrieved for that question by the **RAG Retriever**:
  - explicitly named symbols (`backticks`, snake_case, camelCase, `name()`) and named files (with a symbol outline),
  - vector similarity (follow-ups reuse the previous question),
  - call-graph expansion for "who calls / where is X used" questions (callers' code is pulled in),
  - a character budget, per-file caps, overlap removal and a cap on test/example chunks.
  Answers return their sources (file + line range). Without a live index, chat falls back to whole entry/key files; without any analyzed files it refuses rather than letting the model answer from memory.

---

## 4. Technology Choices

**Backend**
- FastAPI
- GitPython
- Python `ast`
- Groq API (LLM-powered chat)
- fastembed + numpy (local embeddings / vector search)
- CORS middleware

**Frontend**
- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS
- D3.js v7 (force-directed graphs for call graph and file dependencies)
- ReactFlow (architecture diagrams)
- Recharts (bar/pie charts for complexity and statistics)
- Axios (HTTP client)

---

## 5. Data Handling

- No user data is stored
- Analysis data is overwritten per repository
- Repository files are deleted after analysis
- Theme preference is persisted in localStorage
- Chat history is maintained during the session only

---

## 6. API Endpoints

- `GET /api/analyze/stream?repo=&session_id=` — Initiates/reconnects to a streaming analysis session (reconnecting with the same `session_id` replays history). Returns a Server-Sent Event (SSE) stream broadcasting:
  - `clone_progress`, `repo_meta`: Clone progress and GitHub repository data
  - `scan_started`, `file_complexity_batch`: File count, then batched file-level metrics (LOC, functions, classes, imports)
  - `file_tree`: Full repository file structure
  - `language_dist`: Language breakdown
  - `key_files`: Key files and entry points
  - `framework_detected`: Frameworks, databases, and dependencies
  - `file_dependencies`: File-level dependency graph (one event)
  - `call_graph`: Function call graph (one event)
  - `architecture_ready`: ReactFlow architecture data
  - `quickstart_ready`: README, package manager, run scripts
  - `ai_report_ready`: AI-generated architecture summary
  - `search_index_progress` / `search_index_ready`: Vector index build status (runs concurrently)
  - `warning`: Non-fatal problems (analysis continues); `error`: fatal failure; `analysis_complete`: done
- `GET /api/analyze/{session_id}/status` — Pipeline and search-index status for a session.
- `POST /api/analyze` — Legacy endpoint for full analysis (synchronous).
- `POST /api/search` — Hybrid semantic search. Body: `query`, `session_id` (preferred), optional `mode` (`hybrid` | `semantic` | `keyword`), `limit`, and optional `analysis_data` fallback. Returns ranked results with match type, similarity, line range, and code snippet.
- `GET /api/search/status?session_id=` — Vector index status.
- `POST /api/chat` — Retrieval-augmented Q&A. Body: `question`, `session_id` (preferred), optional `chat_history`, optional slim `analysis_data` fallback. Returns `response`, `sources` (`file`, `start_line`, `end_line`, `symbol`, `reason`) and `retrieval` (`semantic` | `files`).
- `GET /api/health` — Health check (reports whether vector search is enabled).

---

## 7. Frontend Features

### Repository Input
- GitHub URL validation (regex-based)
- Example repository suggestions (React, Next.js)
- Loading state and error handling

### Dashboard (Tabbed Interface — 13 Tabs)
1. **AI Report** — Automated architecture overview, key component identification, and codebase insights generated by AI (Stage 4)
2. **Quick Start** — Auto-generated setup and installation guide with language/framework detection, package manager suggestions, install/run commands, Docker/Makefile support, and entry point listing
3. **Chat** — Retrieval-augmented chat with per-answer source chips (GitHub deep links to exact lines), code-block rendering, index status, suggested questions, chat history, rate-limit handling, and retry functionality
4. **Search** — Hybrid vector + keyword code search with index build status, mode toggle (hybrid/semantic/keyword), type filtering, expandable code snippets with line numbers, and GitHub deep links
5. **Architecture** — ReactFlow-based layered architecture diagram with 8 layer types
6. **Call Graph** — Interactive D3.js force-directed graph showing function-to-function call relationships
7. **Complexity** — Recharts bar chart ranking files by complexity (updates incrementally during scan)
8. **Overview** — Repository statistics and language breakdown
9. **File Structure** — Interactive file tree display (available immediately after scan)
10. **Languages** — Language distribution visualization
11. **Dependencies** — Project dependency listing (npm, pip, cargo, go modules)
12. **File Dependencies** — Interactive D3.js graph of file import/export relationships
13. **Key Files** — Highlights important files (README, LICENSE, Dockerfile, etc.)

### Real-time Progress
- Multi-stage progress bar showing current pipeline state (monotonic)
- Human-readable activity log (clone progress, files analyzed, chunks embedded, warnings)
- Incremental data rendering (tabs populate as data arrives)
- Reconnection support for interrupted streams (server replays history; client resets to avoid double counting)

### Global Search Bar
- Searchable index across all files, functions, and classes
- Keyboard shortcut (Ctrl+K) to focus
- Type filtering (files, functions, classes)
- Language-specific file icons
- Smart sorting (exact matches first)

### Theme System (Dark/Light Mode)
- Toggle between dark and light themes
- Persists preference in localStorage
- Respects system color scheme preference
- Smooth CSS transitions

---

## 8. Code Analysis Capabilities

### Language Support
Python, JavaScript, TypeScript, Java, Go, Rust, Ruby, PHP, C#, Swift, Kotlin, Scala, C, C++, Vue, Svelte, and more (19+ extensions mapped)

### Framework Detection
- **Frontend**: React, Vue.js, Angular, Svelte, Next.js, Nuxt.js, Ember.js, Gatsby
- **Backend**: FastAPI, Django, Flask, Express.js, Spring, Spring Boot, ASP.NET, Laravel, Ruby on Rails

### Database Detection
- **SQL**: PostgreSQL, MySQL, SQLite, MariaDB, Oracle
- **NoSQL**: MongoDB, CouchDB, Redis, Elasticsearch, DynamoDB
- **ORM**: SQLAlchemy, Prisma, TypeORM, Sequelize, Hibernate

### Dependency Extraction
- JavaScript/TypeScript: `package.json`
- Python: `requirements.txt`, `Pipfile`, `pyproject.toml`
- Go: `go.mod`
- Rust: `Cargo.toml`

### Entry Point Detection
- Pattern matching on file names (main, app, index, server, etc.)
- Language-specific patterns (manage.py for Django, wsgi.py for Python, etc.)

### Call Graph Analysis
- Extracts function calls across supported languages
- Builds caller/callee relationships
- Shows called_by reverse relationships

### File Dependency Analysis
- Maps file-level import/export relationships
- Resolves relative imports
- Tracks external vs internal dependencies
- Detects circular dependencies
- Builds reverse dependency map

---

## 9. Rate Limiting & Abuse Protection

Per-client sliding-window limits (in-memory, `app/core/rate_limit.py`), configured with `"N/unit"` rules joined by `;`:

| Rule | Default | Applies to |
|------|---------|------------|
| `RATE_LIMIT_ANALYZE` | `3/minute;20/hour` | Starting a **new** analysis (`/api/analyze/stream`, `POST /api/analyze`, `/api/structure`). Reconnecting to an existing session is free. |
| `RATE_LIMIT_CHAT` | `6/minute;100/day` | `POST /api/chat` (the Groq free tier allows 1000 requests/day for the whole server) |
| `RATE_LIMIT_SEARCH` | `60/minute` | `POST /api/search` |
| `MAX_CONCURRENT_ANALYSES` | `3` | Global cap on running analyses (clone + CPU embedding). Checked before the per-client limit, so a "busy" rejection costs no quota. |

- JSON endpoints return **429** with a `Retry-After` header (exposed via CORS). Upstream Groq 429s pass Groq's own `retry-after` through.
- The SSE endpoint returns a single fatal `error` event (`rate_limited: true`, `retry_after`), because `EventSource` cannot read non-200 responses.
- Client identity is the socket address. Behind reverse proxies set `RATE_LIMIT_PROXY_HOPS=N` (the client is taken from the N-th `X-Forwarded-For` entry from the right; left-most entries are spoofable), or run uvicorn with `--forwarded-allow-ips`.
- Limits live in process memory: run a single worker (sessions and vector indexes are in-memory too). `RATE_LIMIT_ENABLED=false` disables limiting.

---

## 10. Non-Functional Requirements

- Free to build and host
- Deterministic and reproducible results
- Read-only access to repositories
- Compatible with free-tier hosting limits
- Responsive UI with dark/light mode support

---

## 11. Limitations

- One repository analyzed at a time
- Public repositories only
- No authentication or persistence across sessions
- Chat context budget is ~14k characters (`CHAT_CONTEXT_CHARS`) because the Groq free tier allows ~8k tokens/minute including the answer
- Chat subject to rate limiting (per-client limits and the shared Groq API quota)
