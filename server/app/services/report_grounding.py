"""
Grounding for the AI architecture report.

The report is written from code the model is actually shown, the same way chat is. Excerpts
come from the repository's chunks (and the vector index, when it is searchable):

  entry_point   the main function / opening code of the detected entry-point files
  key_module    the main class or function of the top key files
  route         handlers of detected HTTP routes, else vector hits for "route handlers" (backends only)
  model         classes in model/schema/entity files, else vector hits for "data models" (backends/DBs)
  setup         docs/config chunks (README, Dockerfile, CI, ...) about installing, running, deploying

Every excerpt is rendered under a `path (lines a-b)` header so the model can cite `path:line`.
The citations in the answer are then checked against the excerpts that were sent: only
citations that point into those excerpts are "verified" (and linked in the UI).
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from app.services.code_chunker import CodeChunk
from app.services.rag_retriever import MIN_SIMILARITY, Candidate, RepoRetriever, _short, is_secondary

REPORT_SECTIONS = ("architecture_summary", "module_breakdown", "tech_stack_rationale",
                   "entry_point_deep_dive", "onboarding_advice")

EXCERPT_MAX_CHARS = 1200     # per excerpt: room for several files within the prompt budget
EXCERPT_HEADER_CHARS = 120
MAX_ENTRY_POINT_FILES = 3
MAX_KEY_MODULE_FILES = 3
MAX_ROUTE_EXCERPTS = 2
MAX_MODEL_EXCERPTS = 2
MAX_SETUP_EXCERPTS = 2

ROLE_TITLES = {
    "entry_point": "Entry points",
    "key_module": "Key modules",
    "route": "HTTP routes / API handlers",
    "model": "Data models",
    "setup": "Setup, configuration and deployment (docs/config files)",
}
ROLE_QUERIES = {
    "route": "HTTP API route handlers and endpoint definitions",
    "model": "data models, database schema and ORM entity classes",
    "setup": "how to install, configure, run the tests and deploy the project",
}

_ENTRY_SYMBOLS = {"main", "create_app", "make_app", "app", "run", "start", "serve", "server",
                  "bootstrap", "init", "setup", "cli", "application", "handler"}
_MODEL_PATH_RE = re.compile(r"(^|/)(models?|schemas?|entities|entity|domain)(/|\.|_)", re.I)
# Doc headings for the setup excerpt when the index cannot be asked: best group first.
_SETUP_HEADINGS = [re.compile(p, re.I) for p in (
    r"install|setup|set up|getting started|quick ?start|requirements|prerequisites",
    r"run|usage|develop|local",
    r"deploy|docker|production|build|config",
)]

# `path:line` or `path:start-end` (also `path:L10-L20`). The path must look like a file: it has a
# directory, an extension, or is a well-known extensionless file. Rejects `localhost:8000`,
# `python:3.12`, `10:30` and IP addresses.
CITATION_RE = re.compile(r"(?<![\w/.:@+-])((?:\./)?[\w.@+-][\w.@+\[\]-]*(?:/[\w.@+\[\]-]+)*):L?(\d+)(?:\s*[-\u2013]\s*L?(\d+))?(?![\w.]*\d)")
_EXTENSIONLESS = {"dockerfile", "makefile", "gnumakefile", "jenkinsfile", "containerfile", "readme",
                  "contributing", "procfile", "gemfile", "rakefile", "vagrantfile"}
_FILE_EXT_RE = re.compile(r"\.[A-Za-z][\w]{0,9}$")


@dataclass
class ReportGrounding:
    context: str                                   # rendered excerpts, grouped by role
    sources: List[dict] = field(default_factory=list)
    index: dict = field(default_factory=dict)      # VectorIndex.info() when the excerpts were chosen
    semantic: bool = False                          # vector retrieval was used

    def info(self) -> dict:
        roles: Dict[str, int] = {}
        for s in self.sources:
            roles[s["reason"]] = roles.get(s["reason"], 0) + 1
        status = self.index.get("status", "unavailable")
        return {
            "mode": "code" if self.sources else "metadata",
            "excerpts": len(self.sources),
            "files": len({s["file"] for s in self.sources}),
            "roles": roles,
            "semantic_retrieval": self.semantic,
            "index_status": status,
            "index_partial": status == "building",
            "indexed_chunks": self.index.get("indexed_chunks", 0),
            "total_chunks": self.index.get("total_chunks", 0),
        }


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def _trim(chunk: CodeChunk, max_chars: int = EXCERPT_MAX_CHARS) -> CodeChunk:
    """Cut at a line boundary and shrink end_line to match, so cited line numbers stay exact."""
    if len(chunk.code) <= max_chars:
        return chunk
    kept, size = [], 0
    for line in chunk.code.split("\n"):
        if kept and size + len(line) + 1 > max_chars:
            break
        kept.append(line[:max_chars])
        size += len(line) + 1
    return CodeChunk(**{**chunk.to_dict(), "code": "\n".join(kept),
                        "end_line": chunk.start_line + len(kept) - 1})


def _primary(paths: Iterable[str], by_file: Dict[str, List[CodeChunk]]) -> List[str]:
    return [p for p in paths if p in by_file and not is_secondary(by_file[p][0])]


def _by_size(chunks: List[CodeChunk]) -> List[CodeChunk]:
    return sorted(chunks, key=lambda c: c.end_line - c.start_line, reverse=True)


def _entry_slot(chunks: List[CodeChunk]) -> List[CodeChunk]:
    """The entry file's main function if it has one, else its largest functions, else its opening."""
    named = [c for c in chunks if c.symbol and _short(c.symbol).lower() in _ENTRY_SYMBOLS]
    funcs = _by_size([c for c in chunks if c.kind in ("function", "method")])
    return _unique(named + funcs + chunks[:1])


def _module_slot(chunks: List[CodeChunk]) -> List[CodeChunk]:
    """A key file's main class, else its largest function, else its opening."""
    classes = _by_size([c for c in chunks if c.kind == "class" and c.symbol])
    funcs = _by_size([c for c in chunks if c.kind in ("function", "method") and c.symbol])
    return _unique(classes + funcs + chunks[:1])


def _unique(chunks: List[CodeChunk]) -> List[CodeChunk]:
    seen, out = set(), []
    for c in chunks:
        if c.id not in seen:
            seen.add(c.id)
            out.append(c)
    return out


def _semantic(index, role: str, want_docs: bool, limit: int) -> List[CodeChunk]:
    out = []
    for c, _sim in index.search(ROLE_QUERIES[role], k=40, min_score=MIN_SIMILARITY):
        if (c.tag != "code") != want_docs or is_secondary(c):
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


Slots = Dict[str, List[List[CodeChunk]]]   # role -> slots; a slot lists alternatives, best first


def _role_slots(chunks: List[CodeChunk], index, entry_points: List[str], key_files: List[str],
                routes: List[dict], has_backend: bool, has_database: bool) -> Tuple[Slots, bool]:
    by_file: Dict[str, List[CodeChunk]] = {}
    for c in chunks:
        by_file.setdefault(c.file, []).append(c)
    for file_chunks in by_file.values():
        file_chunks.sort(key=lambda c: c.start_line)
    semantic = index is not None and getattr(index, "searchable", False)
    slots: Slots = {}

    entry_files = _primary(entry_points, by_file)[:MAX_ENTRY_POINT_FILES]
    slots["entry_point"] = [_entry_slot(by_file[p]) for p in entry_files]

    module_files = [p for p in _primary(key_files, by_file) if p not in entry_files][:MAX_KEY_MODULE_FILES]
    slots["key_module"] = [_module_slot(by_file[p]) for p in module_files]

    route_chunks: List[CodeChunk] = []
    for r in routes or []:
        handler = (r.get("handler") or "").lower()
        for c in by_file.get(r.get("file", ""), []):
            if c.symbol and _short(c.symbol).lower() == handler and not is_secondary(c) and c not in route_chunks:
                route_chunks.append(c)
                break
        if len(route_chunks) >= MAX_ROUTE_EXCERPTS:
            break
    if not route_chunks and semantic and has_backend:  # a library has no routes: don't label any
        route_chunks = _semantic(index, "route", False, MAX_ROUTE_EXCERPTS)
    slots["route"] = [[c] for c in route_chunks]

    model_chunks = [c for c in chunks if c.kind == "class" and c.tag == "code"
                    and _MODEL_PATH_RE.search(c.file) and not is_secondary(c)][:MAX_MODEL_EXCERPTS]
    if not model_chunks and semantic and (has_backend or has_database):
        model_chunks = _semantic(index, "model", False, MAX_MODEL_EXCERPTS)
    slots["model"] = [[c] for c in model_chunks]

    setup_chunks = _semantic(index, "setup", True, MAX_SETUP_EXCERPTS) if semantic else []
    if not setup_chunks:
        docs = sorted((c for c in chunks if c.tag == "docs" and c.symbol and _setup_rank(c.symbol) is not None),
                      key=lambda c: (_setup_rank(c.symbol), c.file.count("/")))  # stable: root README first
        configs = sorted((c for c in chunks if c.tag == "config"),  # how it runs before what it reads
                         key=lambda c: ("Dockerfile", "YAML", "Makefile").index(c.language)
                         if c.language in ("Dockerfile", "YAML", "Makefile") else 3)
        setup_chunks = (docs[:1] + configs[:1])[:MAX_SETUP_EXCERPTS]
    slots["setup"] = [[c] for c in setup_chunks]
    return slots, semantic


def _setup_rank(heading: str) -> Optional[int]:
    return next((i for i, rx in enumerate(_SETUP_HEADINGS) if rx.search(heading)), None)


def _overlaps(a: CodeChunk, b: CodeChunk) -> bool:
    return a.file == b.file and a.start_line <= b.end_line and b.start_line <= a.end_line


# Slots are filled round-robin so a tight budget still covers every role. Specific roles go first,
# so a route handler that is also an entry file's largest function is labelled a route.
SELECTION_ORDER = ("route", "model", "entry_point", "key_module", "setup")


def build_report_grounding(chunks: Optional[List[CodeChunk]], index=None, entry_points: Optional[List[str]] = None,
                           key_files: Optional[List[str]] = None, routes: Optional[List[dict]] = None,
                           call_graph: Optional[dict] = None, files: Optional[dict] = None,
                           budget_chars: int = 8000, frameworks: Optional[dict] = None,
                           databases: Optional[List[str]] = None) -> ReportGrounding:
    """
    Pick and render the code excerpts the report is written from. Routes and models are only
    looked up by meaning when a backend framework or database was detected, so a library's
    code is never presented as "routes" or "data models".
    """
    index_info = index.info() if index is not None else {"status": "unavailable"}
    if not chunks:
        return ReportGrounding("", [], index_info, False)

    has_backend = bool((frameworks or {}).get("backend")) if isinstance(frameworks, dict) else False
    slots, semantic = _role_slots(chunks, index, entry_points or [], key_files or [], routes or [],
                                  has_backend, bool(databases))
    picked: Dict[str, List[Candidate]] = {role: [] for role in ROLE_TITLES}
    chosen: List[CodeChunk] = []
    used = 0
    rounds = max((len(v) for v in slots.values()), default=0)
    for i in range(rounds):
        for role in SELECTION_ORDER:
            if i >= len(slots.get(role, [])):
                continue
            for chunk in slots[role][i]:
                excerpt = _trim(chunk)
                cost = len(excerpt.code) + EXCERPT_HEADER_CHARS
                if any(_overlaps(excerpt, c) for c in chosen) or used + cost > budget_chars:
                    continue
                picked[role].append(Candidate(excerpt, 1.0, role))
                chosen.append(excerpt)
                used += cost
                break

    renderer = RepoRetriever(index, call_graph, files)
    sections, selected = [], []
    for role, title in ROLE_TITLES.items():  # rendered in reading order
        if picked[role]:
            sections.append(f"## {title}\n\n{renderer._render(picked[role])}")
            selected.extend(picked[role])
    return ReportGrounding("\n".join(sections), [RepoRetriever._source(c) for c in selected], index_info, semantic)


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------
def _looks_like_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "/" in path or bool(_FILE_EXT_RE.search(name)) or name.lower() in _EXTENSIONLESS


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def find_citations(text: str) -> List[Tuple[str, str, int, int, int, int]]:
    """[(key, path, start, end, at, to)] for every `path:line` / `path:start-end` in `text`.
    `key` is the normalised citation (`path:start` or `path:start-end`); `at`/`to` bound the match
    in UTF-16 code units, the unit the UI indexes its strings in."""
    out = []
    text = text or ""
    for m in CITATION_RE.finditer(text):
        path = m.group(1)
        if path.startswith("./"):
            path = path[2:]
        if not _looks_like_file(path):
            continue
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        key = f"{path}:{start}-{end}" if m.group(3) else f"{path}:{start}"
        at = _utf16_len(text[:m.start()])
        out.append((key, path, start, max(start, end), at, at + _utf16_len(m.group(0))))
    return out


def _strings(value) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


def check_citations(report: dict, sources: List[dict]) -> dict:
    """
    Check the report's citations against the excerpts the model was given.
      citations          {key: {file, start_line, end_line}}  verified: they point into a sent excerpt;
                         the range is clamped to the lines of that excerpt the model was shown
      unverified         [key]  cited a file or lines the model was not shown
      uncited_sections   sections without a single verified citation
      spans              {text: [{at, to, verified, file?, start_line?, end_line?}]}  where the
                         citations sit in each report string (UTF-16 offsets), so the UI does not parse
    A citation by bare file name (`main.py:3`) resolves when exactly one excerpt file has that name.
    """
    ranges: Dict[str, List[Tuple[int, int]]] = {}
    for s in sources:
        ranges.setdefault(s["file"], []).append((s["start_line"], s["end_line"]))
    verified: Dict[str, dict] = {}
    unverified: List[str] = []
    uncited: List[str] = []
    spans: Dict[str, List[dict]] = {}
    for section in REPORT_SECTIONS:
        section_ok = False
        for text in _strings(report.get(section)):
            text_spans = []
            for key, path, start, end, at, to in find_citations(text):
                file = path if path in ranges else None
                if file is None:  # partial path or bare file name: accept when unambiguous
                    matches = [p for p in ranges if p.endswith("/" + path)]
                    file = matches[0] if len(matches) == 1 else None
                span = {"at": at, "to": to, "verified": False}
                shown = next(((s, e) for s, e in ranges[file] if start <= e and s <= end), None) if file else None
                if shown:
                    verified[key] = {"file": file, "start_line": max(start, shown[0]), "end_line": min(end, shown[1])}
                    span.update(verified[key], verified=True)
                    section_ok = True
                elif key not in unverified:
                    unverified.append(key)
                text_spans.append(span)
            if text_spans:
                spans[text] = text_spans
        if not section_ok and report.get(section):
            uncited.append(section)
    return {"citations": verified, "unverified": unverified, "uncited_sections": uncited, "spans": spans}
