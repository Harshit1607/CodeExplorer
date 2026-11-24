"""Central runtime configuration, read from environment variables."""
import os
import tempfile
from typing import List


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> List[str]:
    return [v.strip().rstrip("/") for v in os.getenv(name, "").split(",") if v.strip()]


SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Pipeline -------------------------------------------------------------
ANALYSIS_WORKERS = _int("ANALYSIS_WORKERS", 8)
SCAN_BATCH_SIZE = _int("SCAN_BATCH_SIZE", 64)          # files per file_complexity_batch event
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None        # optional: raises GitHub API rate limit
# Where repositories are cloned. Leftover clone folders in it are deleted at startup.
CLONE_DIR = os.getenv("CLONE_DIR") or os.path.join(tempfile.gettempdir(), "codeexplorer")
CLONE_TIMEOUT_SECONDS = _int("CLONE_TIMEOUT_SECONDS", 300)   # 0 disables
MAX_REPO_SIZE_MB = _int("MAX_REPO_SIZE_MB", 1500)  # GitHub-reported size (whole history); 0 disables
# A running analysis nobody is watching is cancelled after this many seconds.
ANALYSIS_ABANDON_GRACE_SECONDS = _int("ANALYSIS_ABANDON_GRACE_SECONDS", 10)

# --- HTTP -----------------------------------------------------------------
# Comma-separated browser origins allowed to call the API, or "*" for any.
# Empty (default): http(s)://localhost and 127.0.0.1 on any port (local development).
CORS_ALLOWED_ORIGINS = _list("CORS_ALLOWED_ORIGINS")
MAX_REQUEST_BODY_MB = _int("MAX_REQUEST_BODY_MB", 8)        # 0 disables

# --- Rate limiting (per client, in-memory) --------------------------------
# Format: "N/unit" joined with ";" (unit: s|min|minute|h|hour|d|day, e.g. "5/10min"). "off" disables a rule.
RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "3/minute;20/hour")   # new analyses only (reconnects are free)
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "6/minute;100/day")         # Groq free tier: 1000 requests/day shared
RATE_LIMIT_SEARCH = os.getenv("RATE_LIMIT_SEARCH", "60/minute")
RATE_LIMIT_PROXY_HOPS = _int("RATE_LIMIT_PROXY_HOPS", 0)   # trusted reverse proxies in front of the server
MAX_CONCURRENT_ANALYSES = _int("MAX_CONCURRENT_ANALYSES", 3)  # global; each clones + embeds on the CPU
MAX_ANALYSES_PER_CLIENT = _int("MAX_ANALYSES_PER_CLIENT", 1)  # running analyses per client; 0 disables

# --- Sessions -------------------------------------------------------------
SESSION_TTL_SECONDS = _int("SESSION_TTL_SECONDS", 60 * 60)  # keep finished sessions for 1h
MAX_SESSIONS = _int("MAX_SESSIONS", 20)

# --- Vector search --------------------------------------------------------
VECTOR_SEARCH_ENABLED = _bool("VECTOR_SEARCH_ENABLED", True)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_CACHE_DIR = os.getenv("EMBEDDING_CACHE_DIR", os.path.join(SERVER_DIR, ".cache", "fastembed"))
EMBEDDING_BATCH_SIZE = _int("EMBEDDING_BATCH_SIZE", 4)       # small batches are fastest on CPU
EMBEDDING_PRELOAD = _bool("EMBEDDING_PRELOAD", True)     # warm the model at server start
MAX_INDEX_CHUNKS = _int("MAX_INDEX_CHUNKS", 6000)        # bounds indexing time on huge repos
MAX_CONCURRENT_INDEX_BUILDS = _int("MAX_CONCURRENT_INDEX_BUILDS", 1)
# Docs/config files (README, docs/, Dockerfile, compose, CI, .env.example, Makefile) indexed
# next to the code; capped so they never take more than a small slice of MAX_INDEX_CHUNKS.
DOC_INDEX_MAX_FILES = _int("DOC_INDEX_MAX_FILES", 150)
DOC_INDEX_MAX_CHUNKS = _int("DOC_INDEX_MAX_CHUNKS", 300)

# --- LLM (Groq) -----------------------------------------------------------
# Free tier limit is ~8k tokens/minute *including* the answer, so keep prompts tight.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")  # low | medium | high (gpt-oss models only)
CHAT_CONTEXT_CHARS = _int("CHAT_CONTEXT_CHARS", 14000)   # repo overview + retrieved code
CHAT_MAX_TOKENS = _int("CHAT_MAX_TOKENS", 1536)
CHAT_HISTORY_MESSAGES = _int("CHAT_HISTORY_MESSAGES", 6)
# AI architecture report: characters of retrieved code excerpts in the prompt, and how long the
# report waits for the search index to finish before using whatever part is already searchable.
AI_REPORT_CODE_CHARS = _int("AI_REPORT_CODE_CHARS", 8000)
AI_REPORT_INDEX_WAIT_SECONDS = _int("AI_REPORT_INDEX_WAIT_SECONDS", 60)
