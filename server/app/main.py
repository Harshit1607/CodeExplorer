from dotenv import load_dotenv
load_dotenv()  # Load .env file for local development

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.analyze import router as analyze_router
from app.api.structure import router as structure_router
from app.api.chat import router as chat_router
from app.api.search import router as search_router
from app.core import config
from app.services.vector_index import Embedder


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load (and on first run, download) the embedding model in the background so
    # the first analysis doesn't pay the startup cost.
    if config.EMBEDDING_PRELOAD:
        Embedder.preload_async()
    yield


app = FastAPI(title="CodeExplorer", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "vector_search": Embedder.is_enabled()}

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, # Temporarily disable for maximum compatibility
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],  # lets the browser read 429 back-off times
)

app.include_router(analyze_router, prefix="/api")
app.include_router(structure_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(search_router, prefix="/api")
