"""
GitHub URL handling: the server accepts every form the browser accepts (same rule as
client/src/lib/githubUrl.ts) and reports rejections as an SSE `error` event the
browser's EventSource can actually read.
"""
import asyncio
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api import analyze as analyze_api
from app.core import config
from app.main import app
from app.services.github_url import normalize_github_url
from app.services.session_store import sessions
from app.services.streaming_pipeline import StreamingPipeline, format_sse

CANONICAL = "https://github.com/pallets/itsdangerous"


@pytest.mark.parametrize("raw", [
    "https://github.com/pallets/itsdangerous",
    "https://github.com/pallets/itsdangerous/",
    "  https://github.com/pallets/itsdangerous  ",
    "http://github.com/pallets/itsdangerous",
    "https://www.github.com/pallets/itsdangerous",
    "http://www.github.com/pallets/itsdangerous/",
    "https://GitHub.com/pallets/itsdangerous",
    "https://github.com/pallets/itsdangerous.git",
    "https://github.com/pallets/itsdangerous.git/",
    "https://github.com/pallets/itsdangerous/tree/main",
    "https://github.com/pallets/itsdangerous/tree/main/src/itsdangerous",
    "https://github.com/pallets/itsdangerous/tree/feature/x/src/",
])
def test_accepted_forms_normalize_to_canonical(raw):
    assert normalize_github_url(raw) == CANONICAL


@pytest.mark.parametrize("raw,expected", [
    ("https://github.com/vercel/next.js", "https://github.com/vercel/next.js"),
    ("https://github.com/user/user.github.io.git", "https://github.com/user/user.github.io"),
    ("https://github.com/my-org/my_repo", "https://github.com/my-org/my_repo"),
])
def test_dots_and_underscores_in_names(raw, expected):
    assert normalize_github_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    "https://gitlab.com/pallets/itsdangerous",
    "https://github.com/pallets",
    "https://github.com/pallets/",
    "https://github.com.evil.com/pallets/itsdangerous",
    "https://evil.com/github.com/pallets/itsdangerous",
    "ftp://github.com/pallets/itsdangerous",
    "https://github.com/pallets/itsdangerous/issues",
    "https://github.com/pallets/..",
    "https://github.com/-bad/repo",
    "https://github.com/pallets/its dangerous",
    "file:///etc/passwd",
    "github.com/pallets/itsdangerous",
    "www.github.com/pallets/itsdangerous",
    "https://github.com/pallets/itsdangerous/blob/main/README.md",
    "https://github.com/pallets/itsdangerous?tab=readme-ov-file",
    "https://github.com/pallets/itsdangerous#readme",
])
def test_rejected_forms(raw):
    with pytest.raises(ValueError):
        normalize_github_url(raw)


def _sse_events(text: str) -> list:
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def test_invalid_url_is_reported_as_sse_error_event():
    client = TestClient(app)
    session_id = str(uuid.uuid4())
    resp = client.get("/api/analyze/stream", params={"repo": "https://gitlab.com/a/b", "session_id": session_id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    (event,) = _sse_events(resp.text)
    assert event["event"] == "error"
    assert event["data"]["fatal"] is True
    assert "valid GitHub repository URL" in event["data"]["message"]
    assert "rate_limited" not in event["data"]
    assert sessions.get(session_id) is None


def test_missing_repo_param_is_reported_as_sse_error_event():
    resp = TestClient(app).get("/api/analyze/stream")
    assert resp.status_code == 200
    assert _sse_events(resp.text)[0]["event"] == "error"


class _FakePipeline:
    """Stands in for StreamingPipeline so no clone happens."""

    def __init__(self, repo_url, session_id):
        self.repo_url = repo_url
        self.repo_id = session_id
        self.is_done = True
        self.clients = set()
        self.last_access = time.time()
        self.cancelled = False
        self.running = False
        self.client_key = None

    def start(self):
        pass

    def touch(self):
        pass

    def subscribe(self):
        return [format_sse("analysis_complete", "Complete", 100, {"repo": self.repo_url})], asyncio.Queue()

    def unsubscribe(self, _q):
        pass


@pytest.mark.parametrize("raw", [
    "https://www.github.com/pallets/itsdangerous",
    "http://github.com/pallets/itsdangerous",
    "https://github.com/pallets/itsdangerous/tree/main/src",
])
def test_browser_style_urls_start_an_analysis_of_the_canonical_repo(raw, monkeypatch):
    monkeypatch.setattr(analyze_api, "StreamingPipeline", _FakePipeline)
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    session_id = str(uuid.uuid4())
    resp = TestClient(app).get("/api/analyze/stream", params={"repo": raw, "session_id": session_id})
    assert resp.status_code == 200
    events = _sse_events(resp.text)
    assert events[-1]["event"] == "analysis_complete"
    assert events[-1]["data"]["repo"] == CANONICAL
    assert sessions.get(session_id).repo_url == CANONICAL


TRAVERSAL_SESSION_IDS = ["/tmp/victim", "../../victim", "..", "a/../../victim", "not-a-uuid"]


@pytest.mark.parametrize("session_id", TRAVERSAL_SESSION_IDS)
def test_non_uuid_session_id_is_rejected_before_any_pipeline_is_created(session_id, monkeypatch):
    created = []
    monkeypatch.setattr(analyze_api, "StreamingPipeline", lambda *a: created.append(a))
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    resp = TestClient(app).get("/api/analyze/stream", params={"repo": CANONICAL, "session_id": session_id})
    (event,) = _sse_events(resp.text)
    assert event["event"] == "error"
    assert event["data"]["fatal"] is True
    assert created == []
    assert sessions.get(session_id) is None


@pytest.mark.parametrize("session_id", TRAVERSAL_SESSION_IDS)
def test_pipeline_refuses_clone_path_outside_its_base_dir(session_id):
    with pytest.raises(ValueError):
        StreamingPipeline(CANONICAL, session_id)
