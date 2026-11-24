"""
Big-repository behaviour: the call graph is queried instead of streamed, analyses and
embeddings are cached by commit, and tests / generated / vendored / minified code is kept
out of the expensive stages.
"""
import asyncio
import json
import subprocess

import numpy as np
import pytest

from app.core import config
from app.services import analysis_cache, streaming_pipeline
from app.services.analysis_cache import AnalysisCache, analysis_key, embedding_key
from app.services.call_graph_query import CallGraphQuery
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunk
from app.services.path_filters import is_test_path, non_primary_reason
from app.services.vector_index import Embedder, VectorIndex


# --------------------------------------------------------------------------- path filters
@pytest.mark.parametrize("path, reason", [
    ("tests/test_app.py", "test"),
    ("src/pkg/test_utils.py", "test"),
    ("pkg/conftest.py", "test"),
    ("app/tests.py", "test"),
    ("web/src/Button.test.tsx", "test"),
    ("web/src/__tests__/Button.tsx", "test"),
    ("server/handler_test.go", "test"),
    ("core/src/test/java/a/FooTest.java", "test"),
    ("test/index.js", "test"),
    ("frontend/src/routeTree.gen.ts", "generated"),
    ("api/v1/service_pb2.py", "generated"),
    ("static/js/jquery.min.js", "generated"),
    ("blog/migrations/0001_initial.py", "generated"),
    ("vendor/github.com/x/y.go", "vendored"),
    ("libs/third_party/zlib/inflate.c", "vendored"),
    # primary code, including names that merely contain "test"
    ("django/test/client.py", None),
    ("src/_pytest/python.py", None),
    ("src/contest/scoring.py", None),
    ("app/latest.py", None),
    ("src/generator.ts", None),
])
def test_non_primary_reason(path, reason):
    assert non_primary_reason(path) == reason


# ------------------------------------------------------------------------ call graph query
def _graph():
    def node(name, file, calls=(), called_by=()):
        return {"name": name, "file": file, "calls": list(calls), "called_by": list(called_by),
                "language": "Python", "type": "function"}
    return {
        "app/core.py::run": node("run", "app/core.py", calls=["app/util.py::helper", "app/db.py::save"]),
        "app/util.py::helper": node("helper", "app/util.py", calls=["app/util.py::leaf"],
                                    called_by=["app/core.py::run", "tests/test_core.py::test_run"]),
        "app/util.py::leaf": node("leaf", "app/util.py", called_by=["app/util.py::helper"]),
        "app/db.py::save": node("save", "app/db.py", called_by=["app/core.py::run"]),
        "tests/test_core.py::test_run": node("test_run", "tests/test_core.py", calls=["app/util.py::helper"]),
    }


def test_summary_counts_and_most_called_skips_tests():
    s = CallGraphQuery(_graph()).summary()
    assert s["total_functions"] == 5
    assert s["test_functions"] == 1
    assert s["total_calls"] == 4
    assert s["most_called"]["id"] == "app/util.py::helper"
    assert s["most_called"]["called_by_count"] == 2


def test_functions_hide_tests_by_default_and_page():
    q = CallGraphQuery(_graph())
    page = q.functions()
    assert page["total"] == 4
    assert all(not f["is_test"] for f in page["items"])
    assert q.functions(include_tests=True)["total"] == 5
    assert [f["name"] for f in q.functions(limit=2, offset=2)["items"]] == ["helper", "leaf"]
    assert [f["name"] for f in q.functions(file="app/util.py")["items"]] == ["helper", "leaf"]
    assert q.functions(q="SAV")["items"][0]["id"] == "app/db.py::save"
    assert q.functions(sort="called", limit=1)["items"][0]["id"] == "app/util.py::helper"


def test_neighbourhood_depth_tests_and_cap():
    q = CallGraphQuery(_graph())
    one = q.neighbourhood(["app/util.py::helper"], depth=1)
    assert set(one["nodes"]) == {"app/util.py::helper", "app/util.py::leaf", "app/core.py::run"}
    # edges only point at returned nodes; counts keep the real totals
    assert one["nodes"]["app/core.py::run"]["calls"] == ["app/util.py::helper"]
    assert one["nodes"]["app/core.py::run"]["calls_count"] == 2
    with_tests = q.neighbourhood(["app/util.py::helper"], depth=1, include_tests=True)
    assert "tests/test_core.py::test_run" in with_tests["nodes"]
    two = q.neighbourhood(["app/util.py::helper"], depth=2)
    assert "app/db.py::save" not in two["nodes"]  # a callee of a caller is not in the chain
    capped = q.neighbourhood(["app/util.py::helper"], depth=2, max_nodes=2)
    assert len(capped["nodes"]) == 2 and capped["truncated"]
    assert q.neighbourhood(["missing"], depth=2)["nodes"] == {}


def test_node_lists_callers_with_names():
    node = CallGraphQuery(_graph()).node("app/util.py::helper", include_tests=False)
    assert [c["name"] for c in node["calls"]] == ["leaf"]
    assert [c["name"] for c in node["called_by"]] == ["run"]


# --------------------------------------------------------------------------- analysis cache
def test_analysis_cache_roundtrip_and_eviction(tmp_path):
    cache = AnalysisCache(str(tmp_path), max_bytes=1 << 20)
    key = analysis_key("https://github.com/Owner/Repo", "abc123")
    assert key == "owner/repo@abc123"
    cache.put_analysis(key, "https://github.com/Owner/Repo", "abc123", {"format": 1, "x": [1, 2]})
    assert cache.get_analysis(key) == {"format": 1, "x": [1, 2]}
    assert cache.get_analysis("owner/repo@other") is None
    # Results of another analyzer version are never served (a deploy changes the version).
    newer = AnalysisCache(str(tmp_path), max_bytes=1 << 20)
    newer.version = "other-code"
    assert newer.get_analysis(key) is None

    vec = np.arange(384, dtype=np.float32)
    k = embedding_key("model", "text")
    cache.put_embeddings([(k, vec)])
    assert np.array_equal(cache.get_embeddings([k, b"missing"])[k], vec)

    # Over budget: least recently used rows go first.
    rng = np.random.default_rng(0)
    for i in range(3):
        blob = {"format": 1, "noise": rng.integers(0, 1 << 30, 40_000).tolist()}
        cache.put_analysis(f"o/r@{i}", "u", str(i), blob)
    stats = cache.stats()
    assert stats["bytes"] <= cache.max_bytes
    assert cache.get_analysis("o/r@2") is not None


def test_unwritable_cache_is_disabled_not_fatal(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    cache = AnalysisCache(str(blocker / "sub"), max_bytes=1 << 20)
    assert not cache.enabled
    assert cache.get_analysis("a@b") is None
    cache.put_analysis("a@b", "u", "b", {})  # no error


# ------------------------------------------------------------------ embedding reuse (P3)
@pytest.fixture
def fake_embedder(monkeypatch):
    calls = []

    def embed(texts):
        calls.append(len(texts))
        return np.stack([np.full(8, (len(t) % 7) + 1, dtype=np.float32) for t in texts])

    monkeypatch.setattr(Embedder, "is_enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(Embedder, "get_model", classmethod(lambda cls: object()))
    monkeypatch.setattr(Embedder, "embed_documents", classmethod(lambda cls, texts: embed(texts)))
    return calls


def _chunk(i, code):
    return CodeChunk(id=f"a.py:{i}", file="a.py", language="Python", symbol=f"f{i}",
                     kind="function", start_line=i, end_line=i, code=code)


def test_unchanged_chunks_reuse_cached_embeddings(tmp_path, fake_embedder):
    cache = AnalysisCache(str(tmp_path), max_bytes=1 << 24)
    first = VectorIndex()
    first.build([_chunk(i, f"def f{i}(): return {i}") for i in range(100)], cache=cache)
    assert first.status == "ready" and first.reused_chunks == 0
    assert sum(fake_embedder) == 100

    fake_embedder.clear()
    # Next commit: one chunk changed, one added.
    chunks = [_chunk(i, f"def f{i}(): return {i}") for i in range(100)]
    chunks[5] = _chunk(5, "def f5(): return 'changed'")
    chunks.append(_chunk(100, "def f100(): return 100"))
    second = VectorIndex()
    second.build(chunks, cache=cache)
    assert second.status == "ready"
    assert second.reused_chunks == 99
    assert sum(fake_embedder) == 2
    assert second.indexed_chunks == 101
    found, matrix = second._data
    assert len(found) == matrix.shape[0] == 101


# ------------------------------------------------------------------ analyzer: minified files
def test_minified_and_huge_files_are_counted_not_parsed(tmp_path, monkeypatch):
    (tmp_path / "app.js").write_text("function main() { helper(); }\nfunction helper() {}\n")
    (tmp_path / "bundle.js").write_text("var a=function(){return 1};" * 1000)  # one 27 KB line
    monkeypatch.setattr(config, "MAX_ANALYZE_BYTES", 40_000)
    (tmp_path / "big.py").write_text("def f():\n    return 1\n" * 3000)
    analyzer = CodeAnalyzer(str(tmp_path))
    result = analyzer.analyze()
    assert result["files"]["bundle.js"]["skipped"] == "minified"
    assert result["files"]["big.py"]["skipped"] == "too large"
    assert result["files"]["bundle.js"]["functions"] == []
    assert "main" in result["files"]["app.js"]["functions"]
    assert not any(n["file"] in ("bundle.js", "big.py") for n in result["call_graph"].values())


# ------------------------------------------------------- pipeline: stream + cache by commit
@pytest.fixture
def local_repo(tmp_path):
    repo = tmp_path / "remote" / "owner" / "demo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "core.py").write_text(
        "from src.util import helper\n\n\ndef run():\n    helper()\n    return 1\n")
    (repo / "src" / "util.py").write_text("def helper():\n    return 2\n")
    (repo / "tests" / "test_core.py").write_text(
        "from src.core import run\n\n\ndef test_run():\n    assert run() == 1\n")
    git = ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(git[:3] + ["init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)
    return repo


def _events(pipeline):
    return [json.loads(m[len("data: "):]) for m in pipeline.history]


def test_pipeline_streams_summary_and_replays_from_cache(local_repo, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "VECTOR_SEARCH_ENABLED", False)
    monkeypatch.setattr(analysis_cache, "_cache", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    async def no_meta(self):
        return None
    monkeypatch.setattr(streaming_pipeline.StreamingPipeline, "_fetch_repo_meta", no_meta)

    first = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(first.run())
    events = _events(first)
    done = events[-1]
    assert done["event"] == "analysis_complete", done
    assert done["data"]["cached"] is False and len(done["data"]["commit"]) == 40
    cg = next(e for e in events if e["event"] == "call_graph")["data"]
    # a summary only, not the graph
    assert set(cg) == {"available", "total_functions", "connected_functions", "total_calls",
                       "test_functions", "most_called"}
    assert cg["total_functions"] == 3 and cg["test_functions"] == 1
    assert sum(1 for e in events if e["event"] == "clone_progress") == 1  # coalesced
    assert first.call_graph_query().node("src/core.py::run")["calls"][0]["id"] == "src/util.py::helper"

    second = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(second.run())
    replay = _events(second)
    assert replay[-1]["data"]["cached"] is True
    assert replay[-1]["data"]["commit"] == done["data"]["commit"]
    kinds = lambda evs: sorted(e["event"] for e in evs if e["event"] not in ("clone_progress", "warning"))
    assert kinds(replay) == kinds(events)
    assert second.analyzer.files.keys() == first.analyzer.files.keys()
    assert second.call_graph_query().summary() == first.call_graph_query().summary()


def test_sessions_of_the_same_commit_share_one_copy(local_repo, tmp_path, monkeypatch, fake_embedder):
    monkeypatch.setattr(config, "ANALYSIS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "VECTOR_SEARCH_ENABLED", True)
    monkeypatch.setattr(analysis_cache, "_cache", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    async def no_meta(self):
        return None
    monkeypatch.setattr(streaming_pipeline.StreamingPipeline, "_fetch_repo_meta", no_meta)

    first = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(first.run())
    assert first.vector_index.status == "ready"
    assert first.vector_index.info()["skipped_files"] == 1  # tests/test_core.py
    embedded = sum(fake_embedder)

    second = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(second.run())
    assert second.from_cache
    assert second.analyzer.files is first.analyzer.files
    assert second.vector_index is first.vector_index
    assert sum(fake_embedder) == embedded  # nothing embedded again

    del first, second
    import gc
    gc.collect()
    assert not streaming_pipeline._live_analyses  # freed with the last session
    third = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(third.run())
    assert third.from_cache and third.vector_index.reused_chunks == third.vector_index.indexed_chunks > 0


def test_ai_report_regenerated_on_replay_reaches_later_sessions(local_repo, tmp_path, monkeypatch, fake_embedder):
    monkeypatch.setattr(config, "ANALYSIS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "VECTOR_SEARCH_ENABLED", True)
    monkeypatch.setattr(analysis_cache, "_cache", None)

    async def no_meta(self):
        return None
    monkeypatch.setattr(streaming_pipeline.StreamingPipeline, "_fetch_repo_meta", no_meta)

    llm_calls = []

    class FakeAI:
        def __init__(self, context):
            pass

        async def generate_report(self):
            llm_calls.append(1)
            if len(llm_calls) == 1:
                raise RuntimeError("rate limited")
            return {"summary": "generated"}
    monkeypatch.setattr(streaming_pipeline, "AIAnalyzer", FakeAI)

    def reports(pipeline):
        return [e["data"] for e in _events(pipeline) if e["event"] == "ai_report_ready"]

    first = streaming_pipeline.StreamingPipeline(str(local_repo))
    asyncio.run(first.run())
    assert reports(first) == [{"error": "rate limited"}]

    second = streaming_pipeline.StreamingPipeline(str(local_repo))  # replays and regenerates
    asyncio.run(second.run())
    assert reports(second) == [{"summary": "generated"}]

    third = streaming_pipeline.StreamingPipeline(str(local_repo))  # shares the live analysis
    asyncio.run(third.run())
    assert third.analyzer.files is first.analyzer.files
    assert reports(third) == [{"summary": "generated"}]

    del first, second, third
    import gc
    gc.collect()
    assert not streaming_pipeline._live_analyses
    fourth = streaming_pipeline.StreamingPipeline(str(local_repo))  # from disk only
    asyncio.run(fourth.run())
    assert fourth.from_cache
    assert reports(fourth) == [{"summary": "generated"}]
    assert len(llm_calls) == 2
