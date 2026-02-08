# Technical Specification — CodeExplorer

## 1. System Architecture

CodeExplorer is a web application with a backend analysis pipeline and a frontend visualization layer.

Frontend (React + Vite) communicates with Backend (FastAPI) over HTTP APIs.

---

## 2. High-Level Flow

1. User submits a public GitHub repository URL
2. Backend clones the repository temporarily
3. Repository is scanned and analyzed (structure, dependencies, call graph, architecture)
4. Metadata, dependencies, and code intelligence data are generated
5. Results are exposed via APIs
6. Frontend renders insights, visualizations, and interactive tools
7. Cloned repository is cleaned up after analysis

---

## 3. Backend Components

- **Repo Ingestor**: Clones public GitHub repositories using GitPython and returns a temporary path
- **Repo Scanner**: Performs basic repository scanning and file enumeration
- **Code Analyzer**: Comprehensive static analysis engine that extracts:
  - Imports and dependencies per file
  - Functions and their signatures
  - Classes and their methods
  - Entry points and key files
  - Language detection (19+ languages supported)
  - Call graph (function-to-function call relationships)
  - File-level dependency graph with circular dependency detection
  - Framework and database detection
- **Architecture Analyzer**: Generates high-level layered architecture diagrams by classifying files into layers (Frontend, API, Middleware, Services, Data, Config, Tests, Utils) and detecting component relationships
- **Semantic Search Service**: Concept-based code search using 50+ concept categories with 500+ related terms, enabling search by meaning rather than exact names
- **Chat Service**: AI-powered chat about the analyzed repository using Groq API, with intelligent context building and file prioritization

---

## 4. Technology Choices

**Backend**
- FastAPI
- GitPython
- Python `ast`
- Groq API (LLM-powered chat)
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

- `POST /api/analyze` — Submit a GitHub repository URL for cloning, scanning, and full analysis. Returns scan results, file structure, languages, dependencies, call graph, file dependencies, architecture, frameworks, and databases.
- `POST /api/structure` — Analyze a local repository structure
- `POST /api/search` — Concept-based semantic search across files, functions, classes, and imports. Accepts a query and analysis data, returns ranked and grouped results with relevance scores.
- `POST /api/chat` — AI-powered Q&A about the analyzed repository. Accepts a question, analysis data, and optional chat history. Uses Groq API with intelligent context building (28k character limit). Returns AI-generated answers grounded in repository content.

---

## 7. Frontend Features

### Repository Input
- GitHub URL validation (regex-based)
- Example repository suggestions (React, Next.js)
- Loading state and error handling

### Dashboard (Tabbed Interface — 12 Tabs)
1. **Quick Start** — Auto-generated setup and installation guide with language/framework detection, package manager suggestions, install/run commands, Docker/Makefile support, and entry point listing
2. **Chat** — AI-powered conversational interface for asking questions about the codebase, with suggested questions, chat history, rate-limit handling, and retry functionality
3. **Search** — Semantic code search with suggested searches, type filtering (files, functions, classes, imports), and relevance scoring (high/medium/low)
4. **Architecture** — ReactFlow-based layered architecture diagram with 8 layer types (Frontend, API, Middleware, Services, Data, Config, Tests, Utils), custom nodes, mini-map, and component statistics
5. **Call Graph** — Interactive D3.js force-directed graph showing function-to-function call relationships with graph/list views, depth control (1–5), color coding, search, grouping by file, and statistics
6. **Complexity** — Recharts bar chart ranking files by complexity (lines of code, function count, class count)
7. **Overview** — Repository statistics (total files, languages, entry points, key files) with language breakdown
8. **File Structure** — Interactive file tree display
9. **Languages** — Language distribution visualization
10. **Dependencies** — Project dependency listing (npm, pip, cargo, go modules)
11. **File Dependencies** — Interactive D3.js graph of file import/export relationships with circular dependency detection, external package tracking, graph/list views, and depth control
12. **Key Files** — Highlights important files (README, LICENSE, Dockerfile, config files, entry points)

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

## 9. Non-Functional Requirements

- Free to build and host
- Deterministic and reproducible results
- Read-only access to repositories
- Compatible with free-tier hosting limits
- Responsive UI with dark/light mode support

---

## 10. Limitations

- One repository analyzed at a time
- Public repositories only
- No authentication or persistence across sessions
- Chat context limited to 28k characters (Groq free tier)
- Chat subject to rate limiting (Groq API)
