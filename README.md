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

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- Git

### Backend Setup

1. Navigate to the server directory:
```bash
cd server
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start the FastAPI server:
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
cp .env.example .env.local
```

4. Start the Next.js development server:
```bash
npm run dev
```

The dashboard will be available at [http://localhost:3000](http://localhost:3000)

### Usage

1. Open the dashboard at [http://localhost:3000](http://localhost:3000)
2. Enter a public GitHub repository URL (e.g., `https://github.com/facebook/react`)
3. Click "Analyze Repository"
4. Browse the results across different tabs:
   - **Overview**: Key statistics and README preview
   - **File Structure**: Interactive file tree
   - **Languages**: Code distribution by language
   - **Dependencies**: Project dependencies
   - **Key Files**: Important files and entry points

---

## 📁 Project Structure

```
CodeExplorer/
├── client/                 # Next.js frontend dashboard
│   ├── app/               # Next.js app directory
│   ├── components/        # React components
│   └── package.json       # Frontend dependencies
├── server/                # FastAPI backend
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   ├── services/     # Business logic
│   │   └── main.py       # FastAPI app
│   └── requirements.txt  # Backend dependencies
└── docs/                 # Documentation
```

---

## 📄 Documentation

- [Product Requirements Document](docs/PRD.md)
- [Technical Specification](docs/TechSpecs.md)
- [Client README](client/README.md)
