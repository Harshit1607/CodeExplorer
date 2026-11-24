"""
On-disk cache (SQLite) of finished analyses and of chunk embeddings.

- `analyses`: one row per `owner/repo@commit-sha`, holding the replayable stream events plus
  the server-side data that chat, search and the call-graph endpoints need. A repeat analysis
  of the same commit, by anyone, is served from here without cloning or embedding.
- `embeddings`: content-addressed vectors, keyed by a hash of (model, text that was embedded).
  Unchanged chunks reuse their vectors across commits, so a new commit only embeds what changed.

An analysis is only served to the code version that produced it: the version hashes the
server's analysis code and the settings that change its output, so a deploy never serves
results of the old analyzer (embeddings stay valid; they depend only on model and text).

Both tables share one size budget (`ANALYSIS_CACHE_MAX_MB`); the least recently used rows are
evicted first. Every method is safe to call from any thread and never raises: a broken or
unwritable cache only costs speed.
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from app.core import config

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

SCHEMA_VERSION = 1
_SQL_VARS = 500  # keys per IN (...) query, well under SQLite's variable limit
_APP_DIR = Path(__file__).resolve().parent.parent


def _code_version() -> str:
    """Hash of the analysis code (app/services, app/core) and output-changing settings."""
    h = hashlib.sha1(f"{SCHEMA_VERSION}|{config.INDEX_SKIP_NON_PRIMARY}|{config.MAX_ANALYZE_BYTES}|"
                     f"{config.MAX_AVG_LINE_LENGTH}".encode())
    for sub in ("services", "core"):
        for path in sorted((_APP_DIR / sub).glob("*.py")):
            h.update(path.name.encode())
            h.update(path.read_bytes())
    return h.hexdigest()[:16]


def embedding_key(model: str, text: str) -> bytes:
    return hashlib.sha1(f"{model}\0{text}".encode("utf-8", "surrogatepass")).digest()


def analysis_key(repo_url: str, sha: str) -> str:
    """`owner/repo@sha` from a normalized https://github.com/owner/repo URL."""
    parts = repo_url.rstrip("/").split("/")
    return f"{'/'.join(parts[-2:])}@{sha}".lower()


class AnalysisCache:
    def __init__(self, directory: str, max_bytes: int):
        self.path = os.path.join(directory, "analysis-cache.sqlite3")
        self.max_bytes = max_bytes
        self.version = _code_version()
        self._lock = threading.Lock()  # one writer at a time inside this process
        self._ready = False
        self.error: Optional[str] = None
        try:
            os.makedirs(directory, exist_ok=True)
            with self._connect() as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS analyses (
                        key TEXT PRIMARY KEY, repo TEXT NOT NULL, sha TEXT NOT NULL,
                        version TEXT NOT NULL, created REAL NOT NULL, last_used REAL NOT NULL,
                        size INTEGER NOT NULL, payload BLOB NOT NULL);
                    CREATE TABLE IF NOT EXISTS embeddings (
                        key BLOB PRIMARY KEY, vec BLOB NOT NULL, last_used REAL NOT NULL);
                    CREATE INDEX IF NOT EXISTS embeddings_last_used ON embeddings(last_used);
                """)
            self._ready = True
        except (OSError, sqlite3.Error) as e:
            self.error = f"Analysis cache disabled: {e}"
            print(f"[cache] {self.error}")

    @property
    def enabled(self) -> bool:
        return self._ready

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """A short-lived connection: commits on success, rolls back on error, always closes."""
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
            with conn:
                yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------ analyses
    def get_analysis(self, key: str) -> Optional[Dict[str, Any]]:
        if not self._ready:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT payload FROM analyses WHERE key = ? AND version = ?",
                                   (key, self.version)).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE analyses SET last_used = ? WHERE key = ?", (time.time(), key))
            return json.loads(zlib.decompress(row[0]))
        except (sqlite3.Error, zlib.error, ValueError) as e:
            print(f"[cache] read failed for {key}: {e}")
            return None

    def put_analysis(self, key: str, repo: str, sha: str, payload: Dict[str, Any]) -> None:
        if not self._ready:
            return
        try:
            blob = _compress_json(payload)
            if len(blob) > self.max_bytes // 2:
                print(f"[cache] {key} is {len(blob) >> 20} MB, too large to cache")
                return
            now = time.time()
            with self._lock, self._connect() as conn:
                conn.execute("INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (key, repo, sha, self.version, now, now, len(blob), blob))
                self._enforce_limit(conn)
        except (sqlite3.Error, TypeError, ValueError) as e:
            print(f"[cache] write failed for {key}: {e}")

    # ---------------------------------------------------------------- embeddings
    def get_embeddings(self, keys: List[bytes]) -> Dict[bytes, "np.ndarray"]:
        if not self._ready or not keys or np is None:
            return {}
        found: Dict[bytes, "np.ndarray"] = {}
        try:
            with self._connect() as conn:
                for i in range(0, len(keys), _SQL_VARS):
                    part = keys[i:i + _SQL_VARS]
                    marks = ",".join("?" * len(part))
                    for key, vec in conn.execute(f"SELECT key, vec FROM embeddings WHERE key IN ({marks})", part):
                        found[bytes(key)] = np.frombuffer(vec, dtype=np.float32)
                if found:
                    now = time.time()
                    with self._lock:
                        conn.executemany("UPDATE embeddings SET last_used = ? WHERE key = ?",
                                         ((now, k) for k in found))
        except sqlite3.Error as e:
            print(f"[cache] embedding read failed: {e}")
        return found

    def put_embeddings(self, items: Iterable[Tuple[bytes, "np.ndarray"]]) -> None:
        if not self._ready or np is None:
            return
        now = time.time()
        rows = [(k, np.asarray(v, dtype=np.float32).tobytes(), now) for k, v in items]
        if not rows:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?)", rows)
        except sqlite3.Error as e:
            print(f"[cache] embedding write failed: {e}")

    def enforce_limit(self) -> None:
        if not self._ready:
            return
        try:
            with self._lock, self._connect() as conn:
                self._enforce_limit(conn)
        except sqlite3.Error as e:
            print(f"[cache] eviction failed: {e}")

    # ------------------------------------------------------------------ eviction
    def _sizes(self, conn: sqlite3.Connection) -> int:
        analyses = conn.execute("SELECT COALESCE(SUM(size), 0) FROM analyses").fetchone()[0]
        embeddings = conn.execute("SELECT COALESCE(SUM(LENGTH(vec) + 40), 0) FROM embeddings").fetchone()[0]
        return analyses + embeddings

    def _enforce_limit(self, conn: sqlite3.Connection) -> None:
        """Drop least recently used analyses / embedding batches until under the budget."""
        total = self._sizes(conn)
        while total > self.max_bytes:
            a = conn.execute("SELECT key, size, last_used FROM analyses ORDER BY last_used LIMIT 1").fetchone()
            e = conn.execute("SELECT last_used FROM embeddings ORDER BY last_used LIMIT 1").fetchone()
            if not a and not e:
                break
            if a and (not e or a[2] <= e[0]):
                conn.execute("DELETE FROM analyses WHERE key = ?", (a[0],))
                total -= a[1]
            else:
                freed = conn.execute("""SELECT COALESCE(SUM(LENGTH(vec) + 40), 0) FROM
                    (SELECT vec FROM embeddings ORDER BY last_used LIMIT 2000)""").fetchone()[0]
                conn.execute("""DELETE FROM embeddings WHERE rowid IN
                    (SELECT rowid FROM embeddings ORDER BY last_used LIMIT 2000)""")
                total -= freed

    def stats(self) -> Dict[str, Any]:
        if not self._ready:
            return {"enabled": False, "error": self.error}
        with self._connect() as conn:
            n_a = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            n_e = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            return {"enabled": True, "analyses": n_a, "embeddings": n_e,
                    "bytes": self._sizes(conn), "max_bytes": self.max_bytes}


def _compress_json(payload: Dict[str, Any]) -> bytes:
    """zlib-compressed JSON, encoded piece by piece: a big repository's payload is ~100 MB
    as one string, which would otherwise be held in memory next to its objects."""
    encoder = json.JSONEncoder(default=str, separators=(",", ":"))
    comp = zlib.compressobj(6)
    out: List[bytes] = []
    buf: List[str] = []
    size = 0
    for piece in encoder.iterencode(payload):
        buf.append(piece)
        size += len(piece)
        if size >= 1 << 20:
            out.append(comp.compress("".join(buf).encode()))
            buf, size = [], 0
    out.append(comp.compress("".join(buf).encode()))
    out.append(comp.flush())
    return b"".join(out)


_cache: Optional[AnalysisCache] = None
_cache_lock = threading.Lock()


def get_cache() -> Optional[AnalysisCache]:
    """The process-wide cache, or None when caching is disabled or unavailable."""
    global _cache
    if not config.ANALYSIS_CACHE_ENABLED:
        return None
    with _cache_lock:
        if _cache is None:
            _cache = AnalysisCache(config.ANALYSIS_CACHE_DIR, config.ANALYSIS_CACHE_MAX_MB * 1024 * 1024)
    return _cache if _cache.enabled else None
