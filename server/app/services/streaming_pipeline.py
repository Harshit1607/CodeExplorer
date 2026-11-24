"""
Streaming analysis pipeline.

Stages (progress is monotonic):
   0-15  Clone          clone_progress, repo_meta
  15-50  Scan           scan_started, file_complexity_batch, file_tree
  50-95  Deep analysis  language_dist, key_files, framework_detected, file_dependencies,
                        call_graph, architecture_ready, quickstart_ready, ai_report_ready
   ||    Search index   search_index_progress, search_index_ready   (runs concurrently)
  100    Done           analysis_complete

Non-fatal problems are sent as `warning` events; only a fatal failure sends `error`.

Before cloning, the repository's current commit is looked up (`git ls-remote`). When that
`owner/repo@sha` is in the analysis cache, the stored events are replayed and the search index
is rebuilt from cached embeddings: no clone, no parsing, no embedding.

The call graph is not streamed (tens of MB on big repos): `call_graph` carries a summary and
the client queries /api/callgraph/... for the parts it shows.
"""
import asyncio
import json
import os
import re
import subprocess
import time
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from git import Repo, RemoteProgress

from app.core import config
from app.services.ai_analyzer import AIAnalyzer
from app.services.analysis_cache import analysis_key, get_cache
from app.services.architecture_service import ArchitectureAnalyzer
from app.services.call_graph_query import CallGraphQuery
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunk, CodeChunker
from app.services.fs_utils import remove_tree
from app.services.path_filters import non_primary_reason
from app.services.vector_index import VectorIndex

# Progress events where only the latest one matters: a reconnect replays just that one.
_COALESCED_EVENTS = {"clone_progress", "search_index_progress"}
# Events that describe this run rather than the repository: never stored in the cache.
_RUN_ONLY_EVENTS = {"clone_progress", "search_index_progress", "search_index_ready",
                    "analysis_complete", "error"}
_RUN_ONLY_WARNING_STAGES = {"Cloning", "Indexing"}
CACHE_FORMAT = 1


class _LiveAnalysis:
    """A finished analysis of one commit, shared read-only by every session showing it."""

    def __init__(self, payload: Dict[str, Any], index: VectorIndex):
        self.payload = payload
        self.index = index


# analysis key -> live analysis; an entry disappears with the last session holding it.
_live_analyses: "weakref.WeakValueDictionary[str, _LiveAnalysis]" = weakref.WeakValueDictionary()

HEARTBEAT = ": heartbeat\n\n"


class PipelineError(Exception):
    """Fatal error: the analysis cannot continue."""


def format_sse(event: str, stage: str, progress: int, data: Any) -> str:
    msg = {
        "event": event,
        "stage": stage,
        "progress": progress,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return f"data: {json.dumps(msg, default=str)}\n\n"


class _CloneProgress(RemoteProgress):
    """Forward git clone progress to the pipeline (throttled)."""

    def __init__(self, pipeline: "StreamingPipeline"):
        super().__init__()
        self.pipeline = pipeline
        self._last = 0.0

    def update(self, op_code, cur_count, max_count=None, message=""):
        now = time.time()
        if now - self._last < 0.5 or not max_count:
            return
        self._last = now
        op = op_code & RemoteProgress.OP_MASK
        label = {
            RemoteProgress.COUNTING: "Counting objects",
            RemoteProgress.COMPRESSING: "Compressing objects",
            RemoteProgress.RECEIVING: "Receiving objects",
            RemoteProgress.RESOLVING: "Resolving deltas",
            RemoteProgress.CHECKING_OUT: "Checking out files",
        }.get(op, "Cloning")
        pct = cur_count / max_count
        self.pipeline.emit_threadsafe("clone_progress", "Cloning", 2 + int(pct * 12), {
            "phase": label,
            "current": int(cur_count),
            "total": int(max_count),
            "message": (message or "").strip(),
        })


class StreamingPipeline:
    def __init__(self, repo_url: str, session_id: Optional[str] = None):
        self.repo_url = repo_url.strip().rstrip("/")
        self.repo_id = str(uuid.UUID(session_id)) if session_id else str(uuid.uuid4())

        base = os.environ.get("TEMP", "C:\\temp") if os.name == "nt" else "/tmp"
        self.base_dir = os.path.join(base, "codeexplorer")
        self.repo_path = os.path.join(self.base_dir, self.repo_id)
        os.makedirs(self.base_dir, exist_ok=True)

        self.analyzer = CodeAnalyzer(self.repo_path)
        self.vector_index = VectorIndex()
        self.executor = ThreadPoolExecutor(max_workers=config.ANALYSIS_WORKERS,
                                           thread_name_prefix=f"pipeline-{self.repo_id[:8]}")

        self.history: List[str] = []
        self._coalesced_at: Dict[str, int] = {}   # event -> its slot in history
        # Repository-level events, kept (by reference) for the analysis cache.
        self._replayable: List[Tuple[str, str, int, Any]] = []
        self.clients: Set[asyncio.Queue] = set()
        self.progress = 0
        self.is_done = False
        self.repo_meta: Dict[str, Any] = {"url": self.repo_url, "name": self.repo_url.split("/")[-1]}
        self.warnings: List[str] = []
        # Deep-analysis results kept server-side for chat / search (filled as stages finish).
        self.results: Dict[str, Any] = {}
        self.commit_sha: Optional[str] = None
        self.from_cache = False
        self._chunks: List[CodeChunk] = []
        self._cg_query: Optional[CallGraphQuery] = None
        self._live: Optional[_LiveAnalysis] = None
        self.started_at = time.time()
        self.last_access = time.time()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------ events
    def touch(self) -> None:
        self.last_access = time.time()

    def subscribe(self) -> Tuple[List[str], asyncio.Queue]:
        """Atomically snapshot history and register a queue (no events lost or duplicated)."""
        q: asyncio.Queue = asyncio.Queue()
        self.clients.add(q)
        self.touch()
        return list(self.history), q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)
        self.touch()

    def emit(self, event: str, stage: str, progress: Optional[int] = None,
             data: Any = None, terminal: bool = False) -> None:
        """Must be called on the event loop thread."""
        if progress is not None:
            self.progress = max(self.progress, min(progress, 100))
        data = data if data is not None else {}
        msg = format_sse(event, stage, self.progress, data)
        if event in _COALESCED_EVENTS and event in self._coalesced_at:
            self.history[self._coalesced_at[event]] = msg
        else:
            if event in _COALESCED_EVENTS:
                self._coalesced_at[event] = len(self.history)
            self.history.append(msg)
        if event not in _RUN_ONLY_EVENTS and not (event == "warning" and stage in _RUN_ONLY_WARNING_STAGES):
            self._replayable.append((event, stage, self.progress, data))
        for q in list(self.clients):
            q.put_nowait((msg, terminal))

    def emit_threadsafe(self, *args, **kwargs) -> None:
        if self.loop:
            self.loop.call_soon_threadsafe(lambda: self.emit(*args, **kwargs))

    def warn(self, stage: str, message: str) -> None:
        self.warnings.append(message)
        self.emit("warning", stage, None, {"message": message})

    async def _in_thread(self, fn, *args):
        return await self.loop.run_in_executor(self.executor, fn, *args)

    def call_graph_query(self) -> Optional[CallGraphQuery]:
        """Query view of the finished call graph (None until the call graph stage is done)."""
        graph = self.results.get("call_graph")
        if graph is None:
            return None
        if self._cg_query is None or self._cg_query.graph is not graph:
            self._cg_query = CallGraphQuery(graph)
        return self._cg_query

    # -------------------------------------------------------------------- run
    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        index_task: Optional[asyncio.Task] = None
        try:
            self.emit("clone_progress", "Cloning", 1, {"phase": "Checking for a cached analysis"})
            cached = await self._load_cached()
            if cached:
                await self._replay_cached(cached)
            else:
                meta_task = asyncio.create_task(self._fetch_repo_meta())
                await self._clone_repo()
                await meta_task
                await self._scan_files()

                index_task = asyncio.create_task(self._build_search_index())
                await self._run_deep_analysis()
                await index_task

            self.emit("analysis_complete", "Complete", 100, {
                "message": "All done",
                "files": len(self.analyzer.files),
                "duration_seconds": round(time.time() - self.started_at, 1),
                "warnings": self.warnings,
                "search_index": self.vector_index.info(),
                "commit": self.commit_sha,
                "cached": self.from_cache,
            }, terminal=True)
            if not self.from_cache:
                await self._in_thread(self._store_in_cache)
        except Exception as e:
            if index_task and not index_task.done():
                index_task.cancel()
            print(f"[{self.repo_id}] pipeline failed: {e!r}")
            self.emit("error", "Pipeline", None, {"message": str(e), "fatal": True}, terminal=True)
        finally:
            self.is_done = True
            self.touch()
            self.analyzer._file_contents.clear()
            self._replayable = []  # only needed to fill the cache
            self._chunks = []
            await self._in_thread(remove_tree, self.repo_path)
            self.executor.shutdown(wait=False)

    # ---------------------------------------------------------- stage 1: clone
    def _owner_and_name(self) -> Optional[Tuple[str, str]]:
        parts = self.repo_url.split("/")
        if len(parts) < 2:
            return None
        name = parts[-1][:-4] if parts[-1].endswith(".git") else parts[-1]
        return parts[-2], name

    async def _fetch_repo_meta(self) -> None:
        ids = self._owner_and_name()
        if not ids:
            return
        headers = {"Accept": "application/vnd.github+json"}
        if config.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(f"https://api.github.com/repos/{ids[0]}/{ids[1]}")
            if resp.status_code == 200:
                meta = resp.json()
                self.repo_meta.update({
                    "name": meta.get("name"),
                    "description": meta.get("description"),
                    "stars": meta.get("stargazers_count"),
                    "language": meta.get("language"),
                    "size": meta.get("size"),
                    "default_branch": meta.get("default_branch"),
                })
                self.emit("repo_meta", "Cloning", 2, self.repo_meta)
            elif resp.status_code in (403, 429):
                self.warn("Cloning", "GitHub API rate limit reached; repository metadata is limited. Set GITHUB_TOKEN to raise the limit.")
            else:
                self.warn("Cloning", f"GitHub API returned {resp.status_code} for repository metadata.")
        except Exception as e:
            self.warn("Cloning", f"Could not fetch repository metadata: {e}")

    async def _clone_repo(self) -> None:
        self.emit("clone_progress", "Cloning", 1, {"phase": "Starting clone"})

        progress = _CloneProgress(self)

        def _clone():
            remove_tree(self.repo_path)
            repo = Repo.clone_from(self.repo_url, self.repo_path, depth=1,
                                   single_branch=True, progress=progress)
            try:
                self.commit_sha = repo.head.commit.hexsha
            except Exception:
                pass
            try:
                return repo.active_branch.name
            except Exception:
                return None

        try:
            branch = await self._in_thread(_clone)
        except Exception as e:
            # With a progress handler, git's stderr lands in progress.error_lines.
            detail = "\n".join(progress.error_lines) + "\n" + str(getattr(e, "stderr", "") or e)
            m = re.search(r"(?:fatal|error): [^\n]+", detail)
            if m:
                reason = m.group(0).strip().rstrip("'")
            elif "exit code(128)" in detail:
                reason = "repository not found, private, or unreachable"
            else:
                reason = detail.strip().splitlines()[-1][:300]
            raise PipelineError(f"Clone failed: {reason}")

        # Fallback metadata when the GitHub API was unavailable.
        if not self.repo_meta.get("default_branch") and branch:
            self.repo_meta["default_branch"] = branch
            self.emit("repo_meta", "Cloning", 14, self.repo_meta)
        self.emit("clone_progress", "Cloning", 15, {"phase": "Clone complete"})

    # ----------------------------------------------------------- stage 2: scan
    async def _scan_files(self) -> None:
        paths = await self._in_thread(self.analyzer._get_source_files)
        paths.sort()  # deterministic ordering regardless of thread scheduling
        total = len(paths)
        self.emit("scan_started", "Scanning", 16, {"total_files": total})
        if total == 0:
            self.warn("Scanning", "No supported source files were found in this repository.")

        def _analyze(path: Path):
            return path, self.analyzer._analyze_file(path)

        done = 0
        size = max(1, config.SCAN_BATCH_SIZE)
        for i in range(0, total, size):
            batch = paths[i:i + size]
            results = await asyncio.gather(*(self._in_thread(_analyze, p) for p in batch))
            payload = []
            for path, meta in results:
                if not meta:
                    continue
                rel = str(path.relative_to(self.repo_path)).replace("\\", "/")
                self.analyzer.files[rel] = meta
                self.analyzer.all_imports.extend(meta.get("imports", []))
                payload.append({
                    "file": rel,
                    "language": meta.get("language"),
                    "lines": meta.get("lines", 0),
                    "functions": meta.get("functions", []),
                    "classes": meta.get("classes", []),
                    "imports": meta.get("imports", []),
                })
            done += len(batch)
            self.emit("file_complexity_batch", "Scanning", 16 + int(34 * done / max(total, 1)), {
                "files": payload, "processed": done, "total": total,
            })

        tree = await self._in_thread(self.analyzer._build_file_tree)
        self.emit("file_tree", "Scanning", 50, tree)

    # -------------------------------------------------- stage 3: deep analysis
    async def _run_deep_analysis(self) -> None:
        a = self.analyzer
        stage = "Analyzing"

        languages = await self._in_thread(a._language_stats)
        self.results["languages"] = languages
        self.emit("language_dist", stage, 52, languages)

        entry_points = await self._in_thread(a._entry_points)
        key_files = await self._in_thread(a._key_files)
        self.results.update(entry_points=entry_points, key_files=key_files)
        self.emit("key_files", stage, 55, {"key_files": key_files, "entry_points": entry_points})

        def _deps():
            deps = a._extract_dependencies()
            a._collect_dependency_sets(deps)
            return deps, a._detect_frameworks(), a._detect_databases()

        deps, frameworks, databases = await self._in_thread(_deps)
        self.results.update(dependencies=deps, frameworks=frameworks, databases=databases)
        self.emit("framework_detected", stage, 60, {
            "frameworks": frameworks, "databases": databases, "dependencies": deps,
        })

        file_deps = await self._in_thread(a._build_file_dependencies)
        self.results["file_dependencies"] = file_deps
        self.emit("file_dependencies", stage, 66, file_deps)

        call_graph = await self._in_thread(a._build_call_graph, file_deps, frameworks, databases)
        self.results["call_graph"] = call_graph
        # Only the summary is streamed; the graph itself is served by /api/callgraph/...
        self.emit("call_graph", stage, 74, await self._in_thread(lambda: self.call_graph_query().summary()))

        def _arch():
            return ArchitectureAnalyzer({
                "files": a.files,
                "frameworks": frameworks,
                "databases": databases,
                "file_dependencies": file_deps,
                "entry_points": entry_points,
            }).generate()

        self.emit("architecture_ready", stage, 80, await self._in_thread(_arch))

        def _qs():
            return {
                "readme": a._extract_readme(),
                "package_manager": a._detect_package_manager(),
                "run_scripts": a._extract_run_scripts(),
                "build_systems": a._build_systems(),
            }

        quickstart = await self._in_thread(_qs)
        self.results["quickstart"] = quickstart
        self.emit("quickstart_ready", stage, 84, quickstart)

        # ---- stage 4: AI report (network bound, runs while indexing continues)
        await self._ai_report()

    async def _ai_report(self) -> None:
        """Generate and emit the AI report from `self.results` (also used for cached analyses)."""
        r, files = self.results, self.analyzer.files
        try:
            report = await AIAnalyzer({
                "repoMeta": self.repo_meta,
                "languages": r.get("languages"),
                "frameworks": r.get("frameworks"),
                "databases": r.get("databases"),
                "entryPoints": r.get("entry_points"),
                "keyFiles": r.get("key_files"),
                "complexity": {"fileList": [
                    {"file": rel, "lines": m.get("lines", 0),
                     "functions": m.get("functions", []), "classes": m.get("classes", [])}
                    for rel, m in files.items()
                ]},
                "quickstart": r.get("quickstart"),
                "file_dependencies": r.get("file_dependencies"),
            }).generate_report()
        except Exception as e:
            self.warn("AI Report", f"AI report failed: {e}")
            report = {"error": str(e)}
        # A failed report is not cached: a later run of the same commit tries again.
        if not (isinstance(report, dict) and report.get("error")):
            self.results["ai_report"] = report
        self.emit("ai_report_ready", "AI Report", 92, report)

    # ----------------------------------------------- concurrent: vector index
    def _chunk_files(self) -> List[CodeChunk]:
        """Chunks of primary code. Tests, generated and vendored files are skipped (they slow
        indexing down and crowd out the product's own code) unless nothing else is left."""
        chunker = CodeChunker()
        primary: List[CodeChunk] = []
        other: List[Tuple[str, dict]] = []
        for rel, meta in self.analyzer.files.items():
            if meta.get("skipped"):
                continue
            if config.INDEX_SKIP_NON_PRIMARY and non_primary_reason(rel):
                other.append((rel, meta))
                continue
            content = self.analyzer._file_contents.get(rel) or meta.get("content", "")
            primary.extend(chunker.chunk_file(rel, content, meta.get("language", ""), meta.get("symbols")))
        self.vector_index.skipped_files = len(other) if primary else 0
        if primary:
            return primary
        for rel, meta in other:
            content = self.analyzer._file_contents.get(rel) or meta.get("content", "")
            primary.extend(chunker.chunk_file(rel, content, meta.get("language", ""), meta.get("symbols")))
        return primary

    async def _build_search_index(self, chunks: Optional[List[CodeChunk]] = None) -> None:
        stage = "Indexing"
        index = self.vector_index
        if chunks is None:
            chunks = await self._in_thread(self._chunk_files)
        self._chunks = chunks
        if not config.VECTOR_SEARCH_ENABLED:
            index.status = "unavailable"
            self.emit("search_index_ready", stage, None, index.info())
            return

        index.total_chunks = len(chunks)
        self.emit("search_index_progress", stage, None, {"status": "building", "indexed": 0, "total": len(chunks)})

        last = [0.0]

        def _progress(done: int, total: int):
            now = time.time()
            if now - last[0] >= 0.5 or done >= total:
                last[0] = now
                self.emit_threadsafe("search_index_progress", stage, None,
                                     {"status": "building", "indexed": done, "total": total,
                                      "searchable": done > 0})

        # Dedicated thread so a long embedding job never starves the analysis pool.
        await asyncio.to_thread(index.build, chunks, _progress, get_cache())
        if index.status != "ready":
            self.warn(stage, index.error or "Semantic index unavailable; search falls back to keywords.")
        self.emit("search_index_ready", stage, None, index.info())

    # ------------------------------------------------------------- analysis cache
    def _ls_remote_head(self) -> Optional[str]:
        """Current commit of the default branch, without cloning (None when unknown)."""
        try:
            out = subprocess.run(
                ["git", "ls-remote", self.repo_url, "HEAD"], capture_output=True, text=True,
                timeout=config.LS_REMOTE_TIMEOUT_SECONDS,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.SubprocessError):
            return None
        m = re.match(r"([0-9a-f]{40})\s+HEAD$", out.stdout.strip(), re.M) if out.returncode == 0 else None
        return m.group(1) if m else None

    async def _load_cached(self) -> Optional[Dict[str, Any]]:
        cache = get_cache()
        if cache is None:
            return None
        sha = await self._in_thread(self._ls_remote_head)
        if not sha:
            return None  # unreachable or private: the clone reports the real error
        key = analysis_key(self.repo_url, sha)
        live = _live_analyses.get(key)
        if live is not None:
            # Another session shows this commit right now: share its data instead of a copy.
            self._live = live
            payload = live.payload
        else:
            payload = await self._in_thread(cache.get_analysis, key)
        if not payload or payload.get("format") != CACHE_FORMAT:
            return None
        self.commit_sha = sha
        return payload

    async def _replay_cached(self, payload: Dict[str, Any]) -> None:
        """Serve a cached analysis of the same commit: replay events, rebuild the index."""
        self.from_cache = True
        self.repo_meta.update(payload.get("repo_meta") or {})
        self.analyzer.files = payload.get("files") or {}
        self.results = payload.get("results") or {}
        for event, stage, progress, data in payload.get("events") or []:
            if event == "warning":
                self.warnings.append(data.get("message", ""))
            self.emit(event, stage, progress, data)
        if "ai_report" not in self.results:
            await self._ai_report()
        if self._live is not None and self._live.index.status == "ready":
            self.vector_index = self._live.index
            self.emit("search_index_ready", "Indexing", None, self.vector_index.info())
            return
        chunks = [CodeChunk(**c) for c in payload.get("chunks") or []]
        self.vector_index.skipped_files = payload.get("index_skipped_files", 0)
        await self._build_search_index(chunks)
        self._share(payload)

    def _share(self, payload: Dict[str, Any]) -> None:
        """Offer this session's finished data to later sessions of the same commit."""
        if self.vector_index.status != "ready" or not self.commit_sha:
            return
        # The shared index already holds the chunks.
        self._live = _LiveAnalysis({**payload, "chunks": []}, self.vector_index)
        _live_analyses[analysis_key(self.repo_url, self.commit_sha)] = self._live

    def _store_in_cache(self) -> None:
        """Save a finished analysis for the next request of this commit (blocking)."""
        cache = get_cache()
        if cache is None or not self.commit_sha:
            return
        t = time.time()
        payload = {
            "format": CACHE_FORMAT,
            "repo_url": self.repo_url,
            "commit": self.commit_sha,
            "repo_meta": self.repo_meta,
            "events": [e for e in self._replayable
                       # a failed AI report is regenerated on replay instead
                       if not (e[0] == "ai_report_ready" and "ai_report" not in self.results)
                       and not (e[0] == "warning" and e[1] == "AI Report")],
            "results": self.results,
            "files": self.analyzer.files,
            "chunks": [c.to_dict() for c in self._chunks],
            "index_skipped_files": self.vector_index.skipped_files,
        }
        cache.put_analysis(analysis_key(self.repo_url, self.commit_sha), self.repo_url, self.commit_sha, payload)
        self._share(payload)
        print(f"[{self.repo_id}] cached {self.repo_url}@{self.commit_sha[:12]} in {time.time() - t:.1f}s", flush=True)
