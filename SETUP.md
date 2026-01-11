# CodeExplorer Setup Guide

Complete setup instructions for running CodeExplorer locally.

## System Requirements

- **Python**: 3.9 or higher
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

Expected dependencies:
- fastapi
- uvicorn
- gitpython
- pydantic
- python-multipart
- toml

#### 2.3 Verify Installation

```bash
python -c "import fastapi; print('FastAPI installed successfully')"
```

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
- Next.js 15
- React 19
- TypeScript
- Tailwind CSS
- Axios

#### 3.3 Configure Environment Variables

Create a `.env.local` file:

```bash
cp .env.example .env.local
```

Edit `.env.local` and set:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
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
▲ Next.js 15.5.9
- Local:        http://localhost:3000
- Network:      http://192.168.x.x:3000

✓ Ready in 3.4s
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
Then update `NEXT_PUBLIC_API_URL` in `.env.local` to `http://localhost:8001`

**Problem**: Git clone fails with authentication error
- **Solution**: Make sure the repository URL is valid and accessible
- For private repos, you'll need to configure Git credentials

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
npm run dev -- -p 3001
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
- **Frontend**: Next.js will reload on `.tsx`, `.ts`, `.css` file changes

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
│   ├── workspace/      # Cloned repos (git ignored)
│   └── app/            # Application code
└── client/
    ├── node_modules/   # Dependencies (git ignored)
    ├── .next/          # Build output (git ignored)
    └── app/            # Application code
```

## Next Steps

1. **Explore the API**: Try different endpoints at `/docs`
2. **Test with Various Repos**: Analyze repositories of different sizes and languages
3. **Customize the UI**: Modify components in `client/components/`
4. **Add Features**: Extend the backend analyzers in `server/app/services/`

## Getting Help

- **Documentation**: See `/docs` folder for PRD and Technical Specs
- **Issues**: Check existing issues or create a new one
- **Logs**: Check terminal output for detailed error messages

## Production Deployment

For production deployment:

1. **Backend**: Use production ASGI server
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

2. **Frontend**: Build optimized version
```bash
npm run build
npm start
```

3. **Environment**: Set production environment variables
4. **Security**: Configure CORS, rate limiting, and authentication
5. **Monitoring**: Add logging and error tracking

---

**Happy Coding!** 🚀
