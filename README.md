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

## ✨ Key Features (MVP)

- Analyze a public GitHub repository (single repo at a time)
- Folder and file-level explanations
- Dependency graph visualization
- Repo-grounded semantic search
- Auto-generated onboarding documentation (Markdown)

---

## 🧠 Design Philosophy

- **Repo-only context** — no external knowledge or hallucinations
- **Deterministic output** — same repo gives same results
- **No authentication** — focused on core functionality
- **Free & open-source stack**

---

## 🏗️ Tech Stack

**Backend**
- FastAPI (Python)
- GitPython
- Static analysis (`ast`)
- FAISS + sentence-transformers

**Frontend**
- Next.js
- Tailwind CSS
- D3.js

**Storage**
- SQLite (temporary analysis persistence)

---

## 📌 MVP Constraints

- No authentication or user accounts
- No saved history
- One repository analyzed at a time
- Public GitHub repositories only

---

## 🛣️ Future Enhancements

- User accounts & analysis history
- Private repository support
- Local LLM-based explanations
- Repo comparison & evolution tracking
- IDE integrations

---

## 📄 Documentation

- [Product Requirements Document](docs/PRD.md)
- [Technical Specification](docs/TECHNICAL_SPEC.md)
