"""
Server file-read safety.

A cloned repository is untrusted input: a committed symlink such as `src/x.py -> /etc/passwd`
or `README.md -> /proc/self/environ` must never be read, or the target's contents leak into
analysis results, search results and the LLM prompt. And no endpoint may analyze an
arbitrary server directory.
"""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.code_analyzer import CodeAnalyzer
from app.services.fs_utils import inside_repo, read_repo_text

CANARY = "canary-not-a-real-secret-4242"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="symlink fixtures need a POSIX filesystem")


@pytest.fixture
def leaky_repo(tmp_path):
    """A repo whose symlinks point outside it, next to a host directory holding a canary."""
    host = tmp_path / "host"
    (host / "secrets").mkdir(parents=True)
    secret = host / "secret.py"
    secret.write_text(f'API_KEY = "{CANARY}"\ndef leak():\n    return API_KEY\n')
    (host / "secrets" / "main.py").write_text(f'TOKEN = "{CANARY}"\n')
    pkg = host / "package.json"
    pkg.write_text(json.dumps({"name": CANARY, "main": "index.js",
                               "dependencies": {CANARY: "1.0.0", "express": "4"},
                               "scripts": {"start": f"echo {CANARY}"}}))
    text = host / "notes.txt"
    text.write_text(f"{CANARY} postgres mongodb redis spring-boot rails laravel\n")

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "real.py").write_text("def real():\n    return 1\n")
    (repo / "src" / "app.py").write_text("from src.real import real\n\ndef main():\n    real()\n")
    links = {
        # source files the analyzer, chunker and chat fallback would read
        "src/settings.py": secret,
        "src/passwd.py": "/etc/passwd",
        "src/environ.py": "/proc/self/environ",
        # a symlinked directory leading outside
        "linked": host / "secrets",
        # manifest / README / .env / compose / pom readers
        "package.json": pkg,
        "requirements.txt": text,
        "pyproject.toml": text,
        "Cargo.toml": text,
        "Makefile": text,
        "tsconfig.json": text,
        "README.md": text,
        ".env": text,
        "docker-compose.yml": text,
        "pom.xml": text,
        "Gemfile": text,
        "composer.json": text,
        "prisma": host,  # prisma/schema.prisma through a symlinked dir
    }
    (host / "schema.prisma").write_text(f"// {CANARY}\nprovider = \"postgresql\"\n")
    for rel, target in links.items():
        os.symlink(target, repo / rel)
    # A symlink that stays inside the repository is fine to follow.
    os.symlink("real.py", repo / "src" / "alias.py")
    return repo


def test_symlinks_leaving_the_repo_are_never_read(leaky_repo):
    analyzer = CodeAnalyzer(str(leaky_repo))
    result = analyzer.analyze()
    dumped = json.dumps(result, default=str)

    assert CANARY not in dumped
    assert "root:x:0:0" not in dumped
    assert "PATH=" not in dumped  # nothing from /proc/self/environ
    for leaked in ("src/settings.py", "src/passwd.py", "src/environ.py"):
        assert leaked not in result["files"]
    assert not any(f.startswith("linked/") for f in result["files"])
    assert result["readme"] is None
    assert result["databases"] == []
    assert result["frameworks"]["backend"] == []
    assert result["run_scripts"] is None

    # Real files, and symlinks that stay inside the repo, are still analyzed.
    assert {"src/real.py", "src/app.py", "src/alias.py"} <= set(result["files"])


def test_source_listing_and_single_file_reads_skip_escaping_links(leaky_repo):
    analyzer = CodeAnalyzer(str(leaky_repo))
    listed = {p.relative_to(leaky_repo).as_posix() for p in analyzer._get_source_files()}
    assert listed == {"src/real.py", "src/app.py", "src/alias.py"}
    # Even if a caller hands one over directly, it is not read.
    assert analyzer._analyze_file(leaky_repo / "src" / "settings.py") is None
    assert CANARY not in json.dumps(analyzer._file_contents)


def test_read_repo_text_rules(leaky_repo):
    assert read_repo_text(leaky_repo, "src/real.py").startswith("def real")
    assert read_repo_text(leaky_repo, "src/alias.py").startswith("def real")
    assert read_repo_text(leaky_repo, "src/settings.py") is None
    assert read_repo_text(leaky_repo, "README.md") is None
    assert read_repo_text(leaky_repo, "prisma/schema.prisma") is None
    assert read_repo_text(leaky_repo, "../host/secret.py") is None
    assert read_repo_text(leaky_repo, "/etc/passwd") is None
    assert read_repo_text(leaky_repo, "missing.py") is None
    assert read_repo_text(leaky_repo, "src") is None  # directories are not files
    assert not inside_repo(leaky_repo, "linked/main.py")


def test_repo_under_a_symlinked_parent_still_works(leaky_repo, tmp_path):
    # e.g. macOS /tmp -> /private/tmp: the repo root itself may sit behind a symlink.
    alias = tmp_path / "alias-root"
    os.symlink(leaky_repo, alias)
    result = CodeAnalyzer(str(alias)).analyze()
    assert {"src/real.py", "src/app.py"} <= set(result["files"])
    assert CANARY not in json.dumps(result, default=str)


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/structure"),
    ("GET", "/api/structure/anything"),
    ("POST", "/api/analyze"),
])
def test_legacy_server_path_endpoints_are_gone(method, path):
    client = TestClient(app)
    server_dir = str(Path(__file__).resolve().parents[1] / "app")
    resp = client.request(method, path, json={"repo_path": server_dir, "repo_url": "https://github.com/a/b"})
    assert resp.status_code in (404, 405)
    assert "GROQ" not in resp.text and "def " not in resp.text
