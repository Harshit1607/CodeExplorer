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

### Core Analysis
- Single public GitHub repository analysis via URL input
- Comprehensive static code analysis (19+ languages)
- Framework detection (React, Vue, Angular, Django, FastAPI, Express, Spring, etc.)
- Database detection (PostgreSQL, MongoDB, Redis, SQLite, etc.)
- Dependency extraction from package managers (npm, pip, cargo, go modules)
- Entry point and key file identification

### Visualizations
- **Architecture Diagram** — Layered architecture view (Frontend, API, Services, Data, etc.) using ReactFlow with component nodes, database nodes, and weighted edges showing dependency strength
- **Call Graph** — Interactive D3.js force-directed graph showing function-to-function call relationships with graph/list views, depth control, search, and grouping by file
- **File Dependencies** — Interactive D3.js graph of file import/export relationships with circular dependency detection, external package tracking, and depth control
- **Complexity Analysis** — Bar chart ranking files by complexity metrics (lines, functions, classes)
- **File Structure** — Interactive file tree display
- **Language Distribution** — Visualization of language breakdown across the codebase

### AI-Powered Features
- **Repository Chat** — Conversational AI interface (powered by Groq API) for asking questions about the codebase. Includes suggested questions, chat history, intelligent context building with file prioritization, and error handling with rate-limit awareness
- **Semantic Search** — Concept-based code search using 50+ concept categories. Search by meaning (e.g., "auth" finds authentication, login, JWT, OAuth), with suggested searches, relevance scoring, and type filtering

### Developer Onboarding
- **Quick Start Guide** — Auto-generated setup and installation instructions including:
  - Primary language and framework detection
  - Package manager suggestion (npm, yarn, pip, poetry, cargo, etc.)
  - Install and run commands
  - Docker and Docker Compose support
  - Makefile detection
  - Environment setup instructions
  - Entry points for starting exploration
- **Key Files** — Highlights important files (README, LICENSE, Dockerfile, config files)

### User Experience
- **Global Search Bar** — Searchable index of files, functions, and classes with keyboard shortcut (Ctrl+K), type filtering, and smart sorting
- **Dark/Light Mode** — Theme toggle with localStorage persistence and system preference detection
- **Tabbed Dashboard** — 12-tab interface organizing all analysis results
- **Responsive Design** — Clean UI with smooth transitions

---

## 6. Success Metrics

- Accurate identification of entry points and key files
- Correct framework and database detection
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
- One repository analyzed at a time

---

## 8. Future Scope

- Multi-user support
- Private repository access
- Multiple repository comparison
- Saved analysis history and session persistence
- IDE plugins
- Additional language support for deeper analysis
- Export analysis reports (PDF, Markdown)
