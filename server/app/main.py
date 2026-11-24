from dotenv import load_dotenv
load_dotenv()  # Load .env file for local development

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.analyze import router as analyze_router
from app.api.chat import router as chat_router
from app.api.search import router as search_router
from app.core import config
from app.core.body_limit import BodySizeLimitMiddleware
from app.services.streaming_pipeline import clean_clone_dir
from app.services.vector_index import Embedder


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Clones left behind by a previous run (crash, restart, --reload) are orphans now.
    clean_clone_dir()
    # Load (and on first run, download) the embedding model in the background so
    # the first analysis doesn't pay the startup cost.
    if config.EMBEDDING_PRELOAD:
        Embedder.preload_async()
    yield


app = FastAPI(title="CodeExplorer", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "vector_search": Embedder.is_enabled()}

app.add_middleware(BodySizeLimitMiddleware, max_bytes=config.MAX_REQUEST_BODY_MB * 1024 * 1024)

# CORS (added last so it is outermost and also covers 413 rejections). Only the configured
# origins may call the API from a browser; by default that is local development only.
_LOCAL_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_origin_regex=None if config.CORS_ALLOWED_ORIGINS else _LOCAL_ORIGIN_RE,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],  # lets the browser read 429 back-off times
)

app.include_router(analyze_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")
