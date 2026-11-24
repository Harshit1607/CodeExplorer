"""
The AI architecture report is written from retrieved code, with checked `path:line` citations.

Covers the retrieval inputs (which excerpts go into the prompt and how they are labelled),
the citation format and checking, the prompt itself (through a mocked Groq client, so no API
key is needed), and the pipeline's bounded wait for the search index.
"""
import asyncio
import json
import textwrap
from types import SimpleNamespace

import pytest

from app.core import config
from app.services import ai_analyzer, streaming_pipeline
from app.services.ai_analyzer import AIAnalyzer
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunker
from app.services.doc_files import collect_doc_chunks
from app.services.report_grounding import (ReportGrounding, build_report_grounding, check_citations,
                                           find_citations)

MINI_PROJECT = {
    "app/__init__.py": "",
    "app/main.py": '''
        from fastapi import FastAPI
        from app.api import router


        def create_app() -> FastAPI:
            """Build the FastAPI application."""
            app = FastAPI(title="demo")
            app.include_router(router, prefix="/api")
            return app


        app = create_app()
    ''',
    "app/api.py": '''
        from fastapi import APIRouter
        from app.services import load_users

        router = APIRouter()


        @router.get("/users")
        def list_users():
            """Return every user."""
            users = load_users()
            return [u.to_dict() for u in users]
    ''',
    "app/models.py": '''
        from dataclasses import dataclass


        @dataclass
        class User:
            id: int
            name: str
            email: str

            def to_dict(self):
                return {"id": self.id, "name": self.name, "email": self.email}
    ''',
    "app/services.py": '''
        import json
        from app.models import User


        class UserService:
            """Loads users from disk."""

            def __init__(self, path="users.json"):
                self.path = path
                self.cache = None

            def all(self):
                if self.cache is None:
                    with open(self.path) as f:
                        self.cache = [User(**r) for r in json.load(f)]
                return self.cache


        def load_users():
            return UserService().all()
    ''',
    "tests/test_api.py": "from app.api import list_users\n\n\ndef test_list():\n    assert list_users() is not None\n",
    "README.md": "# Demo\n\nA demo API.\n\n## Installation\n\nRun pip install.\nThen uvicorn.\n",
    "Dockerfile": "FROM python:3.12-slim\nCOPY . .\nCMD [\"uvicorn\", \"app.main:app\"]\n",
}


@pytest.fixture
def analyzed(tmp_path):
    """(analysis result, analyzer, chunks) for the mini project, as the pipeline produces them."""
    for rel, text in MINI_PROJECT.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip("\n"))
    analyzer = CodeAnalyzer(str(tmp_path))
    result = analyzer.analyze()
    chunker = CodeChunker()
    chunks = []
    for rel, meta in analyzer.files.items():
        chunks.extend(chunker.chunk_file(rel, meta["content"], meta["language"], meta.get("symbols")))
    chunks.extend(collect_doc_chunks(str(tmp_path), analyzer._keep_dir))
    return result, analyzer, chunks


def _grounding(analyzed, index=None, budget=8000):
    result, analyzer, chunks = analyzed
    return build_report_grounding(chunks, index, result["entry_points"], result["key_files"],
                                  analyzer.found_routes, result["call_graph"], analyzer.files, budget)


class FakeIndex:
    """Stands in for VectorIndex: every query returns the same ranked chunks."""

    def __init__(self, chunks, status="ready", indexed=None):
        self.chunks = chunks
        self.status = status
        self.indexed = len(chunks) if indexed is None else indexed
        self.queries = []

    @property
    def searchable(self):
        return True

    def search(self, query, k=50, min_score=0.0):
        self.queries.append(query)
        return [(c, 0.9) for c in self.chunks][:k]

    def info(self):
        return {"status": self.status, "searchable": True, "indexed_chunks": self.indexed,
                "total_chunks": len(self.chunks)}


# ---------------------------------------------------------------------------
# Retrieval inputs
# ---------------------------------------------------------------------------
def test_report_excerpts_cover_entry_points_routes_models_and_setup(analyzed):
    g = _grounding(analyzed)
    roles = {s["reason"] for s in g.sources}
    assert {"entry_point", "route", "model", "setup"} <= roles
    files = {s["file"] for s in g.sources}
    assert "app/main.py" in files and "app/models.py" in files
    assert not any(f.startswith("tests/") for f in files)  # tests are not the architecture
    assert any(s["tag"] == "docs" for s in g.sources) and any(s["tag"] == "config" for s in g.sources)

    # The route handler is the detected route's own function.
    route = next(s for s in g.sources if s["reason"] == "route")
    assert (route["file"], route["symbol"]) == ("app/api.py", "list_users")

    # Each excerpt is real code under a `path (lines a-b)` header the model can cite.
    for s in g.sources:
        assert f"### {s['file']} (lines {s['start_line']}-{s['end_line']})" in g.context
    assert "def create_app() -> FastAPI:" in g.context
    assert "class User:" in g.context
    assert "## Entry points" in g.context and "## Data models" in g.context

    info = g.info()
    assert info["mode"] == "code" and info["excerpts"] == len(g.sources)
    assert info["semantic_retrieval"] is False and info["index_status"] == "unavailable"


def test_excerpt_lines_match_the_repository_exactly(analyzed, tmp_path):
    g = _grounding(analyzed, budget=900)  # small budget forces trimming
    assert g.sources
    assert len(g.context) < 900 + 600  # headers/fences on top of the excerpt budget
    for s in g.sources:
        lines = (tmp_path / s["file"]).read_text().splitlines()
        shown = "\n".join(lines[s["start_line"] - 1:s["end_line"]])
        assert shown in g.context, s


def test_vector_index_fills_roles_and_partial_index_is_reported(analyzed):
    result, analyzer, chunks = analyzed
    handler = next(c for c in chunks if c.symbol == "UserService")
    doc = next(c for c in chunks if c.tag == "docs")
    test_code = next(c for c in chunks if c.file.startswith("tests/"))
    index = FakeIndex([test_code, handler, doc], status="building", indexed=2)
    # A library (no backend framework, no database): nothing is labelled a route or a model.
    lib = build_report_grounding(chunks, FakeIndex([handler]), result["entry_points"], result["key_files"], [],
                                 result["call_graph"], analyzer.files, 8000, {"backend": []}, [])
    assert not any(s["reason"] in ("route", "model") and s["file"] == "app/services.py" for s in lib.sources)

    # A backend without detected routes: the route excerpt comes from the vector index (never from tests).
    g = build_report_grounding(chunks, index, result["entry_points"], result["key_files"], [],
                               result["call_graph"], analyzer.files, 8000, {"backend": ["FastAPI"]}, [])
    route = [s for s in g.sources if s["reason"] == "route"]
    assert route and route[0]["symbol"] == "UserService"
    setup = [s for s in g.sources if s["reason"] == "setup"]
    assert setup and setup[0]["tag"] == "docs"
    assert any("route handlers" in q for q in index.queries) and any("deploy" in q for q in index.queries)
    info = g.info()
    assert info["semantic_retrieval"] is True
    assert info["index_partial"] is True and (info["indexed_chunks"], info["total_chunks"]) == (2, 3)


def test_setup_excerpt_without_index_prefers_install_sections():
    from app.services.doc_files import chunk_doc
    readme = ("# Tool\n\nIntro text.\nMore.\n\n## Testing with Mailpit\n\nOpen the mail UI.\nCheck it.\n\n"
              "## Installation\n\npip install tool\nthen run it\n")
    chunks = chunk_doc("README.md", readme, "docs") + chunk_doc("Dockerfile", "FROM x\nRUN y\n", "config")
    g = build_report_grounding(chunks, None, [], [], [], {}, {}, 8000)
    assert [(s["file"], s["symbol"]) for s in g.sources] == [("README.md", "Installation"), ("Dockerfile", None)]


def test_no_chunks_means_metadata_only():
    g = build_report_grounding([], None, ["main.py"], [], [], {}, {}, 8000)
    assert g.context == "" and g.sources == [] and g.info()["mode"] == "metadata"


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------
def test_citation_format():
    text = ("Starts in `app/main.py:5-10`, see main.py:3 and ./app/api.py:L7-L9; Dockerfile:2 runs it; "
            "range app/x.py:1\u20134. Not citations: localhost:8000, python:3.12, 10:30, 127.0.0.1:80, "
            "x.py:3.12, node:18-alpine.")
    assert [k for k, *_ in find_citations(text)] == [
        "app/main.py:5-10", "main.py:3", "app/api.py:7-9", "Dockerfile:2", "app/x.py:1-4"]
    assert find_citations("app/[slug]/page.tsx:2") == [("app/[slug]/page.tsx:2", "app/[slug]/page.tsx", 2, 2, 0, 21)]


def test_citation_spans_cover_non_ascii_paths_in_ui_string_offsets():
    # The UI slices report strings with these offsets, so they are JS (UTF-16) indices:
    # "é" is one unit, "🚀" is a surrogate pair (two units). The whole non-ASCII path is the citation.
    sources = [{"file": "app/café.py", "start_line": 1, "end_line": 9, "symbol": None, "reason": "entry_point"}]
    text = "🚀 Starts in app/café.py:3, not lib/naïve.py:4."
    out = check_citations({"architecture_summary": text}, sources)
    assert out["citations"] == {"app/café.py:3": {"file": "app/café.py", "start_line": 3, "end_line": 3}}
    assert out["spans"] == {text: [
        {"at": 13, "to": 26, "verified": True, "file": "app/café.py", "start_line": 3, "end_line": 3},
        {"at": 32, "to": 46, "verified": False},
    ]}


def test_check_citations_verifies_against_the_excerpts_sent():
    sources = [{"file": "app/main.py", "start_line": 1, "end_line": 12, "symbol": None, "reason": "entry_point"},
               {"file": "app/api.py", "start_line": 7, "end_line": 11, "symbol": "list_users", "reason": "route"}]
    report = {
        "architecture_summary": "The app is built in `app/main.py:4-9` and serves app/api.py:8.",
        "module_breakdown": ["app: routes in api.py:7-11", "lib: helpers in lib/util.py:3"],
        "tech_stack_rationale": "FastAPI.",
        "entry_point_deep_dive": "app/main.py:40 then app/api.py:2",
        "onboarding_advice": ["Read main.py:1"],
    }
    out = check_citations(report, sources)
    assert out["citations"] == {
        "app/main.py:4-9": {"file": "app/main.py", "start_line": 4, "end_line": 9},
        "app/api.py:8": {"file": "app/api.py", "start_line": 8, "end_line": 8},
        "api.py:7-11": {"file": "app/api.py", "start_line": 7, "end_line": 11},  # bare name, unambiguous
        "main.py:1": {"file": "app/main.py", "start_line": 1, "end_line": 1},
    }
    # lines outside the excerpt, or a file the model was never shown, are not verified
    assert out["unverified"] == ["lib/util.py:3", "app/main.py:40", "app/api.py:2"]
    assert out["uncited_sections"] == ["tech_stack_rationale", "entry_point_deep_dive"]


# ---------------------------------------------------------------------------
# Prompt and report (mocked LLM client)
# ---------------------------------------------------------------------------
class FakeGroq:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        msg = SimpleNamespace(content=json.dumps(self.answer))
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


REPORT_INPUT = {"repoMeta": {"name": "demo"}, "languages": {"Python": {}}, "frameworks": {}, "databases": [],
                "entryPoints": ["app/main.py"], "complexity": {"fileList": []}, "quickstart": {},
                "file_dependencies": {}}


def test_report_prompt_contains_code_and_report_carries_checked_citations(analyzed):
    g = _grounding(analyzed)
    main = next(s for s in g.sources if s["file"] == "app/main.py")
    cite = f"app/main.py:{main['start_line']}-{main['end_line']}"
    client = FakeGroq({
        "architecture_summary": f"`create_app` in `{cite}` builds the app.",
        "module_breakdown": ["app: everything"],
        "tech_stack_rationale": "FastAPI.",
        "entry_point_deep_dive": f"{cite} then app/nowhere.py:3",
        "onboarding_advice": ["Install it."],
    })
    analyzer = AIAnalyzer(REPORT_INPUT, g)
    analyzer.client = client
    report = asyncio.run(analyzer.generate_report())

    prompt = client.calls[0]["messages"][1]["content"]
    assert "CODE EXCERPTS" in prompt and g.context in prompt
    assert "def create_app() -> FastAPI:" in prompt
    assert "`path:start-end`" in prompt and "Every section must contain at least one such citation" in prompt

    assert report["sources"] == g.sources
    grounding = report["grounding"]
    assert grounding["mode"] == "code" and grounding["model"] == config.GROQ_MODEL
    assert cite in grounding["citations"]
    assert grounding["unverified"] == ["app/nowhere.py:3"]
    assert grounding["uncited_sections"] == ["module_breakdown", "tech_stack_rationale", "onboarding_advice"]


def test_report_without_code_says_so_in_the_prompt():
    client = FakeGroq({"architecture_summary": "Metadata only."})
    analyzer = AIAnalyzer(REPORT_INPUT)
    analyzer.client = client
    report = asyncio.run(analyzer.generate_report())
    prompt = client.calls[0]["messages"][1]["content"]
    assert "none were available" in prompt and "Do not invent line numbers" in prompt
    assert report["grounding"]["mode"] == "metadata" and report["sources"] == []


def test_report_without_api_key_is_an_error(monkeypatch):
    monkeypatch.setattr(ai_analyzer, "groq_api_key", lambda: None)
    assert "error" in asyncio.run(AIAnalyzer(REPORT_INPUT).generate_report())


# ---------------------------------------------------------------------------
# Pipeline timing: wait for the index, but only so long
# ---------------------------------------------------------------------------
class RecordingAnalyzer:
    instances = []

    def __init__(self, data, grounding=None):
        self.grounding = grounding
        RecordingAnalyzer.instances.append(self)

    async def generate_report(self):
        return {"architecture_summary": "ok", "grounding": self.grounding.info() if self.grounding else None}


def _events(pipeline, name):
    out = []
    for raw in pipeline.history:
        msg = json.loads(raw[len("data: "):])
        if msg["event"] == name:
            out.append(msg["data"])
    return out


def _run_report(monkeypatch, analyzed, index_task_factory, wait_seconds, key="test-key", index=None):
    result, analyzer, chunks = analyzed
    monkeypatch.setattr(streaming_pipeline, "AIAnalyzer", RecordingAnalyzer)
    monkeypatch.setattr(streaming_pipeline, "groq_api_key", lambda: key)
    monkeypatch.setattr(config, "AI_REPORT_INDEX_WAIT_SECONDS", wait_seconds)
    RecordingAnalyzer.instances = []
    pipeline = streaming_pipeline.StreamingPipeline("https://github.com/a/b")
    pipeline.analyzer = analyzer
    pipeline.results.update(entry_points=result["entry_points"], key_files=result["key_files"],
                            call_graph=result["call_graph"])
    if index is not None:
        pipeline.vector_index = index

    async def scenario():
        pipeline.loop = asyncio.get_running_loop()
        pipeline.chunks = chunks
        pipeline._chunks_ready.set()
        task = asyncio.create_task(index_task_factory(pipeline))
        started = asyncio.get_running_loop().time()
        await pipeline._generate_ai_report({}, task)
        elapsed = asyncio.get_running_loop().time() - started
        task.cancel()
        return elapsed

    try:
        elapsed = asyncio.run(scenario())
    finally:
        pipeline.executor.shutdown(wait=False)
    return pipeline, elapsed


def test_report_waits_for_the_index_to_finish(monkeypatch, analyzed):
    async def index_build(pipeline):
        await asyncio.sleep(0.05)
        pipeline.vector_index.status = "ready"

    index = FakeIndex(analyzed[2][:3], status="building")
    pipeline, _ = _run_report(monkeypatch, analyzed, index_build, wait_seconds=5, index=index)
    assert _events(pipeline, "ai_report_started") == [{"waiting_for_index": True, "max_wait_seconds": 5}]
    info = _events(pipeline, "ai_report_ready")[0]["grounding"]
    assert info["index_status"] == "ready" and info["index_partial"] is False
    assert pipeline.chunks == []  # released once the report has its excerpts


def test_report_uses_the_partial_index_after_the_wait(monkeypatch, analyzed):
    async def slow_index_build(pipeline):
        await asyncio.sleep(30)

    index = FakeIndex(analyzed[2][:3], status="building", indexed=1)
    pipeline, elapsed = _run_report(monkeypatch, analyzed, slow_index_build, wait_seconds=0.1, index=index)
    assert elapsed < 5
    info = _events(pipeline, "ai_report_ready")[0]["grounding"]
    assert info["mode"] == "code" and info["index_partial"] is True and info["semantic_retrieval"] is True


def test_report_survives_a_failed_index_build(monkeypatch, analyzed):
    async def failing_index_build(pipeline):
        raise RuntimeError("embedding model unavailable")

    pipeline, _ = _run_report(monkeypatch, analyzed, failing_index_build, wait_seconds=5)
    info = _events(pipeline, "ai_report_ready")[0]["grounding"]
    assert info["mode"] == "code" and info["semantic_retrieval"] is False


def test_report_without_api_key_does_not_wait_for_the_index(monkeypatch, analyzed):
    async def slow_index_build(pipeline):
        await asyncio.sleep(30)

    pipeline, elapsed = _run_report(monkeypatch, analyzed, slow_index_build, wait_seconds=30, key=None)
    assert elapsed < 5
    assert _events(pipeline, "ai_report_started") == []
    assert RecordingAnalyzer.instances[0].grounding is None
