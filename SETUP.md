# CodeExplorer Setup Guide

Complete setup instructions for running CodeExplorer locally.

## System Requirements

- **Python**: 3.10 or higher (3.11+ recommended; `pyproject.toml` / `Cargo.toml` parsing uses `tomllib`)
- **Node.js**: 18.0 or higher
- **Git**: Latest version
- **Operating System**: Windows, macOS, or Linux

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/CodeExplorer.git
cd CodeExplorer
```

### Step 2: Backend Setup

#### 2.1 Create Python Virtual Environment

**On Windows:**
```bash
cd server
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
cd server
python3 -m venv venv
source venv/bin/activate
```

#### 2.2 Install Python Dependencies

```bash
pip install -r requirements.txt
```

Main dependencies:
- fastapi, uvicorn, gitpython, httpx, requests, python-dotenv, toml
- groq (chat and AI report)
- fastembed, numpy (local embeddings for semantic search)
- tree-sitter + grammars: `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`, `tree-sitter-rust`, `tree-sitter-cpp`

#### 2.3 Configure Environment Variables

```bash
cp .env.example .env
```

Set `GROQ_API_KEY` (free key at https://console.groq.com). Optionally set `GITHUB_TOKEN` to raise the GitHub API limit. `.env.example` documents all other settings (embedding model, sessions, chat, rate limits).

#### 2.4 Verify Installation

```bash
python -c "import fastapi, tree_sitter, tree_sitter_python; print('Backend dependencies OK')"
```

#### 2.5 Run the Tests (optional)

```bash
pip install -r requirements-dev.txt
pytest
```

This runs one sample project per language (Python, TypeScript, Java, Rust, C++) through the analyzer. Expected: `6 passed`.

### Step 3: Frontend Setup

#### 3.1 Navigate to Client Directory

```bash
cd ../client
```

#### 3.2 Install Node Dependencies

```bash
npm install
```

This will install:
- Vite 5
- React 18
- TypeScript
- Tailwind CSS
- D3.js, ReactFlow, Recharts
- Axios

#### 3.3 Configure Environment Variables

Create a `.env.local` file:

```bash
cp .env.example .env.local
```

Edit `.env.local` and set:
```
VITE_API_URL=http://localhost:8000
```

### Step 4: Running the Application

You'll need **two terminal windows** open simultaneously.

#### Terminal 1: Backend Server

```bash
cd server
source venv/bin/activate  # On Windows: venv\Scripts\activate
uvicorn app.main:app --reload
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

#### Terminal 2: Frontend Server

```bash
cd client
npm run dev
```

Expected output:
```
  VITE v5.x.x  ready in 500 ms

  ➜  Local:   http://localhost:3000/
```

### Step 5: Verify Setup

1. **Check Backend**: Visit [http://localhost:8000/docs](http://localhost:8000/docs)
   - You should see the FastAPI Swagger documentation

2. **Check Frontend**: Visit [http://localhost:3000](http://localhost:3000)
   - You should see the CodeExplorer dashboard

3. **Test Analysis**:
   - Enter a repository URL: `https://github.com/pallets/flask`
   - Click "Analyze Repository"
   - Wait for analysis to complete
   - Browse results across different tabs
   - The **Quick Start** tab should show `pip` / `python` commands for the repo

## Troubleshooting

### Backend Issues

**Problem**: `ModuleNotFoundError: No module named 'fastapi'`
- **Solution**: Make sure virtual environment is activated and dependencies are installed
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Problem**: Port 8000 already in use
- **Solution**: Either kill the process using port 8000 or change the port
```bash
uvicorn app.main:app --reload --port 8001
```
Then update `VITE_API_URL` in `.env.local` to `http://localhost:8001`

**Problem**: Git clone fails with authentication error
- **Solution**: Make sure the repository URL is valid and accessible
- Only public repositories are supported

**Problem**: Analysis only shows basic results for Python / JS / Java / Rust / C++ (no exact symbols, fewer file dependencies)
- **Solution**: tree-sitter is missing, so the analyzer fell back to regex analysis. Reinstall the dependencies inside the virtual environment:
```bash
pip install -r requirements.txt
python -c "import tree_sitter_python"
```

**Problem**: `pip install` fails on tree-sitter or fastembed
- **Solution**: Check `python --version`. These packages need Python 3.10+.

**Problem**: Chat or AI report says the API key is missing
- **Solution**: Set `GROQ_API_KEY` in `server/.env` and restart the server

**Problem**: `429 Too Many Requests` / "rate limited"
- **Solution**: Wait for the `Retry-After` time, or relax the limits for local development in `server/.env` (`RATE_LIMIT_ENABLED=false`)

### Frontend Issues

**Problem**: `npm install` fails
- **Solution**: Clear npm cache and retry
```bash
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

**Problem**: Port 3000 already in use
- **Solution**: Either kill the process or use a different port
```bash
npm run dev -- --port 3001
```

**Problem**: "Failed to fetch" error when analyzing
- **Solution**:
  1. Verify backend is running on http://localhost:8000
  2. Check `.env.local` has correct API URL
  3. Open browser console for detailed error messages
  4. Verify CORS is configured correctly in backend

### Common Issues

**Problem**: Analysis takes too long
- **Solution**: Large repositories take longer to analyze. Start with smaller repos for testing.

**Problem**: "Repository not found" error
- **Solution**: Ensure the GitHub URL is correct and the repository is public

**Problem**: Dark mode not working
- **Solution**: The UI automatically detects system theme preference. Check your OS theme settings.

## Development Tips

### Hot Reload

Both servers support hot reload:
- **Backend**: FastAPI will reload on `.py` file changes
- **Frontend**: Vite will hot-reload on `.tsx`, `.ts`, `.css` file changes

### API Documentation

Visit [http://localhost:8000/docs](http://localhost:8000/docs) for:
- Interactive API testing
- Endpoint documentation
- Request/response schemas

### Directory Structure

Keep your workspace organized:
```
CodeExplorer/
├── server/
│   ├── venv/           # Virtual environment (git ignored)
│   ├── app/            # Application code
│   └── tests/          # pytest suite
└── client/
    ├── node_modules/   # Dependencies (git ignored)
    ├── dist/           # Build output (git ignored)
    └── src/            # Application code
```

## Next Steps

1. **Explore the API**: Try different endpoints at `/docs`
2. **Test with Various Repos**: Analyze repositories of different sizes and languages
3. **Customize the UI**: Modify components in `client/src/components/`
4. **Add Features**: Extend the backend analyzers in `server/app/services/`
   - New language: add its grammar to `source_parser.py` (an `_Extractor` subclass) and its import rules to `import_resolver.py`
   - New build tool / manifest: `project_manifests.py`

## Getting Help

- **Documentation**: See `/docs` folder for PRD and Technical Specs
- **Issues**: Check existing issues or create a new one
- **Logs**: Check terminal output for detailed error messages

## Production Deployment

For production deployment:

1. **Backend**: Run a **single** worker. Sessions, vector indexes and rate limits are kept in memory.
```bash
pip install -r requirements.txt   # includes tree-sitter grammars
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Behind a reverse proxy, set `RATE_LIMIT_PROXY_HOPS=1` so rate limits apply per real client.

2. **Frontend**: Build the static site and serve `client/dist/` with any static host
```bash
npm run build
npm run preview   # local check of the production build
```

3. **Environment**: Set production environment variables
4. **Security**: Configure CORS and review the rate limits in `.env` (see `docs/TechSpecs.md` §9)
5. **Monitoring**: Add logging and error tracking

---

**Happy Coding!** 🚀
