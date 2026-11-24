"""Central runtime configuration, read from environment variables."""
import os


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


SERVER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Pipeline -------------------------------------------------------------
ANALYSIS_WORKERS = _int("ANALYSIS_WORKERS", 8)
SCAN_BATCH_SIZE = _int("SCAN_BATCH_SIZE", 64)          # files per file_complexity_batch event
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None        # optional: raises GitHub API rate limit

# --- Rate limiting (per client, in-memory) --------------------------------
# Format: "N/unit" joined with ";" (unit: s|min|minute|h|hour|d|day, e.g. "5/10min"). "off" disables a rule.
RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_ANALYZE = os.getenv("RATE_LIMIT_ANALYZE", "3/minute;20/hour")   # new analyses only (reconnects are free)
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "6/minute;100/day")         # Groq free tier: 1000 requests/day shared
RATE_LIMIT_SEARCH = os.getenv("RATE_LIMIT_SEARCH", "60/minute")
RATE_LIMIT_PROXY_HOPS = _int("RATE_LIMIT_PROXY_HOPS", 0)   # trusted reverse proxies in front of the server
MAX_CONCURRENT_ANALYSES = _int("MAX_CONCURRENT_ANALYSES", 3)  # global; each clones + embeds on the CPU

# --- Sessions -------------------------------------------------------------
SESSION_TTL_SECONDS = _int("SESSION_TTL_SECONDS", 60 * 60)  # keep finished sessions for 1h
MAX_SESSIONS = _int("MAX_SESSIONS", 20)

# --- Vector search --------------------------------------------------------
VECTOR_SEARCH_ENABLED = _bool("VECTOR_SEARCH_ENABLED", True)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_CACHE_DIR = os.getenv("EMBEDDING_CACHE_DIR", os.path.join(SERVER_DIR, ".cache", "fastembed"))
EMBEDDING_BATCH_SIZE = _int("EMBEDDING_BATCH_SIZE", 4)       # small batches are fastest on CPU
EMBEDDING_PRELOAD = _bool("EMBEDDING_PRELOAD", True)     # warm the model at server start
MAX_INDEX_CHUNKS = _int("MAX_INDEX_CHUNKS", 10000)       # bounds indexing time on huge repos
MAX_CONCURRENT_INDEX_BUILDS = _int("MAX_CONCURRENT_INDEX_BUILDS", 1)
# Tests, generated and vendored files are left out of the search index (unless that leaves nothing).
INDEX_SKIP_NON_PRIMARY = _bool("INDEX_SKIP_NON_PRIMARY", True)

# --- Analysis cache (finished results + embeddings, keyed by owner/repo@commit-sha) ---
ANALYSIS_CACHE_ENABLED = _bool("ANALYSIS_CACHE_ENABLED", True)
ANALYSIS_CACHE_DIR = os.getenv("ANALYSIS_CACHE_DIR", os.path.join(SERVER_DIR, ".cache", "analysis"))
ANALYSIS_CACHE_MAX_MB = _int("ANALYSIS_CACHE_MAX_MB", 2048)   # analyses + embeddings; LRU eviction
LS_REMOTE_TIMEOUT_SECONDS = _int("LS_REMOTE_TIMEOUT_SECONDS", 15)  # commit lookup before a cache check

# --- Static analysis --------------------------------------------------------
# Files above this size, or minified (very long average line), are counted but not parsed:
# the regex fallback is slow on them and their "functions" are noise.
MAX_ANALYZE_BYTES = _int("MAX_ANALYZE_BYTES", 1_500_000)
MAX_AVG_LINE_LENGTH = _int("MAX_AVG_LINE_LENGTH", 250)

# --- LLM (Groq) -----------------------------------------------------------
# Free tier limit is ~8k tokens/minute *including* the answer, so keep prompts tight.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")  # low | medium | high (gpt-oss models only)
CHAT_CONTEXT_CHARS = _int("CHAT_CONTEXT_CHARS", 14000)   # repo overview + retrieved code
CHAT_MAX_TOKENS = _int("CHAT_MAX_TOKENS", 1536)
CHAT_HISTORY_MESSAGES = _int("CHAT_HISTORY_MESSAGES", 6)
