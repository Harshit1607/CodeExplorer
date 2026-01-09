# Technical Specification — CodeExplorer

## 1. System Architecture

CodeExplorer is a stateless web application with a backend analysis pipeline and a frontend visualization layer.

Frontend (Next.js) communicates with Backend (FastAPI) over HTTP APIs.

---

## 2. High-Level Flow

1. User submits a public GitHub repository URL
2. Backend clones the repository temporarily
3. Repository is scanned and analyzed
4. Metadata, dependencies, and embeddings are generated
5. Results are exposed via APIs
6. Frontend renders insights and visualizations

---

## 3. Backend Components

- Repo Ingestor: Clones and scans repository
- Static Parser: Extracts imports, functions, classes
- Dependency Analyzer: Builds file-level dependency graph
- Semantic Indexer: Enables repo-only search using embeddings
- Docs Generator: Produces onboarding documentation in Markdown

---

## 4. Technology Choices

**Backend**
- FastAPI
- GitPython
- Python `ast`
- sentence-transformers (MiniLM)
- FAISS
- networkx

**Frontend**
- Next.js
- Tailwind CSS
- D3.js

**Storage**
- SQLite (temporary persistence per analysis)

---

## 5. Data Handling

- No user data is stored
- Analysis data is overwritten per repository
- Repository files are deleted after analysis

---

## 6. API Endpoints (MVP)

- `POST /analyze` — submit repository URL
- `GET /structure` — folder & file overview
- `GET /dependencies` — dependency graph data
- `POST /search` — repo-grounded semantic search
- `GET /docs` — download onboarding documentation

---

## 7. Non-Functional Requirements

- Free to build and host
- Deterministic and reproducible results
- Read-only access to repositories
- Compatible with free-tier hosting limits

---

## 8. Limitations

- One repository analyzed at a time
- Public repositories only
- No authentication or persistence across sessions
