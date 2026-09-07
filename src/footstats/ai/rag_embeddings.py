"""RAG Embeddings: sentence-transformers + PostgreSQL BYTEA storage for semantic lesson retrieval.

NIE JEST WLACZONE NA PRODUKCJI — i to jest decyzja, nie awaria.

`sentence-transformers` swiadomie NIE trafia do obrazow (`requirements-jobs.lock`
go nie ma): ciagnie torch, czyli gigabajty warstwy i zimny start Cloud Run, dla
~150 krotkich lekcji. Decyzja z 2026-08-09, uzasadnienie stoi rowniez przy
`except ImportError` w `ai/rag.retrieve_relevant_lessons`. Skutkiem jest linia
w logu kazdego przebiegu:

    [RAG] sentence-transformers not installed. Install via: pip install sentence-transformers

`retrieve_relevant_lessons` oddaje wtedy pusta liste, a `ai/analyzer.py` schodzi
na `pobierz_ostatnie_wnioski(3)` — trzy najnowsze lekcje chronologicznie. Petla
zwrotna DZIALA, brakuje jej wylacznie wyszukiwania semantycznego.

STAN TABELI (pomiar 2026-09-07): `ai_feedback` ma 156 wierszy, a
`ai_feedback_embeddings` — 7. Te siedem to pozostalosc po recznym
`backfill_embeddings` sprzed decyzji; nic w potoku ich nie dopisuje, bo
`backfill_embeddings` wola sie wylacznie z `__main__` tego pliku.

GDYBY WRACAC DO TEMATU. Zastrzezenie dotyczylo torcha, nie samego pomyslu, a
`scikit-learn` JEST juz w `requirements-jobs.lock` (1.9.0) — TF-IDF liczony
w pamieci nad 156 lekcjami kosztowalby zero megabajtow obrazu. Wtedy jednak
NIE wolno tych wektorow zapisywac do tabeli: slownik TF-IDF zalezy od korpusu,
wiec wektor sprzed dolozenia lekcji przestaje byc porownywalny z nowym.

Wieksze ograniczenie lezy gdzie indziej i trzeba je naprawic PIERWSZE:
`analyzer.py` buduje zapytanie jako `f"Liga: {ligi} | Markety: {markety}"` —
same nazwy lig i etykiety kuponow, bez druzyn i bez typu. Lekcje to eseje
o konkretnych meczach, wiec przy takim zapytaniu kazde wyszukiwanie, semantyczne
czy nie, dopasowuje glownie nazwe ligi. Sam embedder tego nie naprawi.
"""

import logging
import numpy as np
from typing import Optional
from pathlib import Path

from footstats.utils.db import connect as _connect

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = None  # Lazy-loaded singleton


def _get_embedding_model():
    """Lazy-load sentence-transformers model (cold start ~2s on CPU)."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _EMBEDDING_MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("[RAG] Embedding model loaded (multilingual MiniLM)")
        except ImportError:
            logger.error("[RAG] sentence-transformers not installed. Install via: pip install sentence-transformers")
            raise
    return _EMBEDDING_MODEL


def ensure_schema():
    """Create ai_feedback_embeddings table if not exists."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_feedback_embeddings (
                feedback_id INTEGER PRIMARY KEY REFERENCES ai_feedback(id) ON DELETE CASCADE,
                embedding   BYTEA NOT NULL,
                model_name  TEXT NOT NULL,
                dim         INTEGER NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    logger.info("[RAG] Embeddings table schema ensured")


class EmbeddingStore:
    """Encapsulates embedding generation, storage, and retrieval."""

    def __init__(self, db_path: Optional[Path] = None, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.db_path = db_path  # kept for API compat, unused (shared PG connection used)
        self.model_name = model_name
        self.model = _get_embedding_model()
        # Use get_embedding_dimension() for newer versions; fallback to old name for compat
        self.dim = getattr(self.model, 'get_embedding_dimension', self.model.get_sentence_embedding_dimension)()

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding vector for text. Returns float32 ndarray."""
        if not text or not text.strip():
            return np.zeros(self.dim, dtype=np.float32)
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)

    def upsert(self, feedback_id: int, text: str) -> bool:
        """Embed text and upsert into ai_feedback_embeddings. Returns success flag."""
        try:
            embedding = self.embed_text(text)
            blob = embedding.tobytes()
            with _connect() as conn:
                conn.execute(
                    "INSERT INTO ai_feedback_embeddings (feedback_id, embedding, model_name, dim)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (feedback_id) DO UPDATE SET"
                    " embedding=EXCLUDED.embedding, model_name=EXCLUDED.model_name, dim=EXCLUDED.dim",
                    (feedback_id, blob, self.model_name, self.dim),
                )
            return True
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"[RAG] Failed to upsert embedding for feedback_id={feedback_id}: {e}")
            return False

    def get_all(self) -> tuple[list[int], Optional[np.ndarray]]:
        """
        Fetch all embeddings. Returns (list of feedback_ids, matrix of embeddings).
        Matrix shape: (num_embeddings, dim). Returns ([], None) if table empty.
        """
        try:
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT feedback_id, embedding FROM ai_feedback_embeddings ORDER BY feedback_id"
                ).fetchall()
            if not rows:
                return [], None
            ids = [row["feedback_id"] for row in rows]
            embeddings = np.array([
                np.frombuffer(bytes(row["embedding"]), dtype=np.float32) for row in rows
            ])
            return ids, embeddings
        except (OSError, ValueError, TypeError) as e:
            logger.error(f"[RAG] Failed to fetch all embeddings: {e}")
            return [], None

    def cosine_top_k(self, query_vec: np.ndarray, k: int = 5, min_score: float = 0.35) -> list[tuple[int, float]]:
        """
        Semantic search: return top-k (feedback_id, cosine_score) by similarity to query_vec.
        Filters by min_score threshold. Returns empty list if not enough matches.
        """
        feedback_ids, embeddings = self.get_all()
        if embeddings is None or len(embeddings) == 0:
            return []

        # Normalize vectors for cosine similarity
        query_normalized = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        embeddings_normalized = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)

        # Compute cosine similarities
        similarities = embeddings_normalized @ query_normalized

        # Filter by min_score, sort descending, take top-k
        results = [(feedback_ids[i], float(similarities[i])) for i in range(len(feedback_ids)) if similarities[i] >= min_score]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]


def backfill_embeddings(db_path: Optional[Path] = None, verbose: bool = False):
    """
    One-time backfill: embed all ai_feedback rows and upsert into ai_feedback_embeddings.
    Idempotent — safe to re-run for model swaps. Requires ai_feedback table populated.
    """
    ensure_schema()
    store = EmbeddingStore(db_path)

    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, reason_for_failure FROM ai_feedback WHERE reason_for_failure IS NOT NULL ORDER BY id"
            ).fetchall()

        if not rows:
            logger.info("[RAG] No ai_feedback rows to backfill")
            return

        count = 0
        for feedback_id, reason_text in rows:
            if store.upsert(feedback_id, reason_text):
                count += 1
                if verbose and count % 10 == 0:
                    logger.info(f"[RAG] Backfilled {count}/{len(rows)} embeddings")

        logger.info(f"[RAG] Backfill complete: {count}/{len(rows)} embeddings stored")
    except (OSError, ValueError, TypeError) as e:
        logger.error(f"[RAG] Backfill failed: {e}")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

    if "--reindex" in sys.argv:
        db_path_arg = None
        if "--db" in sys.argv:
            idx = sys.argv.index("--db")
            if idx + 1 < len(sys.argv):
                db_path_arg = Path(sys.argv[idx + 1])
        backfill_embeddings(db_path_arg, verbose=True)
    else:
        print("Usage: python -m footstats.ai.rag_embeddings --reindex [--db /path/to/db]")
