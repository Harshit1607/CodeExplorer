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

# --- LLM (Groq) -----------------------------------------------------------
# Free tier limit is ~8k tokens/minute *including* the answer, so keep prompts tight.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")  # low | medium | high (gpt-oss models only)
CHAT_CONTEXT_CHARS = _int("CHAT_CONTEXT_CHARS", 14000)   # repo overview + retrieved code
CHAT_MAX_TOKENS = _int("CHAT_MAX_TOKENS", 1536)
CHAT_HISTORY_MESSAGES = _int("CHAT_HISTORY_MESSAGES", 6)
