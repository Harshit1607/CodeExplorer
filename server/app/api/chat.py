import traceback
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.rate_limit import rate_limit
from app.services.chat_service import chat_about_repo
from app.services.session_store import sessions

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    # Preferred: the analysis session (server-side data + vector index → RAG).
    session_id: Optional[str] = None
    # Fallback when the session has expired.
    analysis_data: Optional[dict] = None
    chat_history: Optional[List[ChatMessage]] = None


class ChatSource(BaseModel):
    file: str
    start_line: int
    end_line: int
    symbol: Optional[str] = None
    reason: str
    tag: str = "code"         # code | docs | config


class ChatResponse(BaseModel):
    response: str
    sources: List[ChatSource] = []
    retrieval: str = "none"   # semantic | files | none


@router.post("/chat", response_model=ChatResponse, dependencies=[rate_limit("chat")])
def chat(data: ChatRequest):
    """Chat about an analyzed repository (retrieval-augmented when a session index exists)."""
    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question is empty.")

    pipeline = sessions.get(data.session_id)
    if not pipeline and not data.analysis_data:
        if data.session_id:
            # The client resends with analysis_data on this status.
            raise HTTPException(status_code=404, detail="Session not found or expired")
        raise HTTPException(
            status_code=400,
            detail="Repository analysis data is missing. Please wait for analysis to complete."
        )

    history = [{"role": m.role, "content": m.content} for m in (data.chat_history or [])]
    try:
        result = chat_about_repo(data.question, data.analysis_data, history, pipeline=pipeline)
        print(f"Chat: retrieval={result['retrieval']} sources={len(result['sources'])} q={data.question[:60]!r}")
        return ChatResponse(**result)
    except HTTPException:
        raise
    except Exception:
        # Details stay in the server log; the client only gets a generic message.
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Chat failed because of an internal error. Please try again.")
