"""
AI Researcher – FastAPI Application.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.utils.exceptions import AIResearcherError
from app.utils.logger import get_logger, setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator:
    s = get_settings()
    setup_logging(s.log_level)
    log = get_logger("main")
    log.info("Starting", extra={"model": s.llm_model, "port": s.port})

    # Eagerly initialise the embedding model and Qdrant client so the very
    # first paper upload doesn't time out waiting for a cold-start model load.
    # Run in a thread pool — SentenceTransformer loading is CPU/IO-bound and
    # must not block the async event loop.
    try:
        from app.knowledge_base import get_kb
        kb = get_kb()
        await asyncio.to_thread(kb._warmup)
        log.info("Knowledge base warmed up")
    except Exception as exc:
        log.warning("KB warmup failed (non-fatal)", extra={"err": str(exc)})

    # Initialise persistent storage and rehydrate the paper library (P2).
    try:
        from app import storage
        from app.knowledge_base import get_kb
        await asyncio.to_thread(storage.init_db)
        await asyncio.to_thread(get_kb().load_index)
    except Exception as exc:
        log.warning("Storage init/load failed (non-fatal)", extra={"err": str(exc)})

    # Periodic idle-session sweeper: evicts in-memory sessions past the TTL so
    # abandoned uploads don't linger (persisted Library papers are exempt).
    async def _sweeper() -> None:
        from app.knowledge_base import get_kb
        while True:
            await asyncio.sleep(600)  # every 10 minutes
            try:
                n = await asyncio.to_thread(get_kb().cleanup_old_sessions)
                if n:
                    log.info("Idle sweeper evicted sessions", extra={"count": n})
            except Exception as exc:
                log.warning("Idle sweeper failed", extra={"err": str(exc)})

    sweeper_task = asyncio.create_task(_sweeper())

    yield
    sweeper_task.cancel()
    log.info("Shutdown")


app = FastAPI(
    title="AI Researcher",
    description="Multi-agent research assistant powered by LangGraph.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Signed session cookie — powers Google OAuth login + per-user library scoping.
# https_only is on in the deployment (served over HTTPS); off for local http.
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402
app.add_middleware(
    SessionMiddleware,
    secret_key=s.session_secret,
    same_site="lax",
    https_only=bool(s.oauth_redirect_base.startswith("https")),
    max_age=60 * 60 * 12,   # 12h session
)


@app.exception_handler(AIResearcherError)
async def _app_err(_req: Request, exc: AIResearcherError) -> JSONResponse:
    return JSONResponse(content=exc.to_dict(), status_code=exc.status_code)


@app.exception_handler(Exception)
async def _generic(_req: Request, exc: Exception) -> JSONResponse:
    get_logger("main").error("Unhandled", extra={"err": str(exc)})
    return JSONResponse(content={"error": "InternalError", "message": str(exc)}, status_code=500)


from app.auth import auth_router  # noqa: E402
app.include_router(auth_router)
app.include_router(router)


# ── Frontend (production) ─────────────────────────────────────────────────────
# In production (Docker / HF Spaces) the built React app is copied to
# frontend/dist and served by FastAPI itself — same origin, no CORS needed.
# In local dev, dist/ usually doesn't exist (Vite dev server on :3000 proxies
# /api instead), so we fall back to a plain JSON root.
_UI_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class _CachedUI(StaticFiles):
    """Serve the SPA with correct caching:
      • index.html → no-cache, so returning visitors always fetch the newest
        (hashed) bundle instead of a stale one that can render blank/broken.
      • hashed assets (/assets/*) → cache forever; they're content-addressed.
    """
    async def get_response(self, path, scope):  # type: ignore[override]
        resp = await super().get_response(path, scope)
        if resp.status_code == 200:
            if "text/html" in resp.headers.get("content-type", ""):
                resp.headers["Cache-Control"] = "no-cache"
            else:
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


if _UI_DIST.is_dir() and (_UI_DIST / "index.html").is_file():
    # Mounted last: /api, /docs and /redoc are already registered and win.
    app.mount("/", _CachedUI(directory=str(_UI_DIST), html=True), name="ui")
else:
    @app.get("/", tags=["root"])
    async def root():
        return {"service": "AI Researcher", "docs": "/docs"}
