# CodeExplorer

CodeExplorer is a repository-grounded codebase intelligence tool that helps developers understand unfamiliar GitHub repositories faster.  
It analyzes a public repository and provides architecture-level insights, dependency relationships, and onboarding documentation using only the repository itself as the source of truth.

---

## 🚀 What Problem Does It Solve?

Developers often struggle to understand large or unfamiliar codebases when onboarding to a new project or exploring open-source repositories. Existing tools either show raw folder structures or rely on AI explanations that may hallucinate.

CodeExplorer solves this by:
- Automatically analyzing repository structure
- Identifying key files and entry points
- Visualizing dependencies
- Answering questions strictly from repository-derived context

---

## ✨ Key Features

- ⚡ **Streaming Analysis Pipeline**: Real-time progress updates via Server-Sent Events (SSE)
- 🚀 **Concurrent Processing**: Multi-threaded static analysis for high-speed scanning
- 🌐 **Multi-language Parsing**: Real parsers (tree-sitter) for **Python, JavaScript/TypeScript, Java, Rust and C/C++**: exact functions, classes, imports and call sites. Basic regex support for Go, Ruby, PHP, C#, Swift, Kotlin, Scala, Vue and Svelte
- 📊 **Repository Analysis**: Analyze any public GitHub repository with one click
- 📁 **File Structure Visualization**: Interactive file tree and treemap views
- 💻 **Language Breakdown**: Pie charts and bar graphs showing code distribution
- 🔗 **Dependency Graph**: Interactive force-directed graph of file imports, resolved per language (tsconfig paths, Java packages, Cargo workspaces, `#include`, …)
- 📦 **Dependency Extraction**: pip / Poetry / uv / Pipfile, npm, Maven, Gradle, Cargo, CMake, Conan, vcpkg, Meson, Go modules
- 🌳 **Call Graph**: Function-to-function relationship mapping from real call sites
- 🛠️ **Quick Start Guide**: Ready-to-run install / build / run / test commands for each project in the repo, picked from its lockfiles and wrappers (`uv`, `poetry`, `pnpm`, `./mvnw`, `./gradlew`, `cargo`, CMake…)
- 🔍 **Semantic Search**: Hybrid vector + keyword search over code, docs and config files (local embeddings, no API key)
- 💬 **Repository Chat (RAG)**: Ask questions about the code, or how to set up, test and deploy it (README, docs/, Dockerfile, compose, CI and Makefile are indexed too); answers cite the exact files and lines they come from
- ✨ **AI Architecture Report**: Written from retrieved code excerpts (entry points, key modules, routes, models, setup docs) plus repository metadata; its `path:line` citations are checked against those excerpts and link to the excerpt lines they point into
- ⭐ **Key Files Detection**: Automatic identification of entry points and important files
- 🛡️ **Rate Limiting**: Per-client limits and a cap on concurrent analyses
- 🎨 **Modern Dashboard**: Clean, responsive UI with dark mode support

---

## 🧠 Design Philosophy

- **Repo-only context**: chat and the AI report are given retrieved repository code and asked to cite it; citations are links you can check
- **Deterministic output**: the same repo gives the same results
- **No authentication**: focused on core functionality
- **Free & open-source stack**

---

## 🏗️ Tech Stack

**Backend**
- FastAPI (Python)
- GitPython
- tree-sitter (Python, JS/TS, Java, Rust, C/C++ parsing), with `ast`/regex fallback
- fastembed + numpy (local embeddings / vector search)
- Groq API (chat and AI report)
- Server-Sent Events (SSE) for streaming
- Multi-threading (`ThreadPoolExecutor`)

**Frontend**
- Vite + React 18
- TypeScript
- Tailwind CSS
- D3.js v7 (force-directed graphs, treemaps)
- ReactFlow (architecture diagrams)
- Recharts (pie charts, bar charts)
- EventSource API (for SSE)

**Storage**
- In-memory sessions (TTL-evicted). Nothing is persisted.

---

## 📌 Constraints

- No authentication or user accounts
- No saved history
- Public GitHub repositories only
- Single server worker (sessions, vector indexes and rate limits live in memory)

---

## 🛣️ Future Enhancements

- User accounts & analysis history
- Private repository support
- Tree-sitter parsing for Go, C#, Kotlin and more
- Repo comparison & evolution tracking
- IDE integrations

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+ (3.11+ recommended: `pyproject.toml` / `Cargo.toml` parsing uses `tomllib`)
- Node.js 18+
- Git
- A free [Groq API key](https://console.groq.com) for chat and the AI report

### Backend Setup

1. Navigate to the server directory:
```bash
cd server
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies (includes tree-sitter and its language grammars):
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env   # then set GROQ_API_KEY
```

5. Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

The backend will be available at [http://localhost:8000](http://localhost:8000)

### Frontend Setup

1. Navigate to the client directory:
```bash
cd client
```

2. Install dependencies:
```bash
npm install
```

3. Configure environment variables:
```bash
cp .env.example .env.local   # VITE_API_URL=http://localhost:8000
```

4. Start the Vite development server:
```bash
npm run dev
```

The dashboard will be available at [http://localhost:3000](http://localhost:3000)

### Running Tests

```bash
cd server
pip install -r requirements-dev.txt
pytest
```

The suite runs a small sample project for each language (Python, TypeScript, Java, Rust, C++) through the full analyzer.

### Usage

1. Open the dashboard at [http://localhost:3000](http://localhost:3000)
2. Enter a public GitHub repository URL (e.g., `https://github.com/facebook/react`)
3. Click "Analyze Repository"
4. Watch the **Real-time Pipeline** process the repository in 4 stages:
   - **Stage 1**: Repository Meta Fetching
   - **Stage 2**: Concurrent File Scanning & Complexity Mapping
   - **Stage 3**: Deep Static Analysis (Call Graph, Architecture, Dependencies, Build Commands)
   - **Stage 4**: AI Architecture Report Generation (the search index builds in parallel; the report waits up to `AI_REPORT_INDEX_WAIT_SECONDS` for it, then uses the part already built)
5. Browse the results across different tabs:
   - **AI Report**: Codebase summary written from retrieved code, with linked `path:line` citations
   - **Quick Start**: Install / build / run / test commands per project
   - **Chat**: Ask questions about the code, with source links
   - **Search**: Hybrid semantic + keyword code search
   - **Architecture**: Layered architecture diagram
   - **Call Graph**: Function call relationships
   - **Complexity**: Files ranked by complexity
   - **Overview**: Key statistics and README preview
   - **File Structure**: Interactive file tree
   - **Languages**: Code distribution by language
   - **Dependencies**: Dependencies grouped by ecosystem (Python, JS, Java, Rust, C/C++, Go)
   - **File Dependencies**: File import graph
   - **Key Files**: Important files and entry points

---

## 📁 Project Structure

```
CodeExplorer/
├── client/                    # Vite + React frontend dashboard
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── hooks/            # useAnalysis (SSE) etc.
│   │   └── main.tsx          # App entry
│   └── package.json
├── server/                    # FastAPI backend
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   ├── core/             # Rate limiting, config
│   │   ├── services/         # Analysis pipeline
│   │   │   ├── source_parser.py      # tree-sitter symbols, imports, calls
│   │   │   ├── import_resolver.py    # import -> file resolution per language
│   │   │   ├── project_manifests.py  # dependencies + build/run commands
│   │   │   ├── code_analyzer.py      # analysis orchestration
│   │   │   ├── code_chunker.py       # RAG chunking
│   │   │   └── streaming_pipeline.py # SSE pipeline
│   │   └── main.py           # FastAPI app
│   ├── tests/                # pytest suite
│   ├── requirements.txt
│   └── requirements-dev.txt
└── docs/                     # Documentation
```

---

## 📄 Documentation

- [Setup Guide](SETUP.md)
- [Product Requirements Document](docs/PRD.md)
- [Technical Specification](docs/TechSpecs.md)
- [Client README](client/README.md)
