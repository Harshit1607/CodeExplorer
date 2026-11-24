"""
Streaming analysis pipeline.

Stages (progress is monotonic):
   0-15  Clone          clone_progress, repo_meta
  15-50  Scan           scan_started, file_complexity_batch, file_tree
  50-85  Deep analysis  language_dist, key_files, framework_detected, file_dependencies,
                        call_graph, architecture_ready, quickstart_ready
  86-92  AI report      ai_report_started, ai_report_ready   (waits for the search index, bounded,
                        so the report is written from retrieved code; see report_grounding.py)
   ||    Search index   search_index_progress, search_index_ready   (runs concurrently)
  100    Done           analysis_complete

Non-fatal problems are sent as `warning` events; only a fatal failure sends `error`.
"""
import asyncio
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from git import Repo, RemoteProgress

from app.core import config
from app.services.ai_analyzer import AIAnalyzer
from app.services.architecture_service import ArchitectureAnalyzer
from app.services.code_analyzer import CodeAnalyzer
from app.services.code_chunker import CodeChunk, CodeChunker
from app.services.doc_files import collect_doc_chunks
from app.services.fs_utils import remove_tree
from app.services.llm import groq_api_key
from app.services.report_grounding import build_report_grounding
from app.services.vector_index import VectorIndex

HEARTBEAT = ": heartbeat\n\n"


class PipelineError(Exception):
    """Fatal error: the analysis cannot continue. Its message is shown to the user."""


class PipelineCancelled(Exception):
    """Raised inside worker threads to stop work for a cancelled pipeline."""


INTERNAL_ERROR_MESSAGE = "The analysis failed because of an internal error. Please try again."

# Clone folders are named `<session uuid>-<8 hex>`; only names like that are ever deleted
# from CLONE_DIR, so pointing it at a shared directory can't wipe unrelated files.
_CLONE_NAME_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(-[0-9a-f]{8})?$")


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill git and its helpers (git-remote-https, index-pack), which hold its stderr pipe open."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(proc.pid, signal.SIGKILL)   # git leads its own process group (start_new_session)
    except (OSError, subprocess.SubprocessError):
        pass
    if proc.poll() is None:
        proc.kill()


def clean_clone_dir(base_dir: Optional[str] = None) -> int:
    """Delete clone folders left behind by a previous server run. Returns how many were removed."""
    base_dir = base_dir or config.CLONE_DIR
    try:
        names = os.listdir(base_dir)
    except OSError:
        return 0
    removed = 0
    for name in names:
        path = os.path.join(base_dir, name)
        if _CLONE_NAME_RE.match(name) and os.path.isdir(path) and not os.path.islink(path):
            remove_tree(path)
            removed += 1
    if removed:
        print(f"Removed {removed} orphaned clone folder(s) from {base_dir}")
    return removed


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

        self.base_dir = config.CLONE_DIR
        # Unique per pipeline, so a restarted session never shares a folder with the old one.
        self.repo_path = os.path.join(self.base_dir, f"{self.repo_id}-{uuid.uuid4().hex[:8]}")
        os.makedirs(self.base_dir, exist_ok=True)

        self.analyzer = CodeAnalyzer(self.repo_path)
        self.vector_index = VectorIndex()
        self.executor = ThreadPoolExecutor(max_workers=config.ANALYSIS_WORKERS,
                                           thread_name_prefix=f"pipeline-{self.repo_id[:8]}")

        self.history: List[str] = []
        self.clients: Set[asyncio.Queue] = set()
        self.progress = 0
        self.is_done = False
        self.repo_meta: Dict[str, Any] = {"url": self.repo_url, "name": self.repo_url.split("/")[-1]}
        self.warnings: List[str] = []
        # Deep-analysis results kept server-side for chat / search (filled as stages finish).
        self.results: Dict[str, Any] = {}
        # Every chunk (code + docs/config), kept until the AI report has picked its excerpts.
        self.chunks: List[CodeChunk] = []
        self._chunks_ready = asyncio.Event()
        self.started_at = time.time()
        self.last_access = time.time()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client_key: Optional[str] = None   # who started it (per-client limit)
        self.cancelled = False
        self._task: Optional[asyncio.Task] = None
        self._abandon_timer: Optional[asyncio.TimerHandle] = None
        self._clone_proc: Optional[subprocess.Popen] = None
        self._clone_timed_out = False

    # ------------------------------------------------------------------ events
    def touch(self) -> None:
        self.last_access = time.time()

    def subscribe(self) -> Tuple[List[str], asyncio.Queue]:
        """Atomically snapshot history and register a queue (no events lost or duplicated)."""
        q: asyncio.Queue = asyncio.Queue()
        self.clients.add(q)
        self.touch()
        if self._abandon_timer:
            self._abandon_timer.cancel()
            self._abandon_timer = None
        return list(self.history), q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.clients.discard(q)
        self.touch()
        if not self.clients and self.running and self._abandon_timer is None:
            # Nobody is watching: cancel after a grace period unless a viewer (re)connects.
            loop = self.loop
            if loop is None or loop.is_closed():
                return
            grace = max(0, config.ANALYSIS_ABANDON_GRACE_SECONDS)
            loop.call_soon_threadsafe(self._arm_abandon_timer, grace)

    def _arm_abandon_timer(self, grace: float) -> None:
        if self._abandon_timer is None and not self.clients and self.running:
            self._abandon_timer = self.loop.call_later(grace, self._cancel_if_abandoned)

    def _cancel_if_abandoned(self) -> None:
        self._abandon_timer = None
        if not self.clients and self.running:
            print(f"[{self.repo_id}] no viewers left; cancelling analysis")
            self.cancel()

    # ------------------------------------------------------------- lifecycle
    @property
    def running(self) -> bool:
        """Still working and not cancelled (counts against the concurrency limits)."""
        return not self.is_done and not self.cancelled

    def start(self) -> asyncio.Task:
        self.loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self.run())
        return self._task

    def cancel(self) -> None:
        """Stop the analysis: kill a running clone and cancel the pipeline task."""
        if self.is_done or self.cancelled:
            return
        self.cancelled = True
        proc = self._clone_proc
        if proc and proc.poll() is None:
            _kill_tree(proc)
        if self._task and not self._task.done():
            self._task.cancel()

    def emit(self, event: str, stage: str, progress: Optional[int] = None,
             data: Any = None, terminal: bool = False) -> None:
        """Must be called on the event loop thread."""
        if progress is not None:
            self.progress = max(self.progress, min(progress, 100))
        msg = format_sse(event, stage, self.progress, data if data is not None else {})
        self.history.append(msg)
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

    # -------------------------------------------------------------------- run
    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        index_task: Optional[asyncio.Task] = None
        try:
            # Metadata first: its size decides whether the repository may be cloned at all.
            await self._fetch_repo_meta()
            self._check_repo_size()
            await self._clone_repo()
            await self._scan_files()

            index_task = asyncio.create_task(self._build_search_index())
            report_input = await self._run_deep_analysis()
            await self._generate_ai_report(report_input, index_task)
            await index_task

            self.emit("analysis_complete", "Complete", 100, {
                "message": "All done",
                "files": len(self.analyzer.files),
                "duration_seconds": round(time.time() - self.started_at, 1),
                "warnings": self.warnings,
                "search_index": self.vector_index.info(),
            }, terminal=True)
        except (asyncio.CancelledError, PipelineCancelled):
            self.cancelled = True
            if index_task and not index_task.done():
                index_task.cancel()
            self.emit("error", "Pipeline", None,
                      {"message": "The analysis was cancelled.", "fatal": True}, terminal=True)
        except Exception as e:
            if index_task and not index_task.done():
                index_task.cancel()
            print(f"[{self.repo_id}] pipeline failed: {e!r}")
            message = str(e) if isinstance(e, PipelineError) else INTERNAL_ERROR_MESSAGE
            self.emit("error", "Pipeline", None, {"message": message, "fatal": True}, terminal=True)
        finally:
            self.is_done = True
            self.touch()
            if self._abandon_timer:
                self._abandon_timer.cancel()
                self._abandon_timer = None
            self.chunks = []
            self.analyzer._file_contents.clear()
            self.executor.shutdown(wait=False, cancel_futures=True)
            await asyncio.to_thread(remove_tree, self.repo_path)

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
            # Renamed / transferred repositories answer with a redirect to the new location.
            async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
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
            print(f"[{self.repo_id}] repository metadata request failed: {e!r}")
            self.warn("Cloning", "Could not fetch repository metadata from GitHub.")

    def _check_repo_size(self) -> None:
        """Refuse repositories above MAX_REPO_SIZE_MB (GitHub reports `size` in KB)."""
        limit_mb = config.MAX_REPO_SIZE_MB
        size_kb = self.repo_meta.get("size")
        if limit_mb <= 0 or not isinstance(size_kb, (int, float)):
            return
        if size_kb > limit_mb * 1024:
            raise PipelineError(f"Repository is too large to analyze ({size_kb / 1024:,.0f} MB; "
                                f"this server's limit is {limit_mb:,} MB).")

    async def _clone_repo(self) -> None:
        self.emit("clone_progress", "Cloning", 3, {"phase": "Starting clone"})

        progress = _CloneProgress(self)
        try:
            branch = await self._in_thread(self._run_clone, progress)
        except (PipelineError, PipelineCancelled):
            raise
        except Exception as e:
            print(f"[{self.repo_id}] clone failed: {e!r}")
            raise PipelineError("Clone failed: could not run git.")

        # Fallback metadata when the GitHub API was unavailable.
        if not self.repo_meta.get("default_branch") and branch:
            self.repo_meta["default_branch"] = branch
            self.emit("repo_meta", "Cloning", 14, self.repo_meta)
        self.emit("clone_progress", "Cloning", 15, {"phase": "Clone complete"})

    def _run_clone(self, progress: RemoteProgress) -> Optional[str]:
        """Shallow-clone into repo_path (blocking). Killed on timeout or cancellation."""
        remove_tree(self.repo_path)
        if self.cancelled:
            raise PipelineCancelled()
        cmd = ["git", "clone", "--depth", "1", "--single-branch", "--progress",
               "--", self.repo_url, self.repo_path]
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # never wait for credentials
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, env=env, start_new_session=True)
        self._clone_proc = proc
        if self.cancelled:   # cancel() ran before the process handle was published
            _kill_tree(proc)

        def _on_timeout():
            if proc.poll() is None:
                self._clone_timed_out = True
                _kill_tree(proc)

        timer = None
        if config.CLONE_TIMEOUT_SECONDS > 0:
            timer = threading.Timer(config.CLONE_TIMEOUT_SECONDS, _on_timeout)
            timer.daemon = True
            timer.start()
        tail: List[str] = []
        try:
            # git separates progress updates with \r and messages with \n.
            buf = b""
            while True:
                chunk = proc.stderr.read1(4096) if hasattr(proc.stderr, "read1") else proc.stderr.read(4096)
                if not chunk:
                    break
                buf += chunk
                *lines, buf = re.split(rb"[\r\n]", buf)
                for raw in lines:
                    line = raw.decode("utf-8", "replace").rstrip()
                    if line:
                        progress._parse_progress_line(line)
                        tail = (tail + [line])[-20:]
            if buf.strip():
                tail.append(buf.decode("utf-8", "replace").strip())
            code = proc.wait()
        finally:
            if timer:
                timer.cancel()
            if proc.stderr:
                proc.stderr.close()
            self._clone_proc = None

        if self.cancelled:
            raise PipelineCancelled()
        if self._clone_timed_out:
            raise PipelineError(f"Clone failed: timed out after {config.CLONE_TIMEOUT_SECONDS}s.")
        if code != 0:
            detail = "\n".join(progress.error_lines + tail)
            m = re.search(r"(?:fatal|error): [^\n]+", detail)
            reason = m.group(0).strip().rstrip("'") if m else "repository not found, private, or unreachable"
            raise PipelineError(f"Clone failed: {reason}")
        try:
            return Repo(self.repo_path).active_branch.name
        except Exception:
            return None

    # ----------------------------------------------------------- stage 2: scan
    async def _scan_files(self) -> None:
        paths = await self._in_thread(self.analyzer._get_source_files)
        paths.sort()  # deterministic ordering regardless of thread scheduling
        total = len(paths)
        self.emit("scan_started", "Scanning", 16, {"total_files": total})
        if total == 0:
            self.warn("Scanning", "No supported source files were found in this repository.")

        def _analyze(path: Path):
            if self.cancelled:
                return path, None
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
    async def _run_deep_analysis(self) -> Dict[str, Any]:
        """Runs the static analysis stages; returns the metadata the AI report is written from."""
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
        self.emit("file_dependencies", stage, 66, file_deps)

        call_graph = await self._in_thread(a._build_call_graph, file_deps, frameworks, databases)
        self.results["call_graph"] = call_graph
        self.emit("call_graph", stage, 74, call_graph)

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

        return {
            "repoMeta": self.repo_meta,
            "languages": languages,
            "frameworks": frameworks,
            "databases": databases,
            "entryPoints": entry_points,
            "keyFiles": key_files,
            "complexity": {"fileList": [
                {"file": rel, "lines": m.get("lines", 0),
                 "functions": m.get("functions", []), "classes": m.get("classes", [])}
                for rel, m in a.files.items()
            ]},
            "quickstart": quickstart,
            "file_dependencies": file_deps,
        }

    # ------------------------------------------------------ stage 4: AI report
    async def _generate_ai_report(self, report_input: Dict[str, Any], index_task: asyncio.Task) -> None:
        """
        Write the report from retrieved code. The index finishes long after the static analysis
        (seconds vs minutes on big repos), so wait for it, but at most AI_REPORT_INDEX_WAIT_SECONDS;
        then use the part that is already searchable (product code is embedded first).
        """
        stage = "AI Report"
        try:
            grounding = None
            if groq_api_key():  # without a key the report is an error message; don't wait for it
                await self._chunks_ready.wait()  # chunking is quick; embedding is what takes time
                waiting = not index_task.done()
                self.emit("ai_report_started", stage, 86, {
                    "waiting_for_index": waiting,
                    "max_wait_seconds": config.AI_REPORT_INDEX_WAIT_SECONDS,
                })
                if waiting:
                    try:
                        await asyncio.wait_for(asyncio.shield(index_task),
                                               timeout=max(0, config.AI_REPORT_INDEX_WAIT_SECONDS))
                    except asyncio.TimeoutError:
                        pass  # use the partial index
                    except Exception:
                        pass  # the index task reports its own failure; ground on chunks alone
                a = self.analyzer
                grounding = await self._in_thread(lambda: build_report_grounding(
                    self.chunks, self.vector_index, self.results.get("entry_points"),
                    self.results.get("key_files"), a.found_routes, self.results.get("call_graph"),
                    a.files, config.AI_REPORT_CODE_CHARS, self.results.get("frameworks"),
                    self.results.get("databases")))
            report = await AIAnalyzer(report_input, grounding).generate_report()
            self.emit("ai_report_ready", stage, 92, report)
        except Exception as e:
            print(f"[{self.repo_id}] AI report failed: {e!r}")
            self.warn(stage, "AI report failed.")
            self.emit("ai_report_ready", stage, 92, {"error": "Failed to generate AI report."})
        finally:
            self.chunks = []  # the index keeps what it embedded; drop the rest

    # ----------------------------------------------- concurrent: vector index
    async def _build_search_index(self) -> None:
        stage = "Indexing"
        index = self.vector_index

        def _chunk():
            chunker = CodeChunker()
            chunks = []
            for rel, meta in self.analyzer.files.items():
                content = self.analyzer._file_contents.get(rel) or meta.get("content", "")
                chunks.extend(chunker.chunk_file(rel, content, meta.get("language", ""), meta.get("symbols")))
            # README, docs/, Dockerfile, compose, CI, .env.example, Makefile (tagged docs/config)
            chunks.extend(collect_doc_chunks(str(self.repo_path), self.analyzer._keep_dir))
            return chunks

        try:
            # Chunked even without vector search: the AI report quotes entry points and key files.
            chunks = await self._in_thread(_chunk)
            self.chunks = chunks
        finally:
            self._chunks_ready.set()

        if not config.VECTOR_SEARCH_ENABLED:
            index.status = "unavailable"
            self.emit("search_index_ready", stage, None, index.info())
            return

        index.total_chunks = len(chunks)
        self.emit("search_index_progress", stage, None, {"status": "building", "indexed": 0, "total": len(chunks)})

        last = [0.0]

        def _progress(done: int, total: int):
            if self.cancelled:
                raise PipelineCancelled()   # stops the embedding loop after this batch
            now = time.time()
            if now - last[0] >= 0.5 or done >= total:
                last[0] = now
                self.emit_threadsafe("search_index_progress", stage, None,
                                     {"status": "building", "indexed": done, "total": total,
                                      "searchable": done > 0})

        # Dedicated thread so a long embedding job never starves the analysis pool.
        await asyncio.to_thread(index.build, chunks, _progress)
        if index.status != "ready":
            self.warn(stage, index.error or "Semantic index unavailable; search falls back to keywords.")
        self.emit("search_index_ready", stage, None, index.info())
