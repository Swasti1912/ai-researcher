"""
AI Researcher – FastAPI Application.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

    yield
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


@app.exception_handler(AIResearcherError)
async def _app_err(_req: Request, exc: AIResearcherError) -> JSONResponse:
    return JSONResponse(content=exc.to_dict(), status_code=exc.status_code)


@app.exception_handler(Exception)
async def _generic(_req: Request, exc: Exception) -> JSONResponse:
    get_logger("main").error("Unhandled", extra={"err": str(exc)})
    return JSONResponse(content={"error": "InternalError", "message": str(exc)}, status_code=500)


app.include_router(router)


@app.get("/", tags=["root"])
async def root():
    return {"service": "AI Researcher", "docs": "/docs"}
