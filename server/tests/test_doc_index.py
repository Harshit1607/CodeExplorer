"""
Docs and config files in the chunk index (chat, search, AI report).

README, docs/, CONTRIBUTING, Dockerfile, compose, CI workflows, .env.example and Makefile are
chunked with a `docs` / `config` tag, within a budget, and ranked so they answer setup questions
without crowding code out of code questions. No embedding model is needed: the vector index
is replaced by a fake that returns fixed similarities.
"""
import os

import pytest

from app.core import config
from app.services import vector_index as vi
from app.services.code_chunker import CodeChunk
from app.services.doc_files import chunk_doc, classify_doc_path, collect_doc_chunks, find_doc_files
from app.services.rag_retriever import MAX_DOC_CHUNKS, RepoRetriever
from app.services.semantic_search import hybrid_search


@pytest.mark.parametrize("path,tag", [
    ("README.md", "docs"),
    ("readme.rst", "docs"),
    ("packages/web/README.md", "docs"),
    ("CONTRIBUTING.md", "docs"),
    ("SETUP.md", "docs"),
    ("docs/deployment.md", "docs"),
    ("docs/guide/install.rst", "docs"),
    ("website/docs/intro.mdx", "docs"),
    ("Dockerfile", "config"),
    ("server/Dockerfile.prod", "config"),
    ("compose.yaml", "config"),
    ("docker-compose.override.yml", "config"),
    (".github/workflows/ci.yml", "config"),
    (".gitlab-ci.yml", "config"),
    (".env.example", "config"),
    ("client/.env.local.example", "config"),
    ("Makefile", "config"),
    # not docs/config: source, secrets, dependency lists, random text
    ("src/app.py", None),
    (".env", None),
    (".env.local", None),
    ("requirements.txt", None),
    ("docs/requirements.txt", None),
    ("notes.md", None),
    ("src/setup.md", None),
    ("config.yml", None),
])
def test_classify_doc_path(path, tag):
    hit = classify_doc_path(path)
    assert (hit[0] if hit else None) == tag


def test_markdown_splits_at_headings_with_exact_line_numbers():
    content = ("# Demo\n\nA demo API.\n\n## Installation\n\n```sh\npip install demo\n# not a heading\n```\n\n"
               "## Deployment\n\nBuild the image.\nRun it with compose.\n")
    chunks = chunk_doc("README.md", content, "docs")
    lines = content.splitlines()
    assert [c.symbol for c in chunks] == ["Demo", "Installation", "Deployment"]
    for c in chunks:
        assert c.tag == "docs" and c.kind == "section" and c.language == "Markdown"
        assert c.code == "\n".join(lines[c.start_line - 1:c.end_line])  # citations must be exact
    assert "pip install demo" in chunks[1].code and "# not a heading" in chunks[1].code


def test_heading_only_sections_join_the_next_and_rst_underlines_count():
    md = chunk_doc("docs/a.md", "# Project\n## Install\n\nRun make.\nThen test.\n", "docs")
    assert [(c.symbol, c.start_line) for c in md] == [("Install", 1)]
    rst = chunk_doc("docs/b.rst", "Usage\n=====\n\nCall it.\n\nDeploy\n------\n\nShip it.\n", "docs")
    assert [c.symbol for c in rst] == ["Usage", "Deploy"]
    assert rst[0].language == "reStructuredText"


def test_long_docs_are_windowed_and_config_is_one_chunk_per_window():
    long_doc = "# Guide\n" + "\n".join(f"line {i} " + "x" * 80 for i in range(200))
    chunks = chunk_doc("docs/guide.md", long_doc, "docs")
    assert len(chunks) > 5
    assert all(len(c.code) <= 1600 for c in chunks)
    assert all(b.start_line == a.end_line + 1 for a, b in zip(chunks, chunks[1:]))
    docker = chunk_doc("Dockerfile", "FROM python:3.12\nRUN pip install .\nCMD [\"app\"]\n", "config")
    assert len(docker) == 1 and docker[0].tag == "config" and docker[0].language == "Dockerfile"


@pytest.fixture
def repo(tmp_path):
    files = {
        "README.md": "# Demo\n\nWhat it is.\n\n## Deploy\n\nRun `make deploy`.\nIt pushes the image.\n",
        "CONTRIBUTING.md": "# Contributing\n\nOpen a PR.\nRun the tests first.\n",
        "docs/deployment.md": "# Deployment\n\nUse docker compose.\nSet DATABASE_URL.\n",
        "docs/deep/nested/page.md": "# Page\n\nDeep page.\nMore text.\n",
        "Dockerfile": "FROM python:3.12\nCOPY . .\nCMD [\"python\", \"-m\", \"app\"]\n",
        "compose.yaml": "services:\n  web:\n    build: .\n",
        ".github/workflows/ci.yml": "name: ci\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
        ".env.example": "DATABASE_URL=\n",
        ".env": "DATABASE_URL=postgres://secret\n",
        "Makefile": "test:\n\tpytest\n",
        "node_modules/pkg/README.md": "# Vendored\n\nnope\nnope\n",
        "src/app.py": "def main():\n    pass\n",
    }
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def _keep_dir(name):
    return name not in {"node_modules", ".git"}


def test_collect_doc_chunks_finds_the_listed_files_most_useful_first(repo):
    files = [rel for rel, _ in find_doc_files(str(repo), _keep_dir)]
    assert files[0] == "README.md"
    assert set(files) == {"README.md", "CONTRIBUTING.md", "docs/deployment.md", "docs/deep/nested/page.md",
                          "Dockerfile", "compose.yaml", ".github/workflows/ci.yml", ".env.example", "Makefile"}
    assert files.index("docs/deployment.md") > files.index("Dockerfile")  # docs pages after root files

    chunks = collect_doc_chunks(str(repo), _keep_dir)
    tags = {c.file: c.tag for c in chunks}
    assert tags["README.md"] == "docs" and tags["docs/deployment.md"] == "docs"
    assert tags["Dockerfile"] == "config" and tags[".github/workflows/ci.yml"] == "config"
    assert ".env" not in tags and "node_modules/pkg/README.md" not in tags and "src/app.py" not in tags
    assert all("secret" not in c.code for c in chunks)


def test_doc_budget_is_enforced(repo):
    assert len(collect_doc_chunks(str(repo), _keep_dir, max_chunks=3)) == 3
    few = collect_doc_chunks(str(repo), _keep_dir, max_files=2)
    assert {c.file for c in few} == {"README.md", "CONTRIBUTING.md"}


@pytest.mark.skipif(os.name == "nt", reason="symlink fixtures need a POSIX filesystem")
def test_doc_symlinks_leaving_the_repo_are_not_read(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret\n\ncanary-doc-4242\nmore\n")
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    os.symlink(outside, repo / "README.md")
    os.symlink(outside, repo / "docs" / "guide.md")
    os.symlink("/etc/passwd", repo / "Dockerfile")
    chunks = collect_doc_chunks(str(repo))
    assert chunks == []


# ---------------------------------------------------------------------------
# Index priority: docs/config survive the chunk cap, after product code
# ---------------------------------------------------------------------------
def _chunk(file, tag="code", symbol=None, kind="function", code="x = 1\n" * 5, start=1):
    return CodeChunk(id=f"{file}:{start}", file=file, language="Python" if tag == "code" else "Markdown",
                     symbol=symbol, kind=kind if tag == "code" else ("section" if tag == "docs" else "config"),
                     start_line=start, end_line=start + 4, code=code, tag=tag)


def test_index_keeps_docs_when_capped_and_drops_low_priority_code(monkeypatch):
    np = pytest.importorskip("numpy")
    monkeypatch.setattr(config, "MAX_INDEX_CHUNKS", 6)
    monkeypatch.setattr(vi.Embedder, "is_enabled", classmethod(lambda cls: True))
    monkeypatch.setattr(vi.Embedder, "get_model", classmethod(lambda cls: object()))
    monkeypatch.setattr(vi.Embedder, "embed_documents", classmethod(lambda cls, texts: np.ones((len(texts), 4), dtype=np.float32)))

    chunks = ([_chunk(f"src/m{i}.py", start=i) for i in range(5)]
              + [_chunk("tests/test_a.py"), _chunk("examples/demo.py")]
              + [_chunk("README.md", tag="docs", symbol="Install"), _chunk("Dockerfile", tag="config")])
    index = vi.VectorIndex()
    index.build(chunks)
    kept = index._data[0]
    assert index.truncated and len(kept) == 6
    assert [c.tag for c in kept] == ["code"] * 4 + ["docs", "config"]
    assert all(not c.file.startswith(("tests/", "examples/")) for c in kept)


# ---------------------------------------------------------------------------
# Chat retrieval and search ranking
# ---------------------------------------------------------------------------
class FakeIndex:
    """Stands in for VectorIndex: returns its chunks with fixed similarities."""

    def __init__(self, scored, status="ready"):
        self.scored = scored
        self._data = ([c for c, _ in scored], object())
        self.status = status

    @property
    def searchable(self):
        return True

    def search(self, query, k=50, min_score=0.0):
        return [(c, s) for c, s in self.scored if s >= min_score][:k]

    def info(self):
        n = len(self.scored)
        return {"status": self.status, "searchable": True, "indexed_chunks": n, "total_chunks": n * 2}


def _scored_mix():
    docs = [_chunk(f"docs/page{i}.md", tag="docs", symbol=f"Deploy step {i}", start=1) for i in range(5)]
    code = [_chunk(f"src/m{i}.py", symbol=f"func{i}", start=1) for i in range(5)]
    # docs score slightly higher than code
    return [(d, 0.80 - i * 0.01) for i, d in enumerate(docs)] + [(c, 0.78 - i * 0.01) for i, c in enumerate(code)]


def test_chat_caps_docs_for_code_questions_and_admits_them_for_setup_questions():
    retriever = RepoRetriever(FakeIndex(_scored_mix()))
    _, sources = retriever.retrieve("explain the core processing algorithm", None, 20000)
    assert sum(s["tag"] == "docs" for s in sources) == MAX_DOC_CHUNKS
    assert sources[0]["tag"] == "code"  # docs are mildly down-ranked for code questions

    context, sources = retriever.retrieve("how do I deploy this?", None, 20000)
    assert sum(s["tag"] == "docs" for s in sources) == 5
    assert sources[0]["tag"] == "docs"
    assert '### docs/page0.md (lines 1-5) - docs section "Deploy step 0"' in context
    assert "```markdown" in context


def test_search_returns_docs_and_config_as_their_own_types():
    scored = [(_chunk("docs/deployment.md", tag="docs", symbol="Deployment"), 0.8),
              (_chunk("Dockerfile", tag="config"), 0.79),
              (_chunk("src/deploy.py", symbol="deploy_app"), 0.78)]
    files = {"src/deploy.py": {"functions": ["deploy_app"], "classes": [], "imports": []}}

    setup = hybrid_search("how do I deploy with docker", files, FakeIndex(scored), mode="semantic")
    assert [r["type"] for r in setup["results"]] == ["docs", "config", "function"]
    assert setup["results"][0]["name"] == "Deployment" and setup["results"][0]["start_line"] == 1
    assert set(setup["grouped"]) == {"docs", "config", "function"}

    code = hybrid_search("worker orchestration logic", files, FakeIndex(scored), mode="semantic")
    assert code["results"][0]["type"] == "function"  # docs/config yield to code for code questions
