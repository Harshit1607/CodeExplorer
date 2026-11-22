import asyncio
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.core import config
from app.core.rate_limit import check as rate_check, too_many_message
from app.services.streaming_pipeline import StreamingPipeline, HEARTBEAT, format_sse
from app.services.session_store import sessions
from app.services.github_url import normalize_github_url

router = APIRouter()

HEARTBEAT_SECONDS = 15


def _rejected_stream(message: str, retry_after: Optional[int] = None) -> StreamingResponse:
    """
    EventSource can't read the body/status of a non-200 response (it just reports a
    generic error), so rejections are sent as a single fatal SSE `error` event.
    `retry_after` marks a rate-limit / busy rejection that is worth retrying later.
    """
    data = {"message": message, "fatal": True}
    headers = {"Cache-Control": "no-cache"}
    if retry_after is not None:
        data.update(rate_limited=True, retry_after=retry_after)
        headers["Retry-After"] = str(retry_after)
    event = format_sse("error", "Pipeline", 0, data)

    async def gen():
        yield event

    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


def _is_session_id(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


@router.get("/analyze/stream")
async def analyze_stream(request: Request, repo: str = "", session_id: str = None):
    try:
        repo = normalize_github_url(repo)
    except ValueError as e:
        return _rejected_stream(str(e))
    if session_id and not _is_session_id(session_id):
        return _rejected_stream("Invalid session id.")

    pipeline = sessions.get(session_id)
    if pipeline and pipeline.repo_url != repo:
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

