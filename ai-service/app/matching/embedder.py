"""Sentence Transformers wrapper: turns text into 384 numbers so similar meanings are close together.

The model is loaded once, on first use (it takes a few seconds), and runs on the CPU.
Vectors are scaled to length 1, so a plain dot product between two of them IS the cosine similarity
(1.0 = same meaning, 0 = unrelated).
"""
import os
import threading

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"   # 22.7M parameters, 384 numbers per text
MAX_CACHE = 5000

_lock = threading.Lock()
_model = None
_cache: dict[str, np.ndarray] = {}


class EmbedderUnavailable(Exception):
    """Sentence Transformers could not be loaded (not installed, blocked, or no model available)."""


def model_name() -> str:
    return os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL).strip()


def _load():
    global _model
    with _lock:
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer
                # trust_remote_code stays False: we never run code that comes with a downloaded model
                _model = SentenceTransformer(model_name(), device="cpu")
            except Exception as exc:  # import problems, blocked DLLs, download problems
                raise EmbedderUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    return _model


def warm_up() -> None:
    """Load the model now (in the background at start-up) so the first real request is not slow. Never raises."""
    try:
        embed(["warm up"])
    except Exception:
        pass  # a problem here is reported properly, with a clear message, when a matching request needs the model


def embed(texts: list[str]) -> np.ndarray:
    """One unit-length vector per text. Repeated texts are remembered, so they are free."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    missing = [t for t in dict.fromkeys(texts) if t not in _cache]
    if missing:
        vectors = _load().encode(missing, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        if len(_cache) + len(missing) > MAX_CACHE:
            _cache.clear()
        for text, vector in zip(missing, vectors):
            _cache[text] = np.asarray(vector, dtype=np.float32)
    return np.stack([_cache[t] for t in texts])
