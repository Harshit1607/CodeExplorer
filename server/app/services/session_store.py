"""In-memory registry of analysis sessions with TTL / size based eviction."""
import time
from typing import Dict, List, Optional, TYPE_CHECKING

from app.core import config

if TYPE_CHECKING:
    from app.services.streaming_pipeline import StreamingPipeline


class SessionStore:
    def __init__(self, ttl_seconds: int, max_sessions: int):
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: Dict[str, "StreamingPipeline"] = {}

    def get(self, session_id: Optional[str]) -> Optional["StreamingPipeline"]:
        self.sweep()
        if not session_id:
            return None
        pipeline = self._sessions.get(session_id)
        if pipeline:
            pipeline.touch()
        return pipeline

    def add(self, session_id: str, pipeline: "StreamingPipeline") -> None:
        self.sweep()
        self._sessions[session_id] = pipeline
        self._enforce_limit()

    def sweep(self) -> None:
        """Drop cancelled sessions, and finished ones nobody has touched for `ttl` seconds."""
        now = time.time()
        expired = [sid for sid, p in self._sessions.items()
                   if p.is_done and not p.clients and (p.cancelled or now - p.last_access > self.ttl)]
        for sid in expired:
            self._sessions.pop(sid, None)

    def _enforce_limit(self) -> None:
        if len(self._sessions) <= self.max_sessions:
            return
        # Evict the least recently used *finished* sessions first.
        finished = sorted((p.last_access, sid) for sid, p in self._sessions.items()
                          if p.is_done and not p.clients)
        for _, sid in finished[:len(self._sessions) - self.max_sessions]:
            self._sessions.pop(sid, None)

    def active_count(self) -> int:
        """Analyses still running (cloning / scanning / indexing), not counting cancelled ones."""
        return sum(1 for p in self._sessions.values() if p.running)

    def running_for_client(self, client_key: str) -> List["StreamingPipeline"]:
        """Running analyses started by one client."""
        return [p for p in self._sessions.values() if p.running and p.client_key == client_key]

    def __len__(self) -> int:
        return len(self._sessions)


sessions = SessionStore(config.SESSION_TTL_SECONDS, config.MAX_SESSIONS)
