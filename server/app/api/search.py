from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.rate_limit import rate_limit
from app.services.semantic_search import files_from_analysis_data, hybrid_search
from app.services.session_store import sessions

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    # Preferred: the streaming session id. The server then uses its own file data
    # and the session's vector index.
    session_id: Optional[str] = None
    # Fallback when the session has expired: client-side analysis data (keyword search only).
    analysis_data: Optional[dict] = None
    mode: Literal["hybrid", "semantic", "keyword"] = "hybrid"
    limit: int = Field(30, ge=1, le=100)


class SearchResultItem(BaseModel):
    type: str
    name: str
    file_path: str
    context: str
    score: float
    match: str = "keyword"              # keyword | semantic | hybrid
    keyword_score: Optional[float] = None
    similarity: Optional[float] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItem]
    grouped: Dict[str, List[SearchResultItem]]
    mode: str
    index: Optional[Dict[str, Any]] = None


@router.post("/search", response_model=SearchResponse, dependencies=[rate_limit("search")])
def search(data: SearchRequest):
    """
    Hybrid code search: concept-expanded keyword matching fused with vector similarity
    over embedded code chunks (when the session's index is ready).
    """
    pipeline = sessions.get(data.session_id)
    if not pipeline and data.session_id and not data.analysis_data:
        # The client resends with analysis_data on this status.
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if pipeline:
        files = pipeline.analyzer.files
        index = pipeline.vector_index
    else:
        files = files_from_analysis_data(data.analysis_data or {})
        index = None

    if not files:
        raise HTTPException(status_code=400, detail="No analysis data available for this session. Analyze a repository first.")

    return SearchResponse(**hybrid_search(data.query, files, index, limit=data.limit, mode=data.mode))


@router.get("/search/status")
def search_status(session_id: str):
    pipeline = sessions.get(session_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return pipeline.vector_index.info()
