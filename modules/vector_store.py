"""
modules/vector_store.py

Vector Store:
- Generates Gemini text-embedding-004 embeddings for scheme text
- Builds and persists a FAISS index
- Supports semantic search by natural language query
"""

import os
import json
import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

VECTOR_STORE_PATH = Path("vectorstore")
VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)

INDEX_PATH = VECTOR_STORE_PATH / "faiss_index.pkl"
META_PATH = VECTOR_STORE_PATH / "scheme_metadata.json"


def _get_embedding_model():
    """Lazy-load the Gemini embedding model."""
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GOOGLE_API_KEY not set")
        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=api_key,
        )
    except Exception as exc:
        logger.warning(f"Gemini embeddings unavailable: {exc}. Using TF-IDF fallback.")
        return None


class TFIDFFallbackEmbedder:
    """
    Lightweight TF-IDF based embedder when Gemini API is not available.
    Produces 512-dimensional vectors suitable for FAISS cosine search.
    """

    def __init__(self):
        self.vectorizer = None
        self.vocab: Dict[str, int] = {}
        self.idf: np.ndarray = np.array([])

    def fit(self, texts: List[str]):
        """Build vocabulary and IDF from corpus."""
        from collections import Counter
        import math

        # Tokenize
        tokenized = [self._tokenize(t) for t in texts]

        # Build vocab
        all_tokens = [tok for doc in tokenized for tok in doc]
        freq = Counter(all_tokens)
        vocab_list = [tok for tok, _ in freq.most_common(512)]
        self.vocab = {tok: i for i, tok in enumerate(vocab_list[:512])}

        # Compute IDF
        n = len(texts)
        df = np.zeros(len(self.vocab))
        for doc in tokenized:
            for tok in set(doc):
                if tok in self.vocab:
                    df[self.vocab[tok]] += 1
        self.idf = np.log((n + 1) / (df + 1)) + 1

    def embed(self, text: str) -> np.ndarray:
        """Produce a TF-IDF vector for a single text."""
        if not self.vocab:
            logger.warning("TF-IDF vocabulary is not fitted; returning a zero vector.")
            return np.zeros(512, dtype=np.float32)
        tokens = self._tokenize(text)
        vec = np.zeros(512, dtype=np.float32)
        for tok in tokens:
            if tok in self.vocab:
                vec[self.vocab[tok]] += 1
        # TF-IDF weighting
        if self.idf.size > 0:
            vec *= self.idf[:512]
        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_many(self, texts: List[str]) -> np.ndarray:
        return np.array([self.embed(t) for t in texts], dtype=np.float32)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        import re
        return re.findall(r"[a-z]+", text.lower())


class VectorStore:
    """
    FAISS-backed vector store for semantic scheme search.
    Supports Gemini embeddings with TF-IDF fallback.
    """

    def __init__(self):
        self.index = None
        self.scheme_metadata: List[Dict[str, Any]] = []
        self.embedding_model = None
        self.fallback: Optional[TFIDFFallbackEmbedder] = None
        self.dim = 768  # Gemini text-embedding-004 dimensionality

    # ── Text preparation ──────────────────────────────────────────────────────

    @staticmethod
    def _build_text(scheme: Dict[str, Any]) -> str:
        """Combine scheme fields into a searchable document."""
        parts = [
            scheme.get("scheme_name", ""),
            scheme.get("description", ""),
            scheme.get("benefits", ""),
            scheme.get("eligibility_text", ""),
        ]
        return " | ".join(p for p in parts if p)

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        """Embed a list of texts, using Gemini or TF-IDF fallback."""
        if self.embedding_model:
            try:
                vectors = self.embedding_model.embed_documents(texts)
                return np.array(vectors, dtype=np.float32)
            except Exception as exc:
                logger.error(f"Gemini embedding failed: {exc}. Using fallback.")

        # Fallback
        if not self.fallback:
            self.fallback = TFIDFFallbackEmbedder()
            self.fallback.fit(texts)
        return self.fallback.embed_many(texts)

    def _embed_query(self, query: str) -> np.ndarray:
        """Embed a single search query."""
        if self.embedding_model:
            try:
                vector = self.embedding_model.embed_query(query)
                return np.array(vector, dtype=np.float32).reshape(1, -1)
            except Exception as exc:
                logger.error(f"Gemini query embedding failed: {exc}")

        if self.fallback:
            return self.fallback.embed(query).reshape(1, -1)

        logger.error("No compatible query embedder is available.")
        return np.zeros((1, self.dim), dtype=np.float32)

    # ── Build index ───────────────────────────────────────────────────────────

    def build(self, schemes: List[Dict[str, Any]]):
        """
        Build FAISS index from a list of scheme dicts.
        Saves both the index and metadata to disk.
        """
        import faiss

        if not schemes:
            logger.warning("No schemes provided to vector store builder")
            return

        logger.info(f"Building vector store for {len(schemes)} schemes…")

        # Try Gemini embeddings
        self.embedding_model = _get_embedding_model()

        # Build texts
        texts = [self._build_text(s) for s in schemes]

        # Embed
        vectors = self._embed_texts(texts)
        self.dim = vectors.shape[1]

        # Build FAISS flat L2 index
        self.index = faiss.IndexFlatL2(self.dim)
        self.index.add(vectors)

        # Store metadata (lightweight — only what we need for retrieval)
        self.scheme_metadata = [
            {
                "scheme_id": s.get("scheme_id"),
                "scheme_name": s.get("scheme_name", ""),
                "description": s.get("description", ""),
                "benefits": s.get("benefits", ""),
                "source_url": s.get("source_url", ""),
                "application_link": s.get("application_link", ""),
            }
            for s in schemes
        ]

        self._save()
        logger.info(f"Vector store built. Index size: {self.index.ntotal} vectors ({self.dim}D)")

    # ── Persist ───────────────────────────────────────────────────────────────

    def _save(self):
        import faiss

        if self.index is None:
            return

        # Save FAISS index via pickle (simple approach for portability)
        with open(INDEX_PATH, "wb") as f:
            pickle.dump({
                "index_bytes": faiss.serialize_index(self.index),
                "dim": self.dim,
                "fallback": self.fallback,
            }, f)

        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(self.scheme_metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Vector store saved → {INDEX_PATH}")

    def load(self) -> bool:
        """Load FAISS index from disk. Returns True on success."""
        import faiss

        if not INDEX_PATH.exists() or not META_PATH.exists():
            logger.warning("No saved vector store found. Build it first.")
            return False

        try:
            with open(INDEX_PATH, "rb") as f:
                data = pickle.load(f)

            self.index = faiss.deserialize_index(data["index_bytes"])
            self.dim = data["dim"]
            self.fallback = data.get("fallback")
            if self.fallback is not None and not self.fallback.vocab:
                logger.warning(
                    "Saved TF-IDF embedder has an empty vocabulary; "
                    "the vector store must be rebuilt."
                )
                self.index = None
                self.fallback = None
                return False

            with open(META_PATH, encoding="utf-8") as f:
                self.scheme_metadata = json.load(f)

            # A saved fallback means the index was built with TF-IDF and queries
            # must use that same vector space, even if Gemini is available now.
            self.embedding_model = None if self.fallback else _get_embedding_model()
            logger.info(f"Vector store loaded: {self.index.ntotal} vectors")
            return True
        except Exception as exc:
            logger.error(f"Failed to load vector store: {exc}")
            return False

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search for schemes matching a natural language query.

        Returns top-k most similar scheme metadata dicts with similarity scores.
        """
        if self.index is None:
            loaded = self.load()
            if not loaded:
                logger.error("Vector store not available")
                return []

        query_vec = self._embed_query(query)
        if query_vec.shape[1] != self.dim:
            logger.error(
                "Query vector dimension %s does not match index dimension %s",
                query_vec.shape[1],
                self.dim,
            )
            return []
        if not np.any(query_vec):
            logger.warning("Query produced no known terms; returning no results.")
            return []

        # FAISS search
        distances, indices = self.index.search(query_vec, top_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.scheme_metadata):
                continue
            meta = self.scheme_metadata[idx].copy()
            # Convert L2 distance to similarity score (0-1 range)
            similarity = max(0.0, 1.0 - float(dist) / 10.0)
            meta["similarity_score"] = round(similarity, 3)
            results.append(meta)

        return results

    def index_exists(self) -> bool:
        return INDEX_PATH.exists() and META_PATH.exists()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from database.db_manager import DBManager

    db = DBManager()
    schemes = db.get_all_schemes()

    if not schemes:
        print("❌ No schemes in DB. Run update_schemes.py first.")
        sys.exit(1)

    vs = VectorStore()
    vs.build(schemes)

    print("\n🔍 Test search: 'scholarship for SC students'")
    results = vs.search("scholarship for SC students", top_k=3)
    for r in results:
        print(f"  [{r['similarity_score']:.3f}] {r['scheme_name']}")
