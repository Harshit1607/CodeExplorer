"""
In-memory, per-client sliding-window rate limiting.

Rules are configured as strings like "6/minute;100/day" (also "5/10min", "30/s").
Limits are kept in process memory, which matches the rest of the server (sessions and
vector indexes are in-memory too): run a single worker, or put a shared limiter
(e.g. Redis) in front if you scale out.
"""
import math
import re
import threading
import time
from bisect import bisect_right
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request

from app.core import config

_UNIT_SECONDS = {
    "s": 1, "sec": 1, "second": 1,
    "m": 60, "min": 60, "minute": 60,
    "h": 3600, "hr": 3600, "hour": 3600,
    "d": 86400, "day": 86400,
}
_LIMIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*([a-z]+?)s?\s*$", re.I)


@dataclass(frozen=True)
class Limit:
    count: int
    seconds: int

    def __str__(self) -> str:
        return f"{self.count} per {self.seconds}s"


def parse_limits(spec: str) -> List[Limit]:
    """'6/minute;100/day' -> [Limit(6, 60), Limit(100, 86400)]. Empty/'off' -> []."""
    limits = []
    if not spec or spec.strip().lower() in {"off", "none", "0"}:
        return limits
    for part in re.split(r"[;,]", spec):
        if not part.strip():
            continue
        m = _LIMIT_RE.match(part)
        if not m or m.group(3).lower() not in _UNIT_SECONDS:
            raise ValueError(f"Invalid rate limit {part!r}; expected e.g. '10/minute' or '5/10min'")
        count, mult, unit = int(m.group(1)), int(m.group(2) or 1), m.group(3).lower()
        limits.append(Limit(count, mult * _UNIT_SECONDS[unit]))
    return limits


class RateLimiter:
    """Sliding-window log per (rule, client). Thread-safe (sync endpoints run in a threadpool)."""

    SWEEP_EVERY = 1000  # calls between pruning idle clients

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: Dict[Tuple[str, str], List[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def hit(self, rule: str, key: str, limits: List[Limit]) -> Optional[float]:
        """Record a request. Returns None if allowed, else seconds until it would be allowed."""
        if not limits:
            return None
        now = self._clock()
        longest = max(l.seconds for l in limits)
        with self._lock:
            self._maybe_sweep(now)
            hits = self._hits.setdefault((rule, key), [])
            # Drop timestamps outside the longest window.
            cut = bisect_right(hits, now - longest)
            if cut:
                del hits[:cut]

            retry_after = 0.0
            for limit in limits:
                start = bisect_right(hits, now - limit.seconds)
                in_window = len(hits) - start
                if in_window >= limit.count:
                    # Allowed again once the oldest request that keeps us at the limit expires.
                    oldest_blocking = hits[start + in_window - limit.count]
                    retry_after = max(retry_after, oldest_blocking + limit.seconds - now)
            if retry_after > 0:
                return retry_after
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _maybe_sweep(self, now: float) -> None:
        self._calls += 1
        if self._calls % self.SWEEP_EVERY:
            return
        horizon = max((l.seconds for ls in RULES.values() for l in ls), default=86400)
        for key in [k for k, v in self._hits.items() if not v or v[-1] < now - horizon]:
            del self._hits[key]


# ----------------------------------------------------------------------------
# Configured rules
# ----------------------------------------------------------------------------
RULES: Dict[str, List[Limit]] = {
    "analyze": parse_limits(config.RATE_LIMIT_ANALYZE),
    "chat": parse_limits(config.RATE_LIMIT_CHAT),
    "search": parse_limits(config.RATE_LIMIT_SEARCH),
}

_LABELS = {"analyze": "analysis", "chat": "chat", "search": "search"}

limiter = RateLimiter()


def client_key(request: Request) -> str:
    """
    Client identity for rate limiting.

    By default the socket peer address. Behind N trusted reverse proxies set
    RATE_LIMIT_PROXY_HOPS=N: the client is then the N-th address from the *right* of
    X-Forwarded-For (left-most entries are client-controlled and could be spoofed
    to dodge limits).
    """
    hops = config.RATE_LIMIT_PROXY_HOPS
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-hops] if len(parts) >= hops else parts[0]
    return request.client.host if request.client else "unknown"


def check(rule: str, request: Request) -> Optional[int]:
    """Returns None if allowed, else whole seconds to wait. Records the request when allowed."""
    if not config.RATE_LIMIT_ENABLED:
        return None
    retry = limiter.hit(rule, client_key(request), RULES.get(rule, []))
    return None if retry is None else max(1, math.ceil(retry))


def too_many_message(rule: str, retry_after: int) -> str:
    return f"Too many {_LABELS.get(rule, rule)} requests. Please try again in {retry_after}s."


def rate_limit(rule: str):
    """FastAPI dependency: `dependencies=[rate_limit("chat")]`."""
    def _dependency(request: Request) -> None:
        retry_after = check(rule, request)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail=too_many_message(rule, retry_after),
                headers={"Retry-After": str(retry_after)},
            )
    return Depends(_dependency)
