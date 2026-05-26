"""
pipeline/vector_memory.py  —  Semantic Vector Memory
------------------------------------------------------
Long-term memory layer for the multi-agent pipeline.

Each completed pipeline run is embedded as a KPI-summary vector and stored
in a persistent numpy array store. InsightsAgent queries this store at
inference time to retrieve the most similar historical runs, giving the LLM
concrete trend context instead of averages alone.

Architecture
------------
  Embedding  : Gemini text-embedding-004 (768-dim) via google-genai SDK.
               Falls back to TF-IDF bag-of-words if no API key is available
               (test / offline environments).
  Storage    : numpy .npy (vectors) + JSON (metadata index).
               Zero extra library dependencies beyond numpy (already a dep).
  Retrieval  : Cosine similarity — top-K nearest runs returned.

Why not ChromaDB / Pinecone?
  For a single-node pipeline processing hundreds of calls the overhead of
  a separate vector-DB process adds latency and operational complexity with
  no retrieval-quality benefit. The numpy store is swappable: replace
  VectorMemoryStore._save()/_load()/_search() to point at any vector DB
  without changing the public interface.

Usage
-----
  from pipeline.vector_memory import VECTOR_STORE

  VECTOR_STORE.add_run(run_id="run_001", kpi_text="FCR 72% AHT 4.2 min ...", metadata={...})
  similar = VECTOR_STORE.query("FCR below 60% high escalation", top_k=3)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pipeline.logger import get_logger

log = get_logger(__name__)


# ── Embedding backends ────────────────────────────────────────────────

def _embed_gemini(texts: list[str]) -> np.ndarray:
    """Embed a list of texts using Gemini text-embedding-004 (768-dim)."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise OSError("GEMINI_API_KEY not set — cannot use Gemini embedding backend")

    client = genai.Client(api_key=api_key)
    vectors = []
    for text in texts:
        response = client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        vectors.append(response.embeddings[0].values)
    return np.array(vectors, dtype=np.float32)


def _embed_tfidf(texts: list[str], vocab: dict[str, int] | None = None) -> tuple[np.ndarray, dict[str, int]]:
    """
    Lightweight TF-IDF bag-of-words embedding — offline / test fallback.
    Returns (matrix, vocab) so the same vocab can be reused across calls.
    """
    tokenise = lambda t: re.sub(r"[^a-z0-9%.]", " ", t.lower()).split()  # noqa: E731

    import re

    if vocab is None:
        all_tokens: set[str] = set()
        for text in texts:
            all_tokens.update(tokenise(text))
        vocab = {tok: i for i, tok in enumerate(sorted(all_tokens))}

    dim = len(vocab)
    matrix = np.zeros((len(texts), dim), dtype=np.float32)
    for row, text in enumerate(texts):
        tokens = tokenise(text)
        for tok in tokens:
            if tok in vocab:
                matrix[row, vocab[tok]] += 1.0
        # L2 normalise
        norm = np.linalg.norm(matrix[row])
        if norm > 0:
            matrix[row] /= norm

    return matrix, vocab


def _cosine_similarity(query: np.ndarray, corpus: np.ndarray) -> np.ndarray:
    """Return cosine similarity between a query vector and a corpus matrix."""
    q = query / (np.linalg.norm(query) + 1e-10)
    norms = np.linalg.norm(corpus, axis=1, keepdims=True) + 1e-10
    return (corpus / norms) @ q


# ── Vector store ──────────────────────────────────────────────────────

class VectorMemoryStore:
    """
    Persistent semantic memory store backed by numpy arrays.

    Each record contains:
      run_id   — unique identifier for the pipeline run
      text     — human-readable KPI summary (what was embedded)
      vector   — 768-dim Gemini embedding (or TF-IDF fallback)
      metadata — arbitrary dict (FCR, AHT, timestamp, etc.)
    """

    def __init__(self, store_dir: Path) -> None:
        self._dir      = store_dir
        self._vec_path = store_dir / "vectors.npy"
        self._idx_path = store_dir / "index.json"
        self._vectors: np.ndarray | None = None   # (N, D) float32
        self._index:   list[dict]         = []    # parallel list of metadata dicts
        self._vocab:   dict[str, int]     = {}    # TF-IDF vocab (offline mode)

    # ── Persistence ───────────────────────────────────────────────────

    def load(self) -> VectorMemoryStore:
        """Load vectors and index from disk. Silent no-op if files absent."""
        if self._vec_path.exists() and self._idx_path.exists():
            try:
                self._vectors = np.load(str(self._vec_path))
                with open(self._idx_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self._index = data.get("index", [])
                self._vocab = data.get("vocab", {})
                log.info(
                    "[VectorMemory] Loaded %d run vectors (dim=%d)",
                    len(self._index), self._vectors.shape[1] if self._vectors.ndim > 1 else 0,
                )
            except Exception as exc:
                log.warning("[VectorMemory] Load failed (%s) — starting fresh", exc)
                self._vectors, self._index, self._vocab = None, [], {}
        return self

    def save(self) -> None:
        """Persist vectors and index to disk."""
        if self._vectors is None or len(self._index) == 0:
            return
        self._dir.mkdir(parents=True, exist_ok=True)
        np.save(str(self._vec_path), self._vectors)
        with open(self._idx_path, "w", encoding="utf-8") as fh:
            json.dump({"index": self._index, "vocab": self._vocab}, fh, indent=2)
        log.info("[VectorMemory] Saved %d run vectors → %s", len(self._index), self._dir)

    # ── Write ─────────────────────────────────────────────────────────

    def add_run(self, run_id: str, kpi_text: str, metadata: dict[str, Any]) -> None:
        """
        Embed and store a completed run's KPI summary.
        Called by ExportAgent at the end of each pipeline run.
        """
        if not kpi_text.strip():
            log.warning("[VectorMemory] Empty KPI text for run %s — skipping", run_id)
            return

        # Attempt Gemini embedding; fall back to TF-IDF
        try:
            vec = _embed_gemini([kpi_text])[0]
        except Exception as exc:
            log.debug("[VectorMemory] Gemini embed failed (%s) — using TF-IDF fallback", exc)
            corpus_texts = [r["text"] for r in self._index] + [kpi_text]
            vecs, self._vocab = _embed_tfidf(corpus_texts, self._vocab or None)
            vec = vecs[-1]
            # Re-embed existing corpus to keep vocab consistent
            if len(self._index) > 0:
                existing_texts = [r["text"] for r in self._index]
                existing_vecs, self._vocab = _embed_tfidf(existing_texts + [kpi_text])
                self._vectors = existing_vecs[:-1] if existing_vecs.shape[0] > 1 else None
                vec = existing_vecs[-1]

        vec = vec.astype(np.float32).reshape(1, -1)
        self._vectors = vec if self._vectors is None else np.vstack([self._vectors, vec])

        self._index.append({
            "run_id":    run_id,
            "text":      kpi_text,
            "timestamp": datetime.now(UTC).isoformat(),
            **metadata,
        })
        log.debug("[VectorMemory] Added run %s (total=%d)", run_id, len(self._index))

    # ── Query ─────────────────────────────────────────────────────────

    def query(self, query_text: str, top_k: int = 3) -> list[dict]:
        """
        Return the top-K most similar historical runs to query_text.
        Each result includes the original metadata dict plus a `similarity` score.
        Returns [] if the store is empty.
        """
        if self._vectors is None or len(self._index) == 0:
            return []

        # Embed query with the same backend used for storage
        try:
            q_vec = _embed_gemini([query_text])[0].astype(np.float32)
        except Exception:
            if self._vocab:
                q_vecs, _ = _embed_tfidf([query_text], self._vocab)
                q_vec = q_vecs[0].astype(np.float32)
            else:
                return []

        # Pad / trim query to match stored dimension
        stored_dim = self._vectors.shape[1]
        if q_vec.shape[0] < stored_dim:
            q_vec = np.pad(q_vec, (0, stored_dim - q_vec.shape[0]))
        elif q_vec.shape[0] > stored_dim:
            q_vec = q_vec[:stored_dim]

        scores = _cosine_similarity(q_vec, self._vectors)
        k      = min(top_k, len(self._index))
        top_idx = np.argsort(scores)[::-1][:k]

        return [
            {**self._index[i], "similarity": float(scores[i])}
            for i in top_idx
        ]

    def format_context(self, query_text: str, top_k: int = 3) -> str:
        """
        Return a compact text block of similar runs for LLM prompt injection.
        """
        results = self.query(query_text, top_k=top_k)
        if not results:
            return ""

        lines = [f"Top-{len(results)} similar historical runs (by KPI pattern similarity):"]
        for i, r in enumerate(results, 1):
            ts = r.get("timestamp", "")[:10]
            sim = r.get("similarity", 0)
            text = r.get("text", "")[:200]
            lines.append(f"  {i}. [{ts}] sim={sim:.2f} — {text}")
        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._index)


# ── Module-level singleton ────────────────────────────────────────────

from pipeline.config import VECTOR_MEMORY_PATH  # noqa: E402 — after class definition

VECTOR_STORE = VectorMemoryStore(VECTOR_MEMORY_PATH)
