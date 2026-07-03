"""
Persistent storage for Paper Q&A (P2) — SQLite + files on disk.

- Metadata (papers, figures, chat, highlights) lives in SQLite (``data/app.db``).
- Byte-heavy blobs (the original PDF, figure PNGs) live on disk under
  ``data/papers/{session_id}/`` — never in the DB or in memory long-term.
- Qdrant vectors persist separately (on-disk, configured in knowledge_base).

All functions are synchronous and MUST be called via ``asyncio.to_thread`` from
the async API layer (mirrors how ``kb.ingest`` is already invoked). A single
module-level connection guarded by a lock keeps this thread-safe and cheap.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.utils.logger import get_logger

_log = get_logger(__name__)

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()


# ── paths ─────────────────────────────────────────────────────────────────────

def _data_dir() -> Path:
    return Path(get_settings().data_dir)


def _db_path() -> Path:
    return _data_dir() / "app.db"


def _paper_dir(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return _data_dir() / "papers" / safe


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_.") or "file"


# ── init ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the data dir, open the connection, and ensure the schema exists."""
    global _conn
    with _lock:
        if _conn is not None:
            return
        _data_dir().mkdir(parents=True, exist_ok=True)
        (_data_dir() / "papers").mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS papers(
              session_id   TEXT PRIMARY KEY,
              doc_id       TEXT,
              filename     TEXT,
              title        TEXT,
              page_count   INTEGER DEFAULT 0,
              figure_count INTEGER DEFAULT 0,
              chunk_count  INTEGER DEFAULT 0,
              created_at   REAL,
              summary_json TEXT,
              full_text    TEXT,
              pdf_path     TEXT,
              source       TEXT
            );
            CREATE TABLE IF NOT EXISTS figures(
              session_id TEXT, fig_id TEXT, page INTEGER,
              caption TEXT, kind TEXT, png_path TEXT,
              PRIMARY KEY(session_id, fig_id)
            );
            CREATE TABLE IF NOT EXISTS chat(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT, role TEXT, content TEXT,
              evidence_json TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS highlights(
              id TEXT PRIMARY KEY, session_id TEXT, page INTEGER,
              color TEXT, quote TEXT, note TEXT, rects_json TEXT,
              created_at REAL, updated_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_fig_sid  ON figures(session_id);
            CREATE INDEX IF NOT EXISTS idx_chat_sid ON chat(session_id);
            CREATE INDEX IF NOT EXISTS idx_hl_sid   ON highlights(session_id);
            """
        )
        _conn.commit()
        _log.info("Storage ready", extra={"db": str(_db_path())})


def _c() -> sqlite3.Connection:
    if _conn is None:
        init_db()
    return _conn  # type: ignore[return-value]


# ── papers ────────────────────────────────────────────────────────────────────

def save_paper(session_id: str, meta: Dict[str, Any],
               pdf_bytes: Optional[bytes] = None,
               figures: Optional[List[Dict]] = None) -> None:
    """Persist a paper: PDF + figure PNGs to disk, metadata to SQLite."""
    figures = figures or []
    pdir = _paper_dir(session_id)
    pdir.mkdir(parents=True, exist_ok=True)

    pdf_path = None
    if pdf_bytes:
        pdf_path = str(pdir / "paper.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

    fig_dir = pdir / "figures"
    fig_rows = []
    for fig in figures:
        png = fig.get("png")
        png_path = None
        if png:
            fig_dir.mkdir(parents=True, exist_ok=True)
            png_path = str(fig_dir / f"{_safe_name(fig['fig_id'])}.png")
            with open(png_path, "wb") as f:
                f.write(png)
        fig_rows.append((session_id, fig["fig_id"], fig.get("page", 0),
                         fig.get("caption", ""), fig.get("kind", "figure"), png_path))

    with _lock:
        c = _c()
        c.execute(
            """INSERT OR REPLACE INTO papers(session_id, doc_id, filename, title,
                 page_count, figure_count, chunk_count, created_at, summary_json,
                 full_text, pdf_path, source)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, meta.get("doc_id"), meta.get("filename"),
             meta.get("title") or "", meta.get("page_count", 0), len(figures),
             meta.get("chunk_count", 0), meta.get("created_at") or time.time(),
             json.dumps(meta["summary"]) if meta.get("summary") else None,
             meta.get("text") or "", pdf_path, meta.get("source", "upload")),
        )
        c.execute("DELETE FROM figures WHERE session_id=?", (session_id,))
        c.executemany(
            "INSERT OR REPLACE INTO figures(session_id, fig_id, page, caption, kind, png_path) VALUES(?,?,?,?,?,?)",
            fig_rows,
        )
        c.commit()


def update_summary(session_id: str, summary: Dict[str, Any]) -> None:
    with _lock:
        _c().execute(
            "UPDATE papers SET summary_json=?, title=? WHERE session_id=?",
            (json.dumps(summary), summary.get("title") or "", session_id),
        )
        _c().commit()


def list_papers() -> List[Dict[str, Any]]:
    with _lock:
        rows = _c().execute(
            """SELECT session_id, doc_id, filename, title, page_count, figure_count,
                      chunk_count, created_at, source,
                      (summary_json IS NOT NULL) AS has_summary,
                      (pdf_path IS NOT NULL) AS has_pdf
               FROM papers ORDER BY created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_paper(session_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        row = _c().execute("SELECT * FROM papers WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["summary"] = json.loads(d["summary_json"]) if d.get("summary_json") else None
    return d


def delete_paper(session_id: str) -> None:
    with _lock:
        c = _c()
        for tbl in ("papers", "figures", "chat", "highlights"):
            c.execute(f"DELETE FROM {tbl} WHERE session_id=?", (session_id,))
        c.commit()
    shutil.rmtree(_paper_dir(session_id), ignore_errors=True)


def _resolve(session_id: str, stored: Optional[str], *parts: str) -> Optional[str]:
    """Prefer the path rebuilt from the current data_dir (portable across a
    relocated/mounted data dir, e.g. a container) and fall back to the absolute
    path recorded at write time."""
    if stored is None:
        return None
    canonical = str(_paper_dir(session_id).joinpath(*parts))
    if os.path.exists(canonical):
        return canonical
    return stored if os.path.exists(stored) else None


def read_pdf(session_id: str) -> Optional[bytes]:
    with _lock:
        row = _c().execute("SELECT pdf_path FROM papers WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        return None
    path = _resolve(session_id, row["pdf_path"], "paper.pdf")
    if not path:
        return None
    with open(path, "rb") as f:
        return f.read()


def list_figures(session_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = _c().execute(
            "SELECT fig_id, page, caption, kind, png_path FROM figures WHERE session_id=? ORDER BY page",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def read_figure_png(session_id: str, fig_id: str) -> Optional[bytes]:
    with _lock:
        row = _c().execute(
            "SELECT png_path FROM figures WHERE session_id=? AND fig_id=?", (session_id, fig_id),
        ).fetchone()
    if not row or not row["png_path"]:
        return None
    path = _resolve(session_id, row["png_path"], "figures", f"{_safe_name(fig_id)}.png")
    if not path:
        return None
    with open(path, "rb") as f:
        return f.read()


# ── chat ──────────────────────────────────────────────────────────────────────

def append_chat(session_id: str, role: str, content: str, evidence: Any = None) -> None:
    with _lock:
        _c().execute(
            "INSERT INTO chat(session_id, role, content, evidence_json, created_at) VALUES(?,?,?,?,?)",
            (session_id, role, content, json.dumps(evidence) if evidence else None, time.time()),
        )
        _c().commit()


def get_chat(session_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = _c().execute(
            "SELECT role, content, evidence_json, created_at FROM chat WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["evidence"] = json.loads(d.pop("evidence_json")) if d.get("evidence_json") else []
        out.append(d)
    return out


# ── highlights ────────────────────────────────────────────────────────────────

def add_highlight(session_id: str, page: int, color: str, quote: str,
                  note: str, rects: List[Dict]) -> Dict[str, Any]:
    hid = uuid.uuid4().hex
    now = time.time()
    with _lock:
        _c().execute(
            """INSERT INTO highlights(id, session_id, page, color, quote, note, rects_json, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (hid, session_id, page, color, quote, note, json.dumps(rects), now, now),
        )
        _c().commit()
    return {"id": hid, "session_id": session_id, "page": page, "color": color,
            "quote": quote, "note": note, "rects": rects, "created_at": now, "updated_at": now}


def list_highlights(session_id: str) -> List[Dict[str, Any]]:
    with _lock:
        rows = _c().execute(
            "SELECT * FROM highlights WHERE session_id=? ORDER BY page, created_at", (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["rects"] = json.loads(d.pop("rects_json")) if d.get("rects_json") else []
        out.append(d)
    return out


def update_highlight_note(hid: str, note: str) -> Optional[Dict[str, Any]]:
    with _lock:
        c = _c()
        c.execute("UPDATE highlights SET note=?, updated_at=? WHERE id=?", (note, time.time(), hid))
        c.commit()
        row = c.execute("SELECT * FROM highlights WHERE id=?", (hid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["rects"] = json.loads(d.pop("rects_json")) if d.get("rects_json") else []
    return d


def delete_highlight(hid: str) -> None:
    with _lock:
        _c().execute("DELETE FROM highlights WHERE id=?", (hid,))
        _c().commit()
