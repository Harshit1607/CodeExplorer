"""
Local embeddings + an in-memory vector index (one per analysis session).

- Embeddings come from fastembed (ONNX, no torch, no API key). The model is loaded
  lazily once per process and shared by every session.
- The index is a normalised float32 numpy matrix; search is brute-force cosine
  similarity, which takes a few milliseconds for the ~thousands of chunks a repo produces.
"""
import os
import threading
import time
from typing import Callable, List, Optional, Tuple

from app.core import config
from app.services.code_chunker import CodeChunk

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class EmbeddingUnavailable(RuntimeError):
    pass


class Embedder:
    """Process-wide, lazily-loaded embedding model."""

    _model = None
    _load_lock = threading.Lock()
    _load_error: Optional[str] = None
    _build_semaphore = threading.BoundedSemaphore(max(1, config.MAX_CONCURRENT_INDEX_BUILDS))

    @classmethod
    def is_enabled(cls) -> bool:
        return config.VECTOR_SEARCH_ENABLED and np is not None

    @classmethod
    def get_model(cls):
        if not cls.is_enabled():
            raise EmbeddingUnavailable("Vector search is disabled or numpy is not installed")
        if cls._model is not None:
            return cls._model
        with cls._load_lock:
            if cls._model is not None:
                return cls._model
            if cls._load_error:
                raise EmbeddingUnavailable(cls._load_error)
            try:
                from fastembed import TextEmbedding
                os.makedirs(config.EMBEDDING_CACHE_DIR, exist_ok=True)
                t = time.time()
                cls._model = TextEmbedding(model_name=config.EMBEDDING_MODEL, cache_dir=config.EMBEDDING_CACHE_DIR)
                print(f"[embeddings] loaded {config.EMBEDDING_MODEL} in {time.time() - t:.1f}s")
            except Exception as e:  # ImportError, download failure, ...
                cls._load_error = f"Embedding model unavailable: {e}"
                print(f"[embeddings] {cls._load_error}")
                raise EmbeddingUnavailable(cls._load_error)
        return cls._model

    @classmethod
    def preload_async(cls):
        if cls.is_enabled():
            threading.Thread(target=lambda: cls._safe_preload(), daemon=True).start()

    @classmethod
    def _safe_preload(cls):
        try:
            cls.get_model()
        except EmbeddingUnavailable:
            pass

    @classmethod
    def embed_documents(cls, texts: List[str]) -> "np.ndarray":
        model = cls.get_model()
        # Sort by length so each batch pads to a similar size, then restore order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vecs = list(model.passage_embed([texts[i] for i in order], batch_size=config.EMBEDDING_BATCH_SIZE))
        out = np.empty((len(texts), len(vecs[0]) if vecs else 0), dtype=np.float32)
        for pos, i in enumerate(order):
            out[i] = vecs[pos]
        return _normalize(out)

    @classmethod
    def embed_query(cls, text: str) -> "np.ndarray":
        model = cls.get_model()
        vec = np.asarray(list(model.query_embed([text])), dtype=np.float32)[0]
        return _normalize(vec[None, :])[0]


def _normalize(m: "np.ndarray") -> "np.ndarray":
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


_LOW_PRIORITY_PARTS = ("test", "spec", "__tests__", "__mocks__", "fixture", "example",
                       "sample", "demo", "docs", "benchmark", "migrations")


def _priority(chunk: CodeChunk) -> int:
    """Lower is indexed first. Tests/examples/docs go last (they're dropped first if capped)."""
    path = chunk.file.lower()
    return 1 if any(part in path for part in _LOW_PRIORITY_PARTS) else 0


class VectorIndex:
    """Embeddings for one repository. Searchable incrementally while it is being built."""

    PUBLISH_EVERY = 64  # chunks embedded between snapshots made visible to search

    def __init__(self):
        self.status = "pending"   # pending | building | ready | failed | unavailable
        self.error: Optional[str] = None
        # (chunks, matrix) swapped atomically so readers never see mismatched lengths
        self._data: Tuple[List[CodeChunk], Optional["np.ndarray"]] = ([], None)
        self.total_chunks = 0
        self.indexed_chunks = 0
        self.truncated = False
        self.build_seconds = 0.0

    @property
    def searchable(self) -> bool:
        chunks, matrix = self._data
        return matrix is not None and len(chunks) > 0

    # Kept for callers that only care about completeness.
    @property
    def ready(self) -> bool:
        return self.status == "ready" and self.searchable

    def info(self) -> dict:
        return {
            "status": self.status,
            "searchable": self.searchable,
            "error": self.error,
            "total_chunks": self.total_chunks,
            "indexed_chunks": self.indexed_chunks,
            "truncated": self.truncated,
            "model": config.EMBEDDING_MODEL,
            "build_seconds": round(self.build_seconds, 2),
        }

    def build(self, chunks: List[CodeChunk],
              on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Embed `chunks` (blocking; run in a worker thread)."""
        if not Embedder.is_enabled():
            self.status, self.error = "unavailable", "Vector search disabled"
            return

        chunks = sorted(chunks, key=_priority)  # stable: keeps file order within a tier
        if len(chunks) > config.MAX_INDEX_CHUNKS:
            chunks = chunks[:config.MAX_INDEX_CHUNKS]
            self.truncated = True

        self.total_chunks = len(chunks)
        self.status = "building"
        started = time.time()
        try:
            Embedder.get_model()  # surface load errors before waiting on the semaphore
            with Embedder._build_semaphore:
                parts: List["np.ndarray"] = []
                for i in range(0, len(chunks), self.PUBLISH_EVERY):
                    batch = chunks[i:i + self.PUBLISH_EVERY]
                    parts.append(Embedder.embed_documents([c.embedding_text() for c in batch]))
                    done = i + len(batch)
                    self._data = (chunks[:done], np.vstack(parts))
                    self.indexed_chunks = done
                    if on_progress:
                        on_progress(done, self.total_chunks)
            self.status = "ready"
        except EmbeddingUnavailable as e:
            self.status, self.error = "unavailable", str(e)
        except Exception as e:
            self.status, self.error = "failed", str(e)
        finally:
            self.build_seconds = time.time() - started

    def search(self, query: str, k: int = 50, min_score: float = 0.0) -> List[Tuple[CodeChunk, float]]:
        chunks, matrix = self._data
        if matrix is None or not chunks or not query.strip():
            return []
        q = Embedder.embed_query(query)
        sims = matrix @ q
        k = min(k, len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [(chunks[i], float(sims[i])) for i in top if sims[i] >= min_score]
