# Product Requirements Document — CodeExplorer

## 1. Overview

CodeExplorer is a free developer tool that analyzes a public GitHub repository and provides structured, repository-grounded insights into the codebase. The tool helps developers understand project architecture, key modules, dependencies, and code relationships through interactive visualizations and AI-powered features.

---

## 2. Problem Statement

Understanding unfamiliar codebases is time-consuming and error-prone. Existing tools either provide low-level structural views or rely on AI explanations that hallucinate due to lack of grounding.

There is no free tool that provides automated, architecture-level understanding of a GitHub repository using only repository-derived information — combining static analysis, interactive visualizations, and AI-powered Q&A grounded in actual code.

---

## 3. Goals

- Enable fast understanding of unfamiliar repositories
- Provide hallucination-free explanations grounded in repository content
- **Real-time Pipeline**: Provide immediate feedback during the analysis process via streaming
- **High Performance**: Utilize concurrent processing to handle large repositories efficiently
- Reduce developer onboarding time with auto-generated setup guides
- Present insights through interactive, explorable visualizations
- Allow natural-language queries about the codebase

---

## 4. Target Users

- Software developers exploring new codebases
- Open-source contributors onboarding to projects
- Students learning from real-world repositories
- Tech leads evaluating project architecture

---

## 5. Features

### Core Analysis & Pipeline
- **Streaming Analysis Pipeline** — Real-time progress updates via Server-Sent Events (SSE) in 4 stages (Meta, Scan, Deep Analysis, AI Reporting)
- **Concurrent Processing Engine** — Multi-threaded static analysis (8 workers) for high-speed scanning
- Single public GitHub repository analysis via URL input
- **Multi-language parsing**:
  - First-class (tree-sitter): Python, JavaScript/TypeScript, Java, Rust, C/C++. Exact functions, classes, imports and call sites.
  - Basic (regex): Go, Ruby, PHP, C#, Swift, Kotlin, Scala, Vue, Svelte.
- **Import resolution per language**: tsconfig paths, monorepo workspaces, Java packages, Cargo workspaces, `#include`
- **Framework detection**: React, Vue, Angular, Next.js, Django, FastAPI, Flask, Express, Spring Boot, Quarkus, Actix Web, Axum, Tauri, Qt, and more
- **Database detection**: PostgreSQL, MySQL, MongoDB, Redis, SQLite, and more, based on runtime dependencies only (dev/test-only packages don't count)
- **Dependency extraction**: pip / Poetry / uv / PDM / Pipfile, npm, Maven, Gradle, Cargo, CMake, Conan, vcpkg, Meson, Go modules
- **Entry point and key file identification**: `main` functions, crate roots, `package.json` / `pyproject` scripts, and naming conventions

### Visualizations
- **Architecture Diagram** — Layered architecture view (Frontend, API, Services, Data, etc.) using ReactFlow with component nodes, database nodes, and weighted edges showing dependency strength
- **Call Graph** — Interactive D3.js force-directed graph showing function-to-function call relationships with graph/list views, depth control, search, and grouping by file
- **File Dependencies** — Interactive D3.js graph of file import/export relationships with circular dependency detection, external package tracking, and depth control
- **Complexity Analysis** — Bar chart ranking files by complexity metrics (lines, functions, classes)
- **File Structure** — Interactive file tree display
- **Language Distribution** — Visualization of language breakdown across the codebase

### AI-Powered Features
- **AI Architecture Report** — Automated high-level overview, component analysis, and structural insights generated as the final pipeline stage
- **Repository Chat (RAG)** — Conversational AI interface (powered by Groq API). Each question retrieves the relevant code (named symbols/files, vector similarity, call-graph callers), and answers cite their sources with links to exact lines. Includes suggested questions, chat history, and rate-limit handling
- **Semantic Search** — Hybrid search: local vector embeddings combined with concept-based keyword matching (50+ concept categories, e.g. "auth" finds authentication, login, JWT, OAuth). Includes relevance scoring, mode toggle and type filtering. Code chunks follow real function/class boundaries

### Developer Onboarding
- **Quick Start Guide** — Auto-generated setup and installation instructions including:
  - Primary language and framework detection
  - Build tool detection from lockfiles and wrappers (npm/pnpm/yarn/bun, pip/uv/Poetry/PDM/pipenv, Maven/Gradle, Cargo, CMake/Conan/vcpkg/Meson, Go)
  - Ready-to-run **install / build / run / test** commands for each project in the repo (monorepos get one card per project)
  - Docker and Docker Compose support
  - Makefile detection
  - Environment setup instructions
  - Entry points for starting exploration
- **Key Files** — Highlights important files (README, LICENSE, Dockerfile, config files)

### User Experience
- **Global Search Bar** — Searchable index of files, functions, and classes with keyboard shortcut (Ctrl+K), type filtering, and smart sorting
- **Dark/Light Mode** — Theme toggle with localStorage persistence and system preference detection
- **Tabbed Dashboard** — 13-tab interface organizing all analysis results
- **Responsive Design** — Clean UI with smooth transitions

---

## 6. Success Metrics

- Accurate identification of entry points and key files
- Correct framework and database detection across Python, JS/TS, Java, Rust and C/C++ projects
- Generated build/run commands work as-is for common project types
- Zero hallucinated responses in chat (grounded in repository content)
- Clear explanation of repository structure and architecture
- Analysis completes within reasonable time for small–medium repos
- Useful setup guide generation for common project types

---

## 7. Constraints

- Must be deployable using free-tier infrastructure
- Chat powered by Groq free tier (28k character context limit, rate limiting)
- Must restrict chat explanations strictly to repository content
- Public repositories only
- Per-client rate limits and a cap on concurrent analyses (protects the shared Groq quota and server CPU)

---

## 8. Future Scope

- Multi-user support
- Private repository access
- Multiple repository comparison
- Saved analysis history and session persistence
- IDE plugins
- Tree-sitter parsing for more languages (Go, C#, Kotlin, ...)
- Export analysis reports (PDF, Markdown)
