"""
Query access to a finished call graph, so the browser never has to download all of it.

On a large repository the full graph is tens of megabytes (django: ~29k functions, ~88k
edges). The stream only carries `summary()`; the client asks for one page of the function
list, one function's callers/callees, or the neighbourhood of the functions it is showing.
"""
from typing import Any, Dict, Iterable, List, Optional

from app.services.path_filters import is_test_path

MAX_PAGE = 500
MAX_NEIGHBOURHOOD = 400
MAX_NODE_EDGES = 2000

_SORTS = ("file", "connected", "called")


class CallGraphQuery:
    def __init__(self, graph: Dict[str, Dict[str, Any]]):
        self.graph = graph or {}
        tests_by_file: Dict[str, bool] = {}
        self._is_test: Dict[str, bool] = {}
        for fid, node in self.graph.items():
            file = node.get("file") or ""
            if file not in tests_by_file:
                tests_by_file[file] = is_test_path(file)
            self._is_test[fid] = tests_by_file[file]
        self._orders: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ helpers
    def is_test(self, fid: str) -> bool:
        return self._is_test.get(fid, False)

    def _order(self, sort: str) -> List[str]:
        if sort not in self._orders:
            g = self.graph
            if sort == "called":
                key = lambda f: (-len(g[f].get("called_by") or ()), g[f].get("file") or "", f)
            elif sort == "connected":
                key = lambda f: (-(len(g[f].get("called_by") or ()) + len(g[f].get("calls") or ())),
                                 g[f].get("file") or "", f)
            else:
                key = lambda f: (g[f].get("file") or "", f)
            self._orders[sort] = sorted(g, key=key)
        return self._orders[sort]

    def _brief(self, fid: str) -> Dict[str, Any]:
        node = self.graph[fid]
        return {
            "id": fid,
            "name": node.get("name") or fid.split("::")[-1],
            "file": node.get("file") or "",
            "type": node.get("type") or "function",
            "language": node.get("language") or "Unknown",
            "calls_count": len(node.get("calls") or ()),
            "called_by_count": len(node.get("called_by") or ()),
            "is_test": self.is_test(fid),
        }

    # ------------------------------------------------------------------ queries
    def summary(self) -> Dict[str, Any]:
        """Totals plus the most-called non-test function (what the stream sends)."""
        g = self.graph
        connected = total_calls = tests = 0
        most: Optional[str] = None
        for fid, node in g.items():
            calls, callers = len(node.get("calls") or ()), len(node.get("called_by") or ())
            total_calls += calls
            connected += bool(calls or callers)
            if self.is_test(fid):
                tests += 1
            elif callers and (most is None or callers > len(g[most].get("called_by") or ())):
                most = fid
        return {
            "available": bool(g),
            "total_functions": len(g),
            "connected_functions": connected,
            "total_calls": total_calls,
            "test_functions": tests,
            "most_called": self._brief(most) if most else None,
        }

    def functions(self, q: str = "", file: Optional[str] = None, include_tests: bool = False,
                  sort: str = "file", offset: int = 0, limit: int = 200) -> Dict[str, Any]:
        """One page of the function list, filtered by a substring and/or an exact file."""
        sort = sort if sort in _SORTS else "file"
        limit = max(1, min(limit, MAX_PAGE))
        offset = max(0, offset)
        query = (q or "").strip().lower()
        g = self.graph
        matches: Iterable[str] = self._order(sort)
        if file is not None:
            matches = (f for f in matches if g[f].get("file") == file)
        if not include_tests:
            matches = (f for f in matches if not self._is_test[f])
        if query:
            matches = (f for f in matches
                       if query in f.lower() or query in (g[f].get("name") or "").lower())
        matched = list(matches)
        return {
            "total": len(matched),
            "offset": offset,
            "items": [self._brief(f) for f in matched[offset:offset + limit]],
        }

    def node(self, fid: str, include_tests: bool = True) -> Optional[Dict[str, Any]]:
        """One function with its (capped) callers and callees."""
        node = self.graph.get(fid)
        if node is None:
            return None

        def edges(ids: List[str]) -> List[Dict[str, Any]]:
            out = [self._brief(i) for i in ids if i in self.graph and (include_tests or not self._is_test[i])]
            return out[:MAX_NODE_EDGES]

        return {**self._brief(fid), "calls": edges(node.get("calls") or []),
                "called_by": edges(node.get("called_by") or [])}

    def neighbourhood(self, ids: List[str], depth: int = 2, include_tests: bool = False,
                      max_nodes: int = 150) -> Dict[str, Any]:
        """
        The seeds, their callees' callees and callers' callers up to `depth` hops, breadth
        first, at most `max_nodes` nodes. Edge lists are limited to the returned nodes;
        `calls_count` / `called_by_count` keep the real totals.
        """
        g = self.graph
        depth = max(0, min(depth, 5))
        max_nodes = max(1, min(max_nodes, MAX_NEIGHBOURHOOD))
        seeds = [i for i in dict.fromkeys(ids) if i in g][:max_nodes]
        keep = dict.fromkeys(seeds)
        truncated = False

        def allowed(fid: str) -> bool:
            return fid in g and (include_tests or not self._is_test[fid])

        # Level by level, alternating callees and callers, so neither side starves the other.
        frontiers = {"calls": list(seeds), "called_by": list(seeds)}
        for _ in range(depth):
            for direction, frontier in frontiers.items():
                nxt: List[str] = []
                for fid in frontier:
                    for other in g[fid].get(direction) or ():
                        if other in keep or not allowed(other):
                            continue
                        if len(keep) >= max_nodes:
                            truncated = True
                            break
                        keep[other] = None
                        nxt.append(other)
                frontiers[direction] = nxt

        nodes: Dict[str, Any] = {}
        for fid in keep:
            node = g[fid]
            nodes[fid] = {
                **self._brief(fid),
                "calls": [c for c in node.get("calls") or () if c in keep],
                "called_by": [c for c in node.get("called_by") or () if c in keep],
            }
        return {"nodes": nodes, "truncated": truncated}
