import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.repo_ingestor import clone_repo
from app.services.repo_scanner import scan_repo
from app.services.code_analyzer import CodeAnalyzer
from app.services.streaming_pipeline import StreamingPipeline, HEARTBEAT
from app.services.session_store import sessions
from app.services.fs_utils import remove_tree

router = APIRouter()

HEARTBEAT_SECONDS = 15


class RepoRequest(BaseModel):
    repo_url: str


@router.get("/analyze/stream")
async def analyze_stream(repo: str, request: Request, session_id: str = None):
    if not repo or not repo.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    pipeline = sessions.get(session_id)
    if pipeline and pipeline.repo_url != repo.strip().rstrip("/"):
        pipeline = None  # session id reused for a different repo

    if pipeline:
        print(f"Reconnecting to session: {pipeline.repo_id}")
    else:
        session_id = session_id or str(uuid.uuid4())
        pipeline = StreamingPipeline(repo, session_id)
        sessions.add(session_id, pipeline)
        asyncio.create_task(pipeline.run())
        print(f"Started new session: {session_id}")

    # Snapshot + subscribe happen synchronously, so nothing is missed or duplicated.
    history, client_q = pipeline.subscribe()
    already_done = pipeline.is_done

    async def event_generator():
        try:
            for event in history:
                yield event
            if already_done:
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, terminal = await asyncio.wait_for(client_q.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield HEARTBEAT
                    continue
                yield event
                if terminal:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            pipeline.unsubscribe(client_q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/analyze/{session_id}/status")
def analyze_status(session_id: str):
    pipeline = sessions.get(session_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return {
        "session_id": session_id,
        "repo_url": pipeline.repo_url,
        "done": pipeline.is_done,
        "progress": pipeline.progress,
        "files": len(pipeline.analyzer.files),
        "warnings": pipeline.warnings,
        "search_index": pipeline.vector_index.info(),
    }


@router.post("/analyze")
def analyze_repo(data: RepoRequest):
    """
    Clone and fully analyze a GitHub repository (non-streaming).
    """
    path = None
    try:
        path = clone_repo(data.repo_url)
        scan_results = scan_repo(path)
        analyzer = CodeAnalyzer(path)
        structure_analysis = analyzer.analyze()
        return {
            "message": "Repository cloned and analyzed successfully",
            "repository_url": data.repo_url,
            "scan_results": scan_results,
            "structure_analysis": structure_analysis
        }
    finally:
        if path:
            remove_tree(path)
