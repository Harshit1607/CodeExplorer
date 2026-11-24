"""Call-graph query endpoints (the full graph is too large to stream on big repositories)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.call_graph_query import CallGraphQuery
from app.services.session_store import sessions

router = APIRouter()


def _query(session_id: str) -> CallGraphQuery:
    pipeline = sessions.get(session_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Session not found or expired. Analyze the repository again.")
    q = pipeline.call_graph_query()
    if q is None:
        raise HTTPException(status_code=409, detail="The call graph is not ready yet.")
    return q


@router.get("/callgraph/{session_id}/summary")
def callgraph_summary(session_id: str):
    return _query(session_id).summary()


@router.get("/callgraph/{session_id}/functions")
def callgraph_functions(
    session_id: str,
    q: str = Query("", max_length=200),
    file: Optional[str] = Query(None, max_length=1000),
    include_tests: bool = False,
    sort: Literal["file", "called"] = "file",
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
):
    """A page of functions: search by substring, list one file, or top-N by `sort`."""
    return _query(session_id).functions(q=q, file=file, include_tests=include_tests,
                                        sort=sort, offset=offset, limit=limit)


@router.get("/callgraph/{session_id}/node")
def callgraph_node(session_id: str, id: str = Query(..., max_length=2000), include_tests: bool = True):
    node = _query(session_id).node(id, include_tests=include_tests)
    if node is None:
        raise HTTPException(status_code=404, detail="Function not found")
    return node


@router.get("/callgraph/{session_id}/neighbourhood")
def callgraph_neighbourhood(
    session_id: str,
    ids: List[str] = Query(..., max_length=50),
    depth: int = Query(2, ge=0, le=5),
    include_tests: bool = False,
    max_nodes: int = Query(150, ge=1, le=400),
):
    """The given functions plus callers and callees up to `depth` hops (bounded)."""
    return _query(session_id).neighbourhood(ids, depth=depth, include_tests=include_tests, max_nodes=max_nodes)
