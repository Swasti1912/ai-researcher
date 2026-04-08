"""
Knowledge Base — Qdrant + sentence-transformers (session-scoped).

Each user upload gets a unique ``session_id``.  All vector points in
Qdrant carry that ID as a payload field, so search is always scoped
to the uploading user's paper.  When the session ends (browser closes,
user clicks "New paper", or the TTL expires), ``delete_session()``
wipes every point belonging to that session in a single Qdrant call.

This means 100 concurrent users each see only their own paper — and
we never accumulate stale embeddings.

Storage layout::

    Qdrant collection "paper_chunks"
    ├── point {id, vector[384], payload{session_id, doc_id,
    │         text, chunk_index, created_at}}
    └── ...

In-process session store (plain dict)::

    _sessions[session_id] = {
        "text":       <full paper text>,
        "filename":   <original filename>,
        "doc_id":     <content hash>,
        "created_at": <unix timestamp>,
        "chunk_count": <int>,
    }

Configuration (.env / environment)::

    QDRANT_URL=:memory:           # or http://localhost:6333 for Docker
    QDRANT_COLLECTION=paper_chunks
    EMBEDDING_MODEL=all-MiniLM-L6-v2
    SESSION_MAX_AGE_HOURS=2.0
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Dict, List, Optional, Tuple

from app.utils.logger import get_logger

_log = get_logger(__name__)

# ── lazy imports (loaded once on first use) ──────────────────────────────────
_qdrant_client = None   # QdrantClient instance
_embed_model   = None   # SentenceTransformer instance
_collection_ready = False


def _get_client():
    global _qdrant_client, _collection_ready
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from app.config import get_settings
        s = get_settings()
        _log.info("Connecting to Qdrant", extra={"url": s.qdrant_url})
        _qdrant_client = QdrantClient(location=s.qdrant_url)
        _ensure_collection(_qdrant_client, s.qdrant_collection)
        _collection_ready = True
    return _qdrant_client


def _get_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        from app.config import get_settings
        model_name = get_settings().embedding_model
        _log.info("Loading embedding model", extra={"model": model_name})
        _embed_model = SentenceTransformer(model_name)
        _log.info("Embedding model ready")
    return _embed_model


def _ensure_collection(client, name: str) -> None:
    from qdrant_client.models import Distance, VectorParams
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        _log.info("Created Qdrant collection", extra={"collection": name})


# ── In-process session metadata store ────────────────────────────────────────

_sessions: Dict[str, Dict] = {}


# ── Public API ────────────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    Session-scoped vector store backed by Qdrant.

    All public methods are synchronous wrappers — Qdrant's Python client
    handles its own I/O threading.
    """

    # ── Ingestion ─────────────────────────────────────────────────────

    def ingest(
        self,
        text: str,
        *,
        session_id: Optional[str] = None,
        filename: Optional[str] = None,
        chunk_size: int = 800,
        overlap: int = 200,
    ) -> Tuple[str, str]:
        """
        Chunk, embed, and index a document in Qdrant.

        Args:
            text:       Full document text.
            session_id: Caller-supplied session ID, or a new UUID is generated.
            filename:   Human label (stored in session metadata).
            chunk_size: Characters per chunk.
            overlap:    Overlap between adjacent chunks.

        Returns:
            ``(session_id, doc_id)`` — both strings.
        """
        if not text or not text.strip():
            raise ValueError("Cannot ingest empty text")

        session_id = session_id or str(uuid.uuid4())
        doc_id = hashlib.sha256(text[:512].encode()).hexdigest()[:16]

        chunks = _split(text, chunk_size, overlap)
        model  = _get_model()
        client = _get_client()

        from app.config import get_settings
        collection = get_settings().qdrant_collection

        _log.info("Embedding chunks", extra={
            "session_id": session_id, "chunks": len(chunks), "file": filename
        })

        vectors = model.encode(chunks, batch_size=32, show_progress_bar=False).tolist()

        from qdrant_client.models import PointStruct
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "session_id":  session_id,
                    "doc_id":      doc_id,
                    "text":        chunk,
                    "chunk_index": i,
                    "created_at":  time.time(),
                },
            )
            for i, (chunk, vec) in enumerate(zip(chunks, vectors))
        ]

        client.upsert(collection_name=collection, points=points)

        _sessions[session_id] = {
            "text":        text,
            "filename":    filename,
            "doc_id":      doc_id,
            "created_at":  time.time(),
            "chunk_count": len(chunks),
        }

        _log.info("Ingest complete", extra={
            "session_id": session_id, "doc_id": doc_id, "chunks": len(chunks)
        })
        return session_id, doc_id

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[str]:
        """
        Semantic search over paper chunks.

        Args:
            query:      Natural language query.
            session_id: Restrict results to this session's paper.
                        Pass ``None`` to search across all sessions
                        (used by the existing research pipeline).
            top_k:      Number of results.

        Returns:
            List of text chunks ranked by cosine similarity.
        """
        if not _sessions and session_id:
            return []

        model  = _get_model()
        client = _get_client()

        from app.config import get_settings
        collection = get_settings().qdrant_collection

        query_vec = model.encode(query).tolist()

        search_filter = None
        if session_id:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            search_filter = Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            )

        result = client.query_points(
            collection_name=collection,
            query=query_vec,
            query_filter=search_filter,
            limit=top_k,
        )
        return [p.payload["text"] for p in result.points]

    # ── Session management ─────────────────────────────────────────────

    def delete_session(self, session_id: str) -> int:
        """
        Delete all Qdrant points and session metadata for *session_id*.

        Returns the number of chunks deleted (0 if session not found).
        """
        meta = _sessions.pop(session_id, None)
        if meta is None:
            _log.warning("delete_session: unknown session", extra={"session_id": session_id})
            return 0

        from app.config import get_settings
        from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
        collection = get_settings().qdrant_collection
        client = _get_client()

        client.delete(
            collection_name=collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
                )
            ),
        )

        chunk_count = meta.get("chunk_count", 0)
        _log.info("Session deleted", extra={"session_id": session_id, "chunks": chunk_count})
        return chunk_count

    def cleanup_old_sessions(self) -> int:
        """
        Delete all sessions older than ``session_max_age_hours``.

        Called on startup and by the DELETE /paper/session/cleanup endpoint.
        Returns number of sessions cleaned.
        """
        from app.config import get_settings
        max_age = get_settings().session_max_age_hours
        cutoff  = time.time() - max_age * 3600
        stale   = [sid for sid, m in _sessions.items() if m["created_at"] < cutoff]
        for sid in stale:
            self.delete_session(sid)
        if stale:
            _log.info("Cleaned stale sessions", extra={"count": len(stale)})
        return len(stale)

    # ── Document access ────────────────────────────────────────────────

    def get_doc(self, session_id: str) -> Optional[str]:
        """Return the full text of the paper for *session_id*, or None."""
        return _sessions.get(session_id, {}).get("text")

    def get_session_meta(self, session_id: str) -> Optional[Dict]:
        """Return session metadata dict or None if session doesn't exist."""
        return _sessions.get(session_id)

    # ── Observability ──────────────────────────────────────────────────

    @property
    def session_count(self) -> int:
        return len(_sessions)

    @property
    def doc_count(self) -> int:
        return len(_sessions)

    @property
    def chunk_count(self) -> int:
        return sum(m.get("chunk_count", 0) for m in _sessions.values())


# ── Internal helpers ──────────────────────────────────────────────────────────

def _split(text: str, size: int, overlap: int) -> List[str]:
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + size])
        start += size - overlap
    return out


# ── Singleton ─────────────────────────────────────────────────────────────────

_inst: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    """Return the global KnowledgeBase singleton."""
    global _inst
    if _inst is None:
        _inst = KnowledgeBase()
    return _inst
