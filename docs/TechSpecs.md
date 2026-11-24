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
- **Code Chunker**: Splits source into symbol-level chunks along tree-sitter symbols (doc comments included; large classes/components split into members), with `ast`/regex fallbacks and overlapping windows for oversized segments.
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
- tree-sitter (Python, JS/TS, Java, Rust, C/C++ parsing)
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

- `GET /api/analyze/stream?repo=&session_id=` — Initiates/reconnects to a streaming analysis session (reconnecting with the same `session_id` replays history). `repo` may be any GitHub repo link (`http`, `www.`, `.git`, `/tree/<ref>/...`); it is normalized to `https://github.com/<owner>/<repo>`, and anything else is rejected with a single fatal `error` event. `session_id`, when given, must be a canonical UUID (otherwise the same fatal `error` event). Returns a Server-Sent Event (SSE) stream broadcasting:
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
- `POST /api/search` — Hybrid semantic search. Body: `query`, `session_id` (preferred), optional `mode` (`hybrid` | `semantic` | `keyword`), `limit`, and optional `analysis_data` fallback. Returns ranked results with match type, similarity, line range, and code snippet.
- `GET /api/search/status?session_id=` — Vector index status.
- `POST /api/chat` — Retrieval-augmented Q&A. Body: `question`, `session_id` (preferred), optional `chat_history` (`user` / `assistant` messages; other roles are ignored), optional slim `analysis_data` fallback. Returns `response`, `sources` (`file`, `start_line`, `end_line`, `symbol`, `reason`) and `retrieval` (`semantic` | `files`).
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
**First-class (tree-sitter parsing):** Python, JavaScript/JSX, TypeScript/TSX, Java, Rust, C/C++
(`.py .pyi .js .jsx .mjs .cjs .ts .tsx .mts .cts .java .rs .c .h .cc .cpp .cxx .hpp .hh .hxx .ipp`).
For these, `source_parser.py` extracts with real parsers rather than regexes:
- Symbols with exact line ranges, extended to include decorators, attributes and doc comments:
  - functions, methods, classes, structs, interfaces, traits, enums, records, macros
  - C++ out-of-class definitions (`void Box::put()`), Rust `impl` blocks, nested functions
- Structured imports: Python relative levels, JS `import`/`require`/`import()`/re-exports, Java static/wildcard imports, Rust `use` trees and `mod` declarations, C/C++ `#include "…"` vs `<…>`
- Call sites per function with their qualifier (`Type::new`, `self.x()`, `obj.method()`, JSX `<Component/>`, `new Foo()`)
- Entry points: `if __name__ == "__main__"`, `public static void main`, `fn main`, `int main`, `createRoot(…)`, `app.listen(…)`

**Basic (regex):** Go, Ruby, PHP, C#, Swift, Kotlin, Scala, Vue, Svelte. Tree-sitter missing → all languages fall back to the regex/`ast` analysis.

### File Dependency Analysis (`import_resolver.py`)
- **Python:** dotted modules (src-layout aware), relative imports (`from ..core import X`), submodule imports (`from pkg import mod`)
- **JS/TS:**
  - relative paths with extension probing, including TS ESM `./x.js` → `x.ts`
  - index files
  - tsconfig/jsconfig `baseUrl` + `paths` (JSONC)
  - monorepo workspace packages
- **Java:** fully-qualified names via each file's `package`; static and wildcard imports; same-package type references (no import needed)
- **Rust:**
  - `mod foo;` → `foo.rs` / `foo/mod.rs`
  - `use crate::/self::/super::` paths
  - other crates in the same Cargo workspace
- **C/C++:** `#include "…"` relative to the file, then by path suffix; `<…>` only when it matches a project header (e.g. `<fmt/core.h>`)
- Unresolved imports are listed as external. The graph also detects circular dependencies and builds a reverse dependency map.

### Call Graph Analysis
- Edges come from parsed call sites, resolved in this order:
  1. same file / same class for `self`/`this`
  2. the qualifying type (`Config::new` → `impl Config`) or module/package (`click.echo` → `click/`)
  3. imported files, including what barrel files (`__init__.py`, `index.ts`, `mod.rs`, `lib.rs`) re-export
  4. otherwise only unambiguous matches, so common names don't fan out into false edges
- Cross-boundary tracing: frontend `fetch`/`axios` → backend routes for:
  - Express, FastAPI, Flask, Django, Spring
  - Actix Web, Rocket, Axum
- DB query hints

### Dependency Extraction (`project_manifests.py`)
- **Python:** `requirements*.txt`, `pyproject.toml`, `Pipfile`, `setup.cfg`, `setup.py`
  - `pyproject.toml` covers PEP 621, PEP 735 groups, Poetry, PDM and uv
- **JavaScript/TypeScript:** every `package.json`
- **Java/Kotlin:**
  - `pom.xml`: dependencies, parent, plugins
  - `build.gradle(.kts)`: configurations + plugins
  - `gradle/libs.versions.toml`
- **Rust:** every `Cargo.toml`, including workspace, dev, build and target-specific dependencies
- **C/C++:**
  - `CMakeLists.txt`: `find_package`, `FetchContent`, CPM, `pkg_check_modules`
  - `conanfile.txt/.py`, `vcpkg.json`, `meson.build`
- **Go:** `go.mod`

### Build & Run Commands (Quick Start)
For every project root (nested roots of the same ecosystem collapse into the top one; test/example dirs are skipped), `build_systems` lists install / build / run / test commands, ordered by how much code each build covers:
- **Python:** uv / Poetry / PDM / pipenv / pip (from lockfiles). Run target, first match wins:
  1. Django `manage.py`
  2. `[project.scripts]`
  3. FastAPI → `uvicorn module:app`
  4. Flask
  5. Streamlit
  6. `python -m pkg`
  7. a `__main__` file
- **JS/TS:** npm / pnpm / yarn / bun from lockfiles; `dev`/`start`/`build`/`test` scripts
- **Rust:** `cargo build/run/test`; workspaces use `--workspace` and `cargo run -p <bin crate>`
- **Java:** `./mvnw` or `./gradlew` when present; `spring-boot:run` / `bootRun` / `quarkus:dev` / Gradle `application` run; Android `assembleDebug`
- **C/C++:**
  - CMake configure + build; conan / vcpkg toolchains
  - `ctest` when tests are registered
  - run target = the first non-test `add_executable`
  - meson, make
- **Go:** `go run .` / `./cmd/<app>`

### Framework Detection
- **Frontend:**
  - JS: React, Next.js, Vue.js, Nuxt.js, Angular, Svelte/SvelteKit, Remix, Astro, SolidJS, React Native/Expo, Vite, Tailwind CSS
  - Rust: Tauri, Leptos, Yew, Dioxus, egui, Bevy
  - Java: JavaFX, Android, Jetpack Compose
  - C++: Qt, Dear ImGui, wxWidgets, SDL, SFML, GLFW
  - Unreal Engine
  - Python: Streamlit, Gradio, Dash
- **Backend:**
  - Python: FastAPI, Django, Flask, aiohttp, Tornado, Sanic, Litestar, Celery
  - JS: Express.js, NestJS, Koa, Hapi, Fastify, Hono
  - Java: Spring / Spring Boot, Quarkus, Micronaut, Vert.x, Javalin, Jakarta EE
  - Rust: Actix Web, Axum, Rocket, Warp, Tokio, tonic
  - C++: Drogon, Crow, oat++, Pistache, Boost
  - Go: Gin, Fiber, Echo
  - Ruby on Rails, Laravel
- Backends and databases are detected from **runtime** dependencies only. A server framework that appears only in devDependencies (e.g. a test server) doesn't count. Ecosystems without source files in the repo are ignored.

### Database Detection
- **SQL:** PostgreSQL, MySQL/MariaDB, SQLite, H2, Oracle
- **NoSQL / KV:** MongoDB, Redis, Elasticsearch, RocksDB, LevelDB, Sled, Firebase, Supabase
- **Sources:**
  - npm / PyPI / Maven / crates.io drivers
  - C++ libraries (libpqxx, hiredis, …)
  - Prisma schemas
  - sqlx/diesel feature flags
  - docker-compose and `.env` files

### Entry Point Detection
- **Strong signals:**
  - parsed `main` functions / `__main__` guards
  - Rust crate roots (`src/main.rs`, `src/lib.rs`, `src/bin/*`)
  - Django / WSGI / ASGI files
  - `package.json` `main`/`module`/`bin`
  - `pyproject` `[project.scripts]`
- **Name conventions** (`index`, `app`, `server`, …) only for JS/TS/Python/Go-style projects, and never inside tests/examples.
- **Order:** application code first, then tests/examples.

### Tests
`server/tests/test_language_support.py` runs one realistic mini-project per language through the full analyzer: symbols, import resolution, call graph, manifests, frameworks, databases, entry points, build commands, and the chunker. Run with `cd server && pip install -r requirements-dev.txt && pytest`.

---

## 9. Rate Limiting & Abuse Protection

Per-client sliding-window limits (in-memory, `app/core/rate_limit.py`), configured with `"N/unit"` rules joined by `;`:

| Rule | Default | Applies to |
|------|---------|------------|
| `RATE_LIMIT_ANALYZE` | `3/minute;20/hour` | Starting a **new** analysis (`/api/analyze/stream`). Reconnecting to an existing session is free. |
| `RATE_LIMIT_CHAT` | `6/minute;100/day` | `POST /api/chat` (the Groq free tier allows 1000 requests/day for the whole server) |
| `RATE_LIMIT_SEARCH` | `60/minute` | `POST /api/search` |
| `MAX_CONCURRENT_ANALYSES` | `3` | Global cap on running analyses (clone + CPU embedding). Checked before the per-client limit, so a "busy" rejection costs no quota. |
| `MAX_ANALYSES_PER_CLIENT` | `1` | Running analyses per client (`0` = no limit), so one client can't fill every global slot. Starting a new analysis cancels the same client's previous one if nobody is watching it any more; one still being watched (e.g. in another tab) is kept and the new request is refused. |

Analyses and clones are also bounded:

| Setting | Default | Effect |
|---------|---------|--------|
| `ANALYSIS_ABANDON_GRACE_SECONDS` | `10` | A running analysis is cancelled (clone killed, work stopped, clone deleted) this long after its last viewer disconnects, unless a viewer reconnects first. Finished sessions are never cancelled and stay replayable. |
| `MAX_REPO_SIZE_MB` | `1500` | Repositories whose GitHub-reported size (whole history, fetched before cloning) is larger are refused with a fatal `error` event (`0` = no cap). |
| `CLONE_TIMEOUT_SECONDS` | `300` | The `git clone` is killed and the analysis fails after this long (`0` = no timeout). |
| `CLONE_DIR` | `<system temp>/codeexplorer` | Where repositories are cloned. At startup, clone folders left behind by a previous run (crash, restart, `--reload`) are deleted; only UUID-named folders are touched. |

- JSON endpoints return **429** with a `Retry-After` header (exposed via CORS). Upstream Groq 429s pass Groq's own `retry-after` through.
- The SSE endpoint returns a single fatal `error` event (`rate_limited: true`, `retry_after`), because `EventSource` cannot read non-200 responses.
- Client identity is the socket address. Behind reverse proxies set `RATE_LIMIT_PROXY_HOPS=N` (the client is taken from the N-th `X-Forwarded-For` entry from the right; left-most entries are spoofable), or run uvicorn with `--forwarded-allow-ips`.
- Limits live in process memory: run a single worker (sessions and vector indexes are in-memory too). `RATE_LIMIT_ENABLED=false` disables limiting.

Request hardening:

- **CORS:** `CORS_ALLOWED_ORIGINS` is a comma-separated list of browser origins allowed to call the API (`*` = any). When empty (the default) only `localhost` / `127.0.0.1` on any port are allowed, which covers local development. Set it to the frontend's origin in production.
- **Body size:** request bodies above `MAX_REQUEST_BODY_MB` (default `8`, `0` = no limit) are rejected with **413**.
- **Chat history:** only `user` and `assistant` messages from the client's `chat_history` are passed to the LLM; any other role (e.g. an injected `system` message) is dropped.
- **Errors:** unexpected failures (chat, AI report, pipeline) return a generic message; details are only written to the server log.

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
