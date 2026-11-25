"""Which browser origins may call the API (shared by the CORS middleware and the SSE endpoint)."""
import re
from typing import Optional

from app.core import config

# Used when CORS_ALLOWED_ORIGINS is empty: local development only.
LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"


def origin_regex() -> Optional[str]:
    return None if config.CORS_ALLOWED_ORIGINS else LOCAL_ORIGIN_RE


def origin_allowed(origin: str) -> bool:
    """Same rule as Starlette's CORSMiddleware with allow_origins + allow_origin_regex."""
    allowed = config.CORS_ALLOWED_ORIGINS
    if "*" in allowed or origin in allowed:
        return True
    regex = origin_regex()
    return bool(regex and re.fullmatch(regex, origin))
