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
        text: Optional[str] = None,
        *,
        pages: Optional[List[Dict]] = None,
        pdf_bytes: Optional[bytes] = None,
        figures: Optional[List[Dict]] = None,
        page_count: int = 0,
        session_id: Optional[str] = None,
        filename: Optional[str] = None,
        chunk_size: int = 800,
        overlap: int = 200,
    ) -> Tuple[str, str]:
        """
        Chunk, embed, and index a document in Qdrant.

        Two input modes:
          * Plain text (legacy / research mode / .txt / .md): pass ``text``.
          * PDF (page-aware): pass ``pages`` = [{"page_number", "text"}], plus
            optional ``pdf_bytes``, ``figures`` (from pdf_extract.extract_pdf),
            and ``page_count``. Chunks are cut per page so each carries an exact
            ``page_number``. Figure captions are embedded as extra RAG chunks.

        Returns ``(session_id, doc_id)``.
        """
        # ── Build (chunk, page_number, kind, fig_id) tuples ──────────────
        records: List[Dict] = []          # {"text", "page", "kind", "fig_id"}
        if pages:
            for pg in pages:
                pno = int(pg.get("page_number") or 0)
                for ch in _split(pg.get("text") or "", chunk_size, overlap):
                    if ch.strip():
                        records.append({"text": ch, "page": pno, "kind": "body", "fig_id": None})
            full_text = "\n".join(pg.get("text") or "" for pg in pages)
        else:
            if not text or not text.strip():
                raise ValueError("Cannot ingest empty text")
            for ch in _split(text, chunk_size, overlap):
                if ch.strip():
                    records.append({"text": ch, "page": 0, "kind": "body", "fig_id": None})
            full_text = text

        body_count = len(records)

        # Figure captions → additional retrievable chunks
        for fig in (figures or []):
            cap = (fig.get("caption") or "").strip()
            if cap:
                records.append({
                    "text": cap, "page": int(fig.get("page") or 0),
                    "kind": "figure_caption", "fig_id": fig.get("fig_id"),
                })

        if not records:
            raise ValueError("Cannot ingest empty document")

        session_id = session_id or str(uuid.uuid4())
        doc_id = hashlib.sha256(full_text[:512].encode()).hexdigest()[:16]

        model  = _get_model()
        client = _get_client()
        from app.config import get_settings
        collection = get_settings().qdrant_collection

        _log.info("Embedding chunks", extra={
            "session_id": session_id, "chunks": len(records),
            "body": body_count, "figures": len(figures or []), "file": filename,
        })

        vectors = model.encode([r["text"] for r in records],
                               batch_size=32, show_progress_bar=False).tolist()

        from qdrant_client.models import PointStruct
        now = time.time()
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "session_id":  session_id,
                    "doc_id":      doc_id,
                    "text":        r["text"],
                    "chunk_index": i,
                    "page_number": r["page"],
                    "kind":        r["kind"],
                    "fig_id":      r["fig_id"],
                    "created_at":  now,
                },
            )
            for i, (r, vec) in enumerate(zip(records, vectors))
        ]
        client.upsert(collection_name=collection, points=points)

        _sessions[session_id] = {
            "text":        full_text,
            "filename":    filename,
            "doc_id":      doc_id,
            "created_at":  now,
            "chunk_count": body_count,
            "pdf_bytes":   pdf_bytes,
            "figures":     figures or [],
            "page_count":  page_count,
        }

        _log.info("Ingest complete", extra={
            "session_id": session_id, "doc_id": doc_id,
            "chunks": len(records), "pages": page_count,
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
        return [p.payload["text"] for p in self._query(query, session_id, top_k)]

    def search_with_meta(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        Like :meth:`search` but returns payload metadata per hit:
        ``[{"text", "page_number", "kind", "fig_id", "score"}, ...]``.
        """
        out = []
        for p in self._query(query, session_id, top_k):
            pl = p.payload or {}
            out.append({
                "text":        pl.get("text", ""),
                "page_number": pl.get("page_number", 0),
                "kind":        pl.get("kind", "body"),
                "fig_id":      pl.get("fig_id"),
                "score":       getattr(p, "score", None),
            })
        return out

    def _query(self, query: str, session_id: Optional[str], top_k: int):
        """Shared vector query → list of scored points (empty if nothing indexed)."""
        if not _sessions:
            return []
        if session_id and session_id not in _sessions:
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
        return list(result.points)

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

    # ── PDF & figure access ────────────────────────────────────────────

    def get_pdf_bytes(self, session_id: str) -> Optional[bytes]:
        """Return the stored original PDF bytes, or None (txt/md or not found)."""
        return _sessions.get(session_id, {}).get("pdf_bytes")

    def get_figures(self, session_id: str) -> List[Dict]:
        """Return the extracted figures list (each with png bytes) for a session."""
        return _sessions.get(session_id, {}).get("figures", []) or []

    def get_figure(self, session_id: str, fig_id: str) -> Optional[Dict]:
        """Return a single figure dict by id, or None."""
        for f in self.get_figures(session_id):
            if f.get("fig_id") == fig_id:
                return f
        return None

    def get_page_count(self, session_id: str) -> int:
        return _sessions.get(session_id, {}).get("page_count", 0)

    # ── Warmup ────────────────────────────────────────────────────────

    def _warmup(self) -> None:
        """
        Eagerly load the embedding model and initialise the Qdrant client.

        Called once at server startup so the first paper upload is never
        delayed by cold-start model loading (which can take 30-90 s and
        cause the frontend's 60-second timeout to fire).
        """
        _get_model()   # loads sentence-transformers model into memory
        _get_client()  # connects to Qdrant and ensures collection exists
        _log.info("Embedding model and Qdrant client ready")

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
