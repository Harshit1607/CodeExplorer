"""
Retrieval for repository chat (RAG).

Picks the code chunks most relevant to a question and renders them into a compact,
budgeted context block. Candidates come from:
  1. symbols named in the question   (`parse_args`, AuthService, ...)
  2. files named in the question      (`semantic_search.py`, "the chunker")
  3. vector similarity to the question (+ the previous question for follow-ups)
Selection then enforces a character budget, per-file caps and overlap removal.
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.services.code_chunker import CodeChunk
from app.services.path_classifier import is_secondary
from app.services.semantic_search import _SECONDARY_QUERY_RE

MIN_SIMILARITY = 0.45
MAX_CHUNKS_PER_FILE = 4
MAX_CHUNKS_PER_SYMBOL_MENTION = 3     # skip symbols that are too ambiguous (e.g. "get")
MAX_CALL_NAMES = 6
MAX_SECONDARY_CHUNKS = 2              # tests/examples unless the question asks for them
EXPLICIT_SYMBOL_SCORE = 3.0           # `backticked`, snake_case, camelCase, name()
PLAIN_WORD_SYMBOL_SCORE = 0.8         # "option" matching class Option: comparable to a strong vector hit
MAX_GRAPH_NEIGHBOURS = 4              # callers/callees pulled in for "where is X called" questions

_CALLERS_RE = re.compile(r"\b(called|calls?|callers?|invoked?|invokes|used|usages?|triggers?|references?)\b", re.I)
_CALLEES_RE = re.compile(r"\b(what does .* (call|use)|depends? on|calls into|flow|trace|step by step|walk ?through)\b", re.I)

_LANG_FENCE = {
    "Python": "python", "JavaScript": "javascript", "JavaScript (React)": "jsx",
    "TypeScript": "typescript", "TypeScript (React)": "tsx", "Java": "java", "Go": "go",
    "Rust": "rust", "Ruby": "ruby", "PHP": "php", "C#": "csharp", "Swift": "swift",
    "Kotlin": "kotlin", "Scala": "scala", "C": "c", "C++": "cpp", "Vue": "vue", "Svelte": "svelte",
}

_STOPWORDS = {
    "the", "and", "for", "how", "what", "where", "which", "does", "this", "that", "with", "from",
    "into", "work", "works", "code", "file", "files", "function", "class", "method", "repo",
    "repository", "explain", "show", "about", "there", "used", "use", "uses", "called", "call",
}


@dataclass
class Candidate:
    chunk: CodeChunk
    score: float
    reason: str          # symbol | file | semantic


def _short(symbol: Optional[str]) -> Optional[str]:
    return symbol.split(".")[-1] if symbol else None


def _mentioned_identifiers(text: str) -> Dict[str, bool]:
    """
    {identifier: explicit}. Explicit = backticked, snake_case, camelCase or name().
    Plain words (>= 4 chars) are returned as non-explicit; they only matter if they
    exactly match a symbol, and then with a lower score.
    """
    found: Dict[str, bool] = {}
    for tok in re.findall(r"`([A-Za-z_][\w.]*)`", text or ""):
        found[tok.split(".")[-1]] = True
    for tok in re.findall(r"[A-Za-z_][\w]*(?:\(\))?", text or ""):
        bare = tok.rstrip("()")
        if len(bare) < 3 or bare.lower() in _STOPWORDS:
            continue
        explicit = bool(tok.endswith("()") or "_" in bare.strip("_") or re.search(r"[a-z][A-Z]", bare))
        if explicit or len(bare) >= 4:
            found[bare] = found.get(bare, False) or explicit
    return found


def _mentioned_files(text: str, files: List[str]) -> List[str]:
    """Files referenced by name (`chat_service.py`) or distinctive stem (`chat_service`)."""
    lower = text.lower()
    hits = []
    for path in files:
        name = path.rsplit("/", 1)[-1].lower()
        stem = name.rsplit(".", 1)[0]
        if re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w])", lower):
            hits.append(path)
        elif len(stem) >= 5 and stem not in _STOPWORDS and re.search(rf"(?<![\w.-]){re.escape(stem)}(?![\w.])", lower):
            # Ambiguous stems ("index", "utils") are only accepted when unique.
            hits.append(path)
    by_name: Dict[str, List[str]] = {}
    for h in hits:
        by_name.setdefault(h.rsplit("/", 1)[-1].lower(), []).append(h)
    return [h for h in hits if len(by_name[h.rsplit("/", 1)[-1].lower()]) <= 2]


def _overlaps(a: CodeChunk, b: CodeChunk) -> bool:
    if a.file != b.file:
        return False
    inter = min(a.end_line, b.end_line) - max(a.start_line, b.start_line) + 1
    return inter > 0.5 * min(a.end_line - a.start_line + 1, b.end_line - b.start_line + 1)


class RepoRetriever:
    def __init__(self, vector_index, call_graph: Optional[Dict] = None, files: Optional[Dict] = None):
        self.index = vector_index
        self.call_graph = call_graph or {}
        self.files = files or {}       # path -> analyzer metadata (functions/classes)

    @property
    def available(self) -> bool:
        return self.index is not None and self.index.searchable

    # ------------------------------------------------------------------
    def retrieve(self, question: str, history: Optional[List[dict]], budget_chars: int
                 ) -> Tuple[str, List[dict]]:
        chunks: List[CodeChunk] = self.index._data[0]
        previous = self._previous_question(question, history)
        query = f"{previous[:300]}\n{question}" if previous else question
        mentioned_files = _mentioned_files(question, sorted({c.file for c in chunks}))
        candidates = self._candidates(question, previous, query, chunks, mentioned_files)
        allow_secondary = bool(_SECONDARY_QUERY_RE.search(query))
        outline = self._outline(mentioned_files)
        selected = self._select(candidates, budget_chars - len(outline), allow_secondary, set(mentioned_files))
        return outline + self._render(selected), [self._source(c) for c in selected]

    @staticmethod
    def _previous_question(question: str, history: Optional[List[dict]]) -> str:
        """Short follow-ups ("where is it called?") borrow the previous user question."""
        if history and len(question.split()) < 8:
            return next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
        return ""

    def _candidates(self, question: str, previous: str, query: str, chunks: List[CodeChunk],
                    mentioned_files: List[str]) -> List[Candidate]:
        cands: List[Candidate] = []

        # 1. Symbols named in the question (or, for follow-ups, the previous question)
        by_symbol: Dict[str, List[CodeChunk]] = {}
        for c in chunks:
            if c.symbol:
                by_symbol.setdefault(_short(c.symbol).lower(), []).append(c)
        for text, weight in ((question, 1.0), (previous, 0.8)):
            for ident, explicit in _mentioned_identifiers(text).items():
                matches = by_symbol.get(ident.lower(), [])
                if not matches or len({c.file for c in matches}) > MAX_CHUNKS_PER_SYMBOL_MENTION:
                    continue
                score = (EXPLICIT_SYMBOL_SCORE if explicit else PLAIN_WORD_SYMBOL_SCORE) * weight
                for c in matches[:MAX_CHUNKS_PER_SYMBOL_MENTION]:
                    cands.append(Candidate(c, score, "symbol"))

        # 2. Files named in the question: the file's opening chunk (docstring / imports).
        #    Its relevant parts come from step 3, boosted. (An outline is added separately.)
        mentioned = set(mentioned_files)
        for path in mentioned_files:
            first = next((c for c in chunks if c.file == path), None)
            if first:
                cands.append(Candidate(first, 1.2, "file"))

        # 3. Semantic similarity (more candidates when we need to fill mentioned files)
        penalize = not _SECONDARY_QUERY_RE.search(query)
        for c, sim in self.index.search(query, k=80 if mentioned else 40, min_score=MIN_SIMILARITY):
            score = sim
            if penalize and is_secondary(c.file):
                score *= 0.85
            if c.file in mentioned:
                score *= 1.3
            cands.append(Candidate(c, score, "semantic"))

        cands.sort(key=lambda x: x.score, reverse=True)
        cands.extend(self._graph_neighbours(question, cands, chunks))
        cands.sort(key=lambda x: x.score, reverse=True)
        return cands

    def _graph_neighbours(self, question: str, cands: List[Candidate], chunks: List[CodeChunk]) -> List[Candidate]:
        """For call-flow questions, add the code of callers (and/or callees) of the top hits."""
        want_callers = bool(_CALLERS_RE.search(question))
        want_callees = bool(_CALLEES_RE.search(question))
        if not self.call_graph or not (want_callers or want_callees):
            return []

        funcs = [c for c in chunks if c.symbol and c.kind in ("function", "method")]
        by_id: Dict[str, CodeChunk] = {f"{c.file}::{c.symbol}": c for c in reversed(funcs)}
        for c in funcs:
            by_id.setdefault(f"{c.file}::{_short(c.symbol)}", c)  # regex-parsed languages

        seeds = []
        for cand in cands:
            c = cand.chunk
            if cand.reason == "symbol" and cand.score < 1.0:
                continue  # weak plain-word match; don't expand from it
            if c.kind in ("function", "method") and c.symbol and cand.chunk not in seeds:
                seeds.append(c)
            if len(seeds) >= 2:
                break

        extra: List[Candidate] = []
        for seed in seeds:
            node = self._node(seed) or {}
            ids = (node.get("called_by", []) if want_callers else []) + (node.get("calls", []) if want_callees else [])
            added = 0
            for nid in ids:
                c = by_id.get(nid)
                if c is None or is_secondary(c.file):
                    continue
                extra.append(Candidate(c, 0.9, "graph"))
                added += 1
                if added >= MAX_GRAPH_NEIGHBOURS:
                    break
        return extra

    def _outline(self, paths: List[str]) -> str:
        """Symbol list for files the user named, so 'what does X do' sees the whole file's shape."""
        out = []
        for path in paths[:3]:
            meta = self.files.get(path) or {}
            classes, funcs = meta.get("classes", [])[:20], meta.get("functions", [])[:40]
            if classes or funcs:
                out.append(f"### Outline of {path} ({meta.get('lines', '?')} lines)\n"
                           + (f"classes: {', '.join(classes)}\n" if classes else "")
                           + (f"functions: {', '.join(funcs)}\n" if funcs else ""))
        return "\n".join(out) + ("\n" if out else "")

    def _select(self, cands: List[Candidate], budget: int, allow_secondary: bool,
                mentioned: Optional[set] = None) -> List[Candidate]:
        selected: List[Candidate] = []
        per_file: Dict[str, int] = {}
        secondary = 0
        used = 0
        mentioned = mentioned or set()
        for cand in cands:
            c = cand.chunk
            cap = MAX_CHUNKS_PER_FILE + (3 if c.file in mentioned else 0)
            if per_file.get(c.file, 0) >= cap and cand.reason == "semantic":
                continue
            secondary_file = is_secondary(c.file)
            if secondary_file and not allow_secondary and cand.reason == "semantic" and secondary >= MAX_SECONDARY_CHUNKS:
                continue
            if any(_overlaps(c, s.chunk) for s in selected):
                continue
            cost = len(c.code) + 200  # header overhead
            if used + cost > budget:
                remaining = budget - used - 200
                if remaining < 600:
                    continue  # try smaller chunks further down the list
                trimmed = CodeChunk(**{**c.to_dict(), "code": c.code[:remaining] + "\n... [truncated]"})
                cand = Candidate(trimmed, cand.score, cand.reason)
                cost = remaining + 200
            selected.append(cand)
            secondary += int(secondary_file)
            per_file[c.file] = per_file.get(c.file, 0) + 1
            used += cost
            if budget - used < 600:
                break
        return selected

    def _node(self, chunk: CodeChunk) -> Optional[Dict]:
        """The call-graph node of a function chunk. Nodes are keyed `file::Class.method` (the chunk's
        own symbol) for parsed languages and `file::name` for regex-parsed ones."""
        if not chunk.symbol:
            return None
        return self.call_graph.get(f"{chunk.file}::{chunk.symbol}") \
            or self.call_graph.get(f"{chunk.file}::{_short(chunk.symbol)}")

    def _call_info(self, chunk: CodeChunk) -> str:
        if chunk.kind not in ("function", "method") or not chunk.symbol:
            return ""
        node = self._node(chunk)
        if not node:
            return ""

        def names(ids):
            return ", ".join(sorted({i.split("::")[-1] for i in ids})[:MAX_CALL_NAMES])

        parts = []
        if node.get("calls"):
            parts.append(f"calls: {names(node['calls'])}")
        if node.get("called_by"):
            parts.append(f"called by: {names(node['called_by'])}")
        return " | ".join(parts)

    def _render(self, selected: List[Candidate]) -> str:
        if not selected:
            return ""
        # Group by file (ordered by best rank), chunks in line order within a file.
        order: List[str] = []
        groups: Dict[str, List[CodeChunk]] = {}
        for cand in selected:
            if cand.chunk.file not in groups:
                order.append(cand.chunk.file)
                groups[cand.chunk.file] = []
            groups[cand.chunk.file].append(cand.chunk)

        out = []
        for path in order:
            for c in sorted(groups[path], key=lambda x: x.start_line):
                label = f" - {c.kind} `{c.symbol}`" if c.symbol else ""
                out.append(f"### {path} (lines {c.start_line}-{c.end_line}){label}")
                info = self._call_info(c)
                if info:
                    out.append(info)
                out.append(f"```{_LANG_FENCE.get(c.language, '')}\n{c.code}\n```\n")
        return "\n".join(out)

    @staticmethod
    def _source(cand: Candidate) -> dict:
        c = cand.chunk
        return {
            "file": c.file,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "symbol": c.symbol,
            "reason": cand.reason,
        }
