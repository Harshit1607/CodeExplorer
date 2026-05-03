import shutil
import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.repo_ingestor import clone_repo
from app.services.repo_scanner import scan_repo
from app.services.code_analyzer import CodeAnalyzer
from app.services.streaming_pipeline import StreamingPipeline

router = APIRouter()

class RepoRequest(BaseModel):
    repo_url: str

ACTIVE_SESSIONS = {}

@router.get("/analyze/stream")
async def analyze_stream(repo: str, request: Request, session_id: str = None):
    if not repo or not repo.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")
        
    if session_id and session_id in ACTIVE_SESSIONS:
        pipeline = ACTIVE_SESSIONS[session_id]
        print(f"Reconnecting to session: {session_id}")
    else:
        session_id = session_id or str(uuid.uuid4())
        pipeline = StreamingPipeline(repo, session_id)
        ACTIVE_SESSIONS[session_id] = pipeline
        asyncio.create_task(pipeline.run())
        print(f"Started new session: {session_id}")
        
    client_q = asyncio.Queue()
    pipeline.register_client(client_q)
    
    async def event_generator():
        # Yield history first for reconnections
        for event in pipeline.history:
            yield event
            
        try:
            while True:
                if await request.is_disconnected():
                    break
                    
                event = await client_q.get()
                yield event
                
                if "analysis_complete" in event or ("error" in event and '"stage": "Pipeline"' in event):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            pipeline.unregister_client(client_q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/analyze")
def analyze_repo(data: RepoRequest):
    """
    Clone and fully analyze a GitHub repository.

    This endpoint:
    1. Clones the repository
    2. Scans file/folder structure
    3. Performs static code analysis
    4. Cleans up cloned repo to save disk space
    5. Returns comprehensive analysis results
    """
    path = None
    try:
        # Clone repository
        path = clone_repo(data.repo_url)

        # Basic scan
        scan_results = scan_repo(path)

        # Detailed code analysis
        analyzer = CodeAnalyzer(path)
        structure_analysis = analyzer.analyze()

        return {
            "message": "Repository cloned and analyzed successfully",
            "repository_url": data.repo_url,
            "scan_results": scan_results,
            "structure_analysis": structure_analysis
        }
    finally:
        # Cleanup: delete cloned repo to save disk space
        if path:
            shutil.rmtree(path, ignore_errors=True)
