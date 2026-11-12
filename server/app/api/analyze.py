import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.repo_ingestor import clone_repo
from app.services.repo_scanner import scan_repo
from app.services.code_analyzer import CodeAnalyzer
from app.core import config
from app.core.rate_limit import check as rate_check, rate_limit, too_many_message
from app.services.streaming_pipeline import StreamingPipeline, HEARTBEAT, format_sse
from app.services.session_store import sessions
from app.services.fs_utils import remove_tree

router = APIRouter()

HEARTBEAT_SECONDS = 15


class RepoRequest(BaseModel):
    repo_url: str


def _rejected_stream(message: str, retry_after: int) -> StreamingResponse:
    """
    EventSource can't read the body/status of a non-200 response (it just reports a
    generic error), so rejections are sent as a single fatal SSE `error` event.
    """
    event = format_sse("error", "Pipeline", 0, {
        "message": message, "fatal": True, "rate_limited": True, "retry_after": retry_after,
    })

    async def gen():
        yield event

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Retry-After": str(retry_after)})


@router.get("/analyze/stream")
async def analyze_stream(repo: str, request: Request, session_id: str = None):
    if not repo or not repo.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Invalid GitHub URL")

    pipeline = sessions.get(session_id)
    if pipeline and pipeline.repo_url != repo.strip().rstrip("/"):
        pipeline = None  # session id reused for a different repo

    if pipeline:
        # Reconnects (EventSource retries automatically) never count against limits.
        print(f"Reconnecting to session: {pipeline.repo_id}")
    else:
        # Check global capacity first so a "busy" rejection doesn't use up the client's quota.
        if sessions.active_count() >= config.MAX_CONCURRENT_ANALYSES:
            return _rejected_stream("The server is busy analyzing other repositories. Please try again in a minute.", 30)
        retry_after = rate_check("analyze", request)
        if retry_after is not None:
            return _rejected_stream(too_many_message("analyze", retry_after), retry_after)

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


@router.post("/analyze", dependencies=[rate_limit("analyze")])
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
