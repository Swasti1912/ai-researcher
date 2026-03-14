"""
Knowledge Base (RAG).

In-memory document store with TF-IDF–weighted keyword retrieval.
Swap internals for ChromaDB / FAISS + embeddings in production.

Usage::

    from app.knowledge_base import get_kb
    kb = get_kb()
    doc_id = kb.ingest("paper text…", filename="paper.pdf")
    chunks = kb.search("attention mechanism", top_k=5)
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

from app.utils.exceptions import KnowledgeBaseError
from app.utils.logger import get_logger

_log = get_logger(__name__)


class KnowledgeBase:
    """In-memory vector-free retrieval store."""

    def __init__(self) -> None:
        self._docs: Dict[str, str] = {}
        self._chunks: List[Tuple[str, str, str]] = []   # (chunk_id, doc_id, text)
        self._idf: Dict[str, float] = {}

    # ── Ingestion ────────────────────────────────────────────────────

    def ingest(self, text: str, *, filename: Optional[str] = None,
               chunk_size: int = 800, overlap: int = 200) -> str:
        """
        Chunk and index a document.

        Args:
            text:       Full document text.
            filename:   Human label.
            chunk_size: Characters per chunk.
            overlap:    Overlap between chunks.

        Returns:
            Unique document ID.

        Raises:
            KnowledgeBaseError: On empty text or internal failure.
        """
        if not text or not text.strip():
            raise KnowledgeBaseError("Cannot ingest empty text")
        try:
            did = hashlib.sha256(text[:512].encode()).hexdigest()[:16]
            self._docs[did] = text
            chunks = self._split(text, chunk_size, overlap)
            for i, c in enumerate(chunks):
                self._chunks.append((f"{did}_{i}", did, c))
            self._rebuild_idf()
            _log.info("Ingested", extra={"doc_id": did, "filename": filename, "chunks": len(chunks)})
            return did
        except KnowledgeBaseError:
            raise
        except Exception as e:
            raise KnowledgeBaseError("Ingest failed", str(e)) from e

    # ── Retrieval ────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> List[str]:
        """Return *top_k* chunks ranked by TF-IDF overlap with *query*."""
        if not self._chunks:
            return []
        qtoks = self._tok(query)
        scored = [(self._score(qtoks, c), c) for _, _, c in self._chunks]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:top_k]]

    # ── Internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _split(text: str, size: int, overlap: int) -> List[str]:
        out, start = [], 0
        while start < len(text):
            out.append(text[start:start + size])
            start += size - overlap
        return out

    @staticmethod
    def _tok(text: str) -> List[str]:
        return [w.lower().strip(".,;:!?\"'()[]{}") for w in text.split() if len(w) > 2]

    def _rebuild_idf(self) -> None:
        n = max(len(self._chunks), 1)
        df: Counter = Counter()
        for _, _, c in self._chunks:
            for t in set(self._tok(c)):
                df[t] += 1
        self._idf = {t: math.log(n / (1 + v)) for t, v in df.items()}

    def _score(self, qtoks: List[str], chunk: str) -> float:
        ctf: Counter = Counter(self._tok(chunk))
        total = max(sum(ctf.values()), 1)
        return sum((ctf[q] / total) * self._idf.get(q, 1.0) for q in qtoks if q in ctf)

    # ── Properties ───────────────────────────────────────────────────

    @property
    def doc_count(self) -> int:
        return len(self._docs)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def clear(self) -> None:
        self._docs.clear(); self._chunks.clear(); self._idf.clear()


_inst: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    """Global singleton."""
    global _inst
    if _inst is None:
        _inst = KnowledgeBase()
    return _inst
