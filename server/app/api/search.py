from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services.semantic_search import search_with_ai_ranking

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    analysis_data: dict

class SearchResultItem(BaseModel):
    type: str
    name: str
    file_path: str
    context: str
    score: float

class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResultItem]
    grouped: Dict[str, List[SearchResultItem]]

@router.post("/search", response_model=SearchResponse)
def search(data: SearchRequest):
    """
    Perform semantic search on an analyzed repository.

    Search for code elements by concept (e.g., "authentication logic",
    "database queries", "error handling").
    """
    results = search_with_ai_ranking(
        query=data.query,
        analysis_data=data.analysis_data,
    )

    return SearchResponse(**results)
