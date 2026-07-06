"""
FastAPI Router.

Endpoints:
  POST /api/research          – run full pipeline (sync)
  POST /api/research/stream   – run pipeline with SSE agent-step events
  POST /api/upload-paper      – upload PDF/text → KB
  GET  /api/research/{id}     – poll result
  GET  /api/health            – health check
  GET  /api/graph-topology    – pipeline node/edge metadata for the UI
"""
from __future__ import annotations

import asyncio
import io
import json
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.paper_summarizer import PaperSummarizerAgent
from app.agents.paper_qa import PaperQAAgent
from app.agents.paper_visualizer import PaperVisualizerAgent
from app.agents.paper_teacher import PaperTeacherAgent
from app.config import get_settings
from app.graph import get_graph
from app.knowledge_base import get_kb
from app.state import ResearchState
from app.utils.exceptions import AIResearcherError
from app.utils.logger import get_logger

_log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["AI Researcher"])

_store: Dict[str, Dict[str, Any]] = {}


# ── Background jobs (HF Spaces proxy kills requests > ~60 s) ──────────────────
# The slow LLM endpoints (summarize / teach / visualize / teach-section) can
# exceed the reverse-proxy timeout on Hugging Face Spaces, which 504s any
# request that takes longer than about a minute. Instead of holding the HTTP
# connection open, POST /paper/<x>/start returns a job_id immediately, the
# work runs as an asyncio task, and the client polls GET /paper/job/{job_id}.
# NOTE: in-memory — requires a single uvicorn worker (which is what we run).

_jobs: Dict[str, Dict[str, Any]] = {}
_JOB_TTL_SECONDS = 15 * 60


def _jobs_gc() -> None:
    import time
    cutoff = time.time() - _JOB_TTL_SECONDS
    for jid in [j for j, v in _jobs.items() if v["created"] < cutoff]:
        _jobs.pop(jid, None)


def _start_job(coro) -> str:
    """Run ``coro`` as a background task; return a job_id to poll."""
    import time
    import uuid
    _jobs_gc()
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "running", "result": None, "error": None,
                     "created": time.time()}

    async def _run() -> None:
        try:
            result = await coro
            if isinstance(result, BaseModel):
                result = result.model_dump()
            _jobs[job_id]["result"] = result
            _jobs[job_id]["status"] = "done"
        except Exception as exc:  # HTTPException detail or plain message
            _jobs[job_id]["error"] = getattr(exc, "detail", None) or str(exc)
            _jobs[job_id]["status"] = "error"
            _log.error("Job failed", extra={"job": job_id, "err": _jobs[job_id]["error"]})

    asyncio.create_task(_run())
    return job_id


class JobStartResp(BaseModel):
    job_id: str
    status: str = "running"

class JobStatusResp(BaseModel):
    job_id: str
    status: str                              # running | done | error
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ── Schemas ──────────────────────────────────────────────────────────────────

class ResearchReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=10_000)
    paper_text: Optional[str] = None
    paper_filename: Optional[str] = None
    max_iterations: int = Field(3, ge=1, le=5)

class ResearchResp(BaseModel):
    request_id: str = ""
    status: str = "pending"
    original_query: str = ""
    refined_query: str = ""
    intent: Optional[Dict[str, Any]] = None
    sub_questions: List[Dict[str, Any]] = []
    api_results: List[Dict[str, Any]] = []
    aggregated_context: str = ""
    reasoning_output: str = ""
    visualizations: List[Dict[str, Any]] = []
    rag_references: List[str] = []
    evaluation: Optional[Dict[str, Any]] = None
    final_answer: str = ""
    error: Optional[str] = None
    agent_trace: List[Dict[str, Any]] = []

class UploadResp(BaseModel):
    session_id: str
    doc_id: str
    filename: Optional[str] = None
    text_length: int
    chunks: int
    text_preview: str = ""
    page_count: int = 0
    figure_count: int = 0

class FigureMeta(BaseModel):
    fig_id: str
    page: int
    caption: str = ""
    kind: str = "figure"

class FiguresResp(BaseModel):
    session_id: str
    figures: List[FigureMeta] = []

class HealthResp(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    kb_docs: int = 0
    kb_chunks: int = 0

class SubQuestionReq(BaseModel):
    question: str
    context: str = ""          # aggregated_context from the research run
    api_results: List[Dict[str, Any]] = []   # raw api_results for source cards

class SubQuestionResp(BaseModel):
    question: str = ""
    answer: str = ""
    papers: List[Dict[str, Any]] = []   # accessible source papers

class TopoNode(BaseModel):
    id: str; label: str; description: str; color: str = "orange"
class TopoEdge(BaseModel):
    source: str; target: str; label: str = ""; animated: bool = False
class Topology(BaseModel):
    nodes: List[TopoNode]; edges: List[TopoEdge]

class PaperSummarizeReq(BaseModel):
    session_id: str  # returned by /upload-paper
    filename: Optional[str] = None

class KeyConcept(BaseModel):
    name: str = ""
    definition: str = ""
    importance: str = ""

class SectionBreakdown(BaseModel):
    section: str = ""
    summary: str = ""

class PaperSummarizeResp(BaseModel):
    session_id: str = ""
    doc_id: str = ""
    filename: Optional[str] = None
    title: str = ""
    authors: str = ""
    domain: str = ""
    technical_depth: str = ""
    core_innovation: str = ""
    tldr: str = ""
    abstract_summary: str = ""
    section_breakdown: List[Dict[str, Any]] = []
    key_concepts: List[Dict[str, Any]] = []
    methodology: str = ""
    key_results: str = ""
    limitations: str = ""
    future_work: str = ""
    prior_work_comparison: str = ""
    key_contributions: List[str] = []  # kept for backwards compat

class PaperAskReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=5_000)
    session_id: str  # returned by /upload-paper

class PaperAskResp(BaseModel):
    question: str = ""
    answer: str = ""
    paper_evidence: List[Dict[str, Any]] = []   # [{text, page}]
    related_papers: List[Dict[str, Any]] = []
    confidence: str = "medium"
    rag_chunks_used: int = 0
    external_papers_found: int = 0
    follow_up_questions: List[str] = []
    rag_pages: List[int] = []

class SessionDeleteResp(BaseModel):
    session_id: str
    chunks_deleted: int

class PaperVisualizeReq(BaseModel):
    session_id: str

class PaperVisualizeResp(BaseModel):
    session_id: str = ""
    concept_diagrams: List[Dict[str, Any]] = []   # Mermaid diagrams
    equations: List[Dict[str, Any]] = []          # explained equations (KaTeX)
    charts: List[Dict[str, Any]] = []
    architecture_diagram: Dict[str, Any] = {}     # legacy (kept for compat)
    concept_map: Dict[str, Any] = {}
    method_flow: Dict[str, Any] = {}

class PaperTeachReq(BaseModel):
    session_id: str

class TeachChapter(BaseModel):
    number: int = 0
    title: str = ""
    explanation: str = ""
    analogy: str = ""
    key_takeaway: str = ""

class PaperTeachResp(BaseModel):
    session_id: str = ""
    lesson_title: str = ""
    big_picture: str = ""
    prerequisite_knowledge: str = ""
    chapters: List[Dict[str, Any]] = []
    how_it_all_fits: str = ""
    paper_in_one_sentence: str = ""

class TeachSectionReq(BaseModel):
    session_id: str
    section: str
    summary: str = ""

class TeachSectionResp(BaseModel):
    section: str = ""
    explanation: str = ""
    figures: List[Dict[str, Any]] = []   # [{fig_id, page, caption, kind}]
    pages: List[int] = []

# ── Library / persistence (P2) ────────────────────────────────────────────────
class LibraryItem(BaseModel):
    session_id: str
    filename: Optional[str] = None
    title: str = ""
    page_count: int = 0
    figure_count: int = 0
    created_at: float = 0.0
    source: str = "upload"
    has_pdf: bool = False
    has_summary: bool = False

class LibraryResp(BaseModel):
    papers: List[LibraryItem] = []

class ReopenResp(BaseModel):
    session_id: str
    filename: Optional[str] = None
    title: str = ""
    page_count: int = 0
    figure_count: int = 0
    created_at: float = 0.0
    has_pdf: bool = False
    summary: Optional[Dict[str, Any]] = None

class ChatItem(BaseModel):
    role: str
    content: str
    evidence: List[Dict[str, Any]] = []
    created_at: float = 0.0

class ChatHistoryResp(BaseModel):
    messages: List[ChatItem] = []

class Rect(BaseModel):
    x: float; y: float; w: float; h: float

class Highlight(BaseModel):
    id: str = ""
    session_id: str = ""
    page: int = 0
    color: str = "yellow"
    quote: str = ""
    note: str = ""
    rects: List[Rect] = []
    created_at: float = 0.0
    updated_at: float = 0.0

class HighlightsResp(BaseModel):
    highlights: List[Highlight] = []

class HighlightCreate(BaseModel):
    page: int
    color: str = "yellow"
    quote: str = ""
    note: str = ""
    rects: List[Rect] = []

class HighlightNoteUpdate(BaseModel):
    note: str = ""

class FetchPaperReq(BaseModel):
    url: str = ""        # arXiv abs or PDF URL
    abstract: str = ""   # fallback plain text (for non-arXiv sources)
    title: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalise(raw: Any, query: str) -> Dict[str, Any]:
    """Turn the LangGraph result (dict or dataclass) into a flat dict.

    LangGraph 1.x returns a plain dict from ainvoke(); older versions may
    return the state object directly.  Both cases are handled here.
    """
    if hasattr(raw, "to_api_dict"):
        # State dataclass returned directly (older LangGraph or custom schema)
        d = raw.to_api_dict()
        # Map internal field name to API field name
        if "error_message" in d:
            d["error"] = d.pop("error_message")
        # Remove internal-only fields that ResearchResp doesn't accept
        for _internal in ("iteration", "current_agent", "uploaded_paper_text",
                          "uploaded_paper_filename", "max_iterations"):
            d.pop(_internal, None)
    elif isinstance(raw, dict):
        # LangGraph 1.x returns a plain dict with all channel values.
        # Values can be Pydantic model instances, plain dicts, lists, or scalars.
        d = {}
        for k in ResearchResp.model_fields:
            # Also check the internal alias for 'error'
            v = raw.get(k) if k != "error" else raw.get("error") or raw.get("error_message")
            if v is None:
                # Keep the field absent so ResearchResp uses its default.
                continue
            if hasattr(v, "model_dump"):
                d[k] = v.model_dump()
            elif isinstance(v, list):
                serialised = []
                for x in v:
                    if hasattr(x, "model_dump"):
                        serialised.append(x.model_dump())
                    elif isinstance(x, dict):
                        serialised.append(x)
                    else:
                        serialised.append(str(x))
                d[k] = serialised
            else:
                d[k] = v
    else:
        d = {}
    d.setdefault("original_query", query)
    d.setdefault("status", "completed")
    return d


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/research/subquestion", response_model=SubQuestionResp)
async def explain_subquestion(req: SubQuestionReq):
    """
    Answer one sub-question in depth, citing from the aggregated research
    context and any accessible external papers already in api_results.
    """
    from app.agents.base import BaseAgent
    from app.utils.helpers import truncate as _trunc

    # Flatten accessible papers from api_results
    papers = []
    seen = set()
    for res in req.api_results:
        items = (res.get("data") or {}).get("papers", []) or (res.get("data") or {}).get("works", [])
        for p in items:
            url      = p.get("url", "")
            abstract = p.get("abstract") or p.get("summary") or ""
            title    = p.get("title", "")
            key = (url or title).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            papers.append({
                "title":    title,
                "url":      url,
                "abstract": abstract,
                "year":     p.get("year", ""),
                "source":   res.get("source", ""),
            })

    # Build a focused context for this sub-question
    paper_blurbs = "\n".join(
        f'[{p["source"]}] {p["title"]} ({p["year"]}): {_trunc(p["abstract"], 200)}'
        for p in papers[:6]
    ) or "(no external papers available)"

    context_snippet = _trunc(req.context, 3000) if req.context else "(no aggregated context)"

    class _QuickAgent(BaseAgent):
        name = "subq_explainer"
        @property
        def system_prompt(self):
            return (
                "You are an expert research assistant. Given a focused research sub-question, "
                "answer it in depth (300-500 words) using the provided context and external papers. "
                "Structure with ## headers. Cite sources by paper title. "
                "Explain concepts clearly — include how/why, not just what. "
                "Plain text only, no JSON."
            )
        async def execute(self, state):
            raise NotImplementedError

    agent = _QuickAgent()
    prompt = (
        f"Sub-question: {req.question}\n\n"
        f"--- Aggregated research context ---\n{context_snippet}\n\n"
        f"--- External papers ---\n{paper_blurbs}\n\n"
        "Provide a focused, well-cited answer to this sub-question."
    )
    try:
        answer = await agent.call_llm(prompt)
    except Exception as exc:
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))

    return SubQuestionResp(question=req.question, answer=answer, papers=papers[:6])


@router.get("/health", response_model=HealthResp)
async def health():
    kb = get_kb()
    return HealthResp(kb_docs=kb.doc_count, kb_chunks=kb.chunk_count)


@router.post("/research", response_model=ResearchResp)
async def run_research(req: ResearchReq):
    """Synchronously run the full pipeline and return the result."""
    _log.info("Research request", extra={"q_len": len(req.query)})

    from app.guardrails import screen
    allowed, msg = await screen(req.query, "query")
    if not allowed:
        raise HTTPException(400, msg)

    if req.paper_text:
        try:
            get_kb().ingest(req.paper_text, filename=req.paper_filename)  # session_id discarded — research mode
        except Exception as exc:
            _log.warning("KB ingest failed", extra={"err": str(exc)})

    state = ResearchState(
        original_query=req.query,
        uploaded_paper_text=req.paper_text,
        uploaded_paper_filename=req.paper_filename,
        max_iterations=req.max_iterations,
    )
    try:
        result = await get_graph().ainvoke(state)
        d = _normalise(result, req.query)
        resp = ResearchResp(**d)
        if resp.request_id:
            _store[resp.request_id] = resp.model_dump()
        return resp
    except AIResearcherError as exc:
        raise HTTPException(exc.status_code, exc.message)
    except Exception as exc:
        _log.error("Pipeline error", extra={"err": str(exc), "tb": traceback.format_exc()})
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))


@router.post("/research/stream")
async def run_research_stream(req: ResearchReq):
    """
    SSE endpoint – emits a JSON event for each agent that completes,
    allowing the React UI to animate the pipeline in real time.
    """
    _log.info("Stream request", extra={"q_len": len(req.query)})
    if req.paper_text:
        try:
            get_kb().ingest(req.paper_text, filename=req.paper_filename)
        except Exception as exc:
            _log.warning("KB ingest failed (stream)", extra={"err": str(exc)})

    state = ResearchState(
        original_query=req.query,
        uploaded_paper_text=req.paper_text,
        uploaded_paper_filename=req.paper_filename,
        max_iterations=req.max_iterations,
    )

    async def _events():
        try:
            graph = get_graph()
            prev_len = 0
            # Use "updates" mode explicitly — in LangGraph 1.x the default
            # compiled stream_mode may differ; "updates" gives {node: updates}.
            async for chunk in graph.astream(state, stream_mode="updates"):
                # chunk is a dict keyed by the node name
                for node_name, node_output in chunk.items():
                    if not isinstance(node_output, dict):
                        continue  # skip internal LangGraph book-keeping tasks
                    trace = node_output.get("agent_trace", [])
                    if isinstance(trace, list):
                        new_entries = trace[prev_len:]
                        prev_len = len(trace)
                        for entry in new_entries:
                            yield f"data: {json.dumps({'type':'agent_done','payload': entry})}\n\n"
                    # Send partial state snapshot
                    partial = _normalise(node_output, req.query)
                    yield f"data: {json.dumps({'type':'state_update','payload': partial})}\n\n"

            # Final complete event
            yield f"data: {json.dumps({'type':'complete'})}\n\n"
        except Exception as exc:
            _log.error("Stream error", extra={"err": str(exc), "tb": traceback.format_exc()})
            yield f"data: {json.dumps({'type':'error','payload': str(exc)})}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@router.get("/research/{request_id}", response_model=ResearchResp)
async def get_result(request_id: str):
    s = _store.get(request_id)
    if not s:
        raise HTTPException(404, "Not found")
    return ResearchResp(**s)


def _library_on() -> bool:
    """Persistence/Library is controlled solely by ENABLE_LIBRARY, independent of
    auth — so you can keep login on but turn off saved papers (and their disk
    usage). When on *and* auth is on, the library is scoped per-user."""
    return get_settings().enable_library


async def _persist_paper(session_id: str, pdf_bytes: Optional[bytes], source: str,
                         owner: str = "public") -> None:
    """Save a freshly-ingested paper to persistent storage and mark it persisted.

    No-op when the Library is disabled (single-tenant deployment): papers then
    live only in the caller's in-memory session and are never written to the
    shared store, so visitors can't see each other's uploads.
    """
    kb = get_kb()
    meta = kb.get_session_meta(session_id)
    if meta is not None:
        meta["owner"] = owner   # always tag the in-memory session for scoping
    if not _library_on():
        return
    try:
        from app import storage
        meta = meta or {}
        figs = meta.get("figures", [])
        await asyncio.to_thread(
            lambda: storage.save_paper(session_id, {**meta, "source": source, "owner": owner},
                                       pdf_bytes=pdf_bytes, figures=figs)
        )
        meta["persisted"] = True   # protect from the in-memory TTL cleanup
    except Exception as exc:
        _log.warning("persist paper failed", extra={"session_id": session_id, "err": str(exc)})


@router.post("/upload-paper", response_model=UploadResp)
async def upload_paper(request: Request, file: UploadFile = File(...)):
    """
    Extract text from PDF/TXT, embed into Qdrant, return a session_id.

    The session_id scopes all subsequent /paper/summarize and /paper/ask
    calls to this user's paper.  Call DELETE /paper/session/{session_id}
    when done to free Qdrant storage.
    """
    _log.info("Upload", extra={"file": file.filename})
    content = await file.read()
    filename = file.filename or ""
    kb = get_kb()

    if filename.lower().endswith(".pdf"):
        # Page-aware extraction (PyMuPDF) + figures; store the PDF bytes so the
        # viewer can render the original, and captions feed the RAG index.
        from app.knowledge_base.pdf_extract import extract_pdf
        result = await asyncio.to_thread(extract_pdf, content)
        full_text = "\n".join(p["text"] for p in result["pages"])
        if not full_text.strip() and not result["figures"]:
            raise HTTPException(400, "No text or figures extracted from PDF")
        from app.guardrails import screen
        allowed, msg = await screen(full_text[:4000], "document")
        if not allowed:
            raise HTTPException(400, msg)
        session_id, doc_id = await asyncio.to_thread(
            lambda: kb.ingest(
                pages=result["pages"], pdf_bytes=content, figures=result["figures"],
                page_count=result["page_count"], filename=filename,
            )
        )
        text_len, preview = len(full_text), full_text[:500]
        page_count, figure_count = result["page_count"], len(result["figures"])
    else:
        # Plain text (.txt / .md)
        text = content.decode("utf-8", errors="ignore")
        if not text.strip():
            raise HTTPException(400, "No text extracted")
        from app.guardrails import screen
        allowed, msg = await screen(text[:4000], "document")
        if not allowed:
            raise HTTPException(400, msg)
        session_id, doc_id = await asyncio.to_thread(
            lambda: kb.ingest(text=text, filename=filename)
        )
        text_len, preview, page_count, figure_count = len(text), text[:500], 0, 0

    from app.auth import require_owner
    await _persist_paper(session_id, content if filename.lower().endswith(".pdf") else None,
                         "upload", owner=require_owner(request))

    meta = kb.get_session_meta(session_id) or {}
    return UploadResp(
        session_id=session_id, doc_id=doc_id, filename=filename,
        text_length=text_len, chunks=meta.get("chunk_count", 0),
        text_preview=preview, page_count=page_count, figure_count=figure_count,
    )


@router.get("/paper/pdf/{session_id}")
async def get_paper_pdf(session_id: str):
    """Stream the original PDF bytes for a session (404 if none stored)."""
    data = get_kb().get_pdf_bytes(session_id)
    if not data:
        raise HTTPException(404, "No PDF stored for this session")
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{session_id}.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/paper/figures/{session_id}", response_model=FiguresResp)
async def list_paper_figures(session_id: str):
    """List extracted figures/tables (metadata only, no image bytes)."""
    kb = get_kb()
    if not kb.get_session_meta(session_id):
        raise HTTPException(404, f"Session '{session_id}' not found")
    figs = kb.get_figures(session_id)
    return FiguresResp(
        session_id=session_id,
        figures=[
            FigureMeta(fig_id=f["fig_id"], page=f["page"],
                       caption=f.get("caption", ""), kind=f.get("kind", "figure"))
            for f in figs
        ],
    )


@router.get("/paper/figure/{session_id}/{fig_id}")
async def get_paper_figure(session_id: str, fig_id: str):
    """Stream a single figure PNG (404 if missing or caption-only table)."""
    f = get_kb().get_figure(session_id, fig_id)
    if not f or not f.get("png"):
        raise HTTPException(404, "Figure not found")
    return StreamingResponse(
        io.BytesIO(f["png"]), media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/paper/summarize", response_model=PaperSummarizeResp)
async def summarize_paper(req: PaperSummarizeReq):
    """
    Summarise an uploaded paper.

    Requires a ``session_id`` returned by ``POST /upload-paper``.
    Fetches the full paper text from the session store and runs the
    PaperSummarizerAgent to produce a structured LLM summary.
    """
    kb = get_kb()
    text = kb.get_doc(req.session_id)
    if not text:
        raise HTTPException(404, f"Session '{req.session_id}' not found — upload the paper first")

    meta = kb.get_session_meta(req.session_id)
    doc_id  = meta["doc_id"]  if meta else ""
    filename = req.filename or (meta["filename"] if meta else None)

    try:
        agent = PaperSummarizerAgent()
        summary = await agent.summarize(text, filename=filename)
        # Cache summary in session meta so teach endpoint can use it
        if meta is not None:
            meta["summary"] = summary
        # Persist the summary (title + body) so the library + reopen show it.
        if _library_on():
            try:
                from app import storage
                await asyncio.to_thread(lambda: storage.update_summary(req.session_id, summary))
            except Exception as exc:
                _log.warning("persist summary failed", extra={"err": str(exc)})
        return PaperSummarizeResp(
            session_id=req.session_id,
            doc_id=doc_id,
            filename=filename,
            **summary,
        )
    except Exception as exc:
        _log.error("Summarize error", extra={"err": str(exc)})
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))


@router.post("/paper/ask", response_model=PaperAskResp)
async def ask_paper(req: PaperAskReq):
    """
    Answer a detailed question about the uploaded paper.

    Scoped to the caller's session: only retrieves chunks from their paper.
    Also searches arXiv + Semantic Scholar for related external context.
    """
    kb = get_kb()
    if not kb.get_session_meta(req.session_id):
        raise HTTPException(404, f"Session '{req.session_id}' not found — upload the paper first")

    from app.guardrails import screen
    allowed, msg = await screen(req.question, "question")
    if not allowed:
        return PaperAskResp(question=req.question, answer=msg, confidence="low")

    try:
        agent = PaperQAAgent()
        result = await agent.answer(question=req.question, session_id=req.session_id)
        # Persist both turns so chat history survives restart / reopen.
        if _library_on():
            try:
                from app import storage
                sid = req.session_id
                await asyncio.to_thread(lambda: storage.append_chat(sid, "user", req.question))
                await asyncio.to_thread(lambda: storage.append_chat(
                    sid, "assistant", result.get("answer", ""), evidence=result.get("paper_evidence")))
            except Exception as exc:
                _log.warning("persist chat failed", extra={"err": str(exc)})
        return PaperAskResp(question=req.question, **result)
    except Exception as exc:
        _log.error("PaperAsk error", extra={"err": str(exc)})
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))


@router.post("/paper/visualize", response_model=PaperVisualizeResp)
async def visualize_paper(req: PaperVisualizeReq):
    """
    Extract concept map, method flow, and result charts from the uploaded paper.

    Uses RAG to pull the most relevant chunks, then the LLM structures them
    into three visualization-ready JSON objects for React Flow + Recharts.
    """
    kb = get_kb()
    if not kb.get_session_meta(req.session_id):
        raise HTTPException(404, f"Session '{req.session_id}' not found — upload the paper first")
    try:
        agent = PaperVisualizerAgent()
        result = await agent.visualize(session_id=req.session_id)
        return PaperVisualizeResp(session_id=req.session_id, **result)
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        _log.error("Visualize error", extra={"err": detail})
        raise HTTPException(500, detail)


@router.post("/paper/teach", response_model=PaperTeachResp)
async def teach_paper(req: PaperTeachReq):
    """
    Generate a teacher-style walkthrough lesson for the uploaded paper.

    Reads the full paper text from the session store, optionally uses
    cached summary metadata for richer context, and returns a structured
    lesson plan with chapters, analogies, and key takeaways.
    """
    kb = get_kb()
    text = kb.get_doc(req.session_id)
    if not text:
        raise HTTPException(404, f"Session '{req.session_id}' not found — upload the paper first")

    meta = kb.get_session_meta(req.session_id)
    summary = meta.get("summary") if meta else None

    try:
        agent = PaperTeacherAgent()
        lesson = await agent.teach(text, filename=meta.get("filename") if meta else None, summary=summary)
        return PaperTeachResp(session_id=req.session_id, **lesson)
    except Exception as exc:
        _log.error("Teach error", extra={"err": str(exc)})
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))


@router.post("/paper/teach-section", response_model=TeachSectionResp)
async def teach_section(req: TeachSectionReq):
    """
    Extensively teach ONE section of the paper — weaving in its equations
    (LaTeX) and the figures/tables on that section's pages.
    """
    from app.agents.paper_section_teacher import PaperSectionTeacherAgent
    kb = get_kb()
    if not kb.get_session_meta(req.session_id):
        raise HTTPException(404, f"Session '{req.session_id}' not found — upload the paper first")
    try:
        agent = PaperSectionTeacherAgent()
        result = await agent.teach_section(req.session_id, req.section, req.summary)
        return TeachSectionResp(**result)
    except Exception as exc:
        _log.error("Teach-section error", extra={"err": str(exc)})
        raise HTTPException(500, getattr(exc, "detail", None) or str(exc))


# ── Async job variants of the slow LLM endpoints ──────────────────────────────
# Same request bodies, but they return a job_id immediately instead of holding
# the connection open. Poll GET /paper/job/{job_id} for the result — required
# on Hugging Face Spaces, whose proxy 504s requests longer than ~60 s.

@router.post("/paper/summarize/start", response_model=JobStartResp)
async def summarize_paper_start(req: PaperSummarizeReq):
    return JobStartResp(job_id=_start_job(summarize_paper(req)))


@router.post("/paper/teach/start", response_model=JobStartResp)
async def teach_paper_start(req: PaperTeachReq):
    return JobStartResp(job_id=_start_job(teach_paper(req)))


@router.post("/paper/visualize/start", response_model=JobStartResp)
async def visualize_paper_start(req: PaperVisualizeReq):
    return JobStartResp(job_id=_start_job(visualize_paper(req)))


@router.post("/paper/teach-section/start", response_model=JobStartResp)
async def teach_section_start(req: TeachSectionReq):
    return JobStartResp(job_id=_start_job(teach_section(req)))


@router.post("/paper/ask/start", response_model=JobStartResp)
async def ask_paper_start(req: PaperAskReq):
    return JobStartResp(job_id=_start_job(ask_paper(req)))


@router.post("/research/start", response_model=JobStartResp)
async def run_research_start(req: ResearchReq):
    return JobStartResp(job_id=_start_job(run_research(req)))


@router.get("/paper/job/{job_id}", response_model=JobStatusResp)
async def get_job_status(job_id: str):
    j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found or expired")
    return JobStatusResp(job_id=job_id, status=j["status"],
                         result=j["result"], error=j["error"])


@router.post("/paper/from-url", response_model=UploadResp)
async def paper_from_url(req: FetchPaperReq, request: Request):
    """
    Fetch a paper by URL (arXiv abs/PDF) or use supplied abstract text.
    Extracts text, embeds into Qdrant, returns a session_id exactly like
    /upload-paper — so the caller can immediately use /paper/summarize,
    /paper/ask, and /paper/visualize on the result.
    """
    import re
    import httpx

    title = req.title or "external_paper"
    filename = re.sub(r"[^a-z0-9_]", "_", title.lower())[:60] + ".pdf"
    pdf_bytes: Optional[bytes] = None
    text = ""

    async def _fetch_pdf(pdf_url: str) -> Optional[bytes]:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(
                    pdf_url,
                    headers={"User-Agent": "AI-Researcher/1.0 (research tool; mailto:noreply@example.com)"},
                )
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception as exc:
            _log.warning("PDF fetch failed", extra={"url": pdf_url, "err": str(exc)})
        return None

    # ── Try direct arXiv URL ────────────────────────────────────────────────
    if req.url:
        pdf_url = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", req.url.strip())
        if not pdf_url.endswith(".pdf"):
            pdf_url = pdf_url.rstrip("/")
        pdf_bytes = await _fetch_pdf(pdf_url)

    # ── Fallback: search arXiv by title (full title, then first 5 words) ─────
    if not pdf_bytes and req.title:
        import urllib.parse, xml.etree.ElementTree as ET

        async def _arxiv_search(query_title: str) -> Optional[bytes]:
            try:
                search_q = urllib.parse.quote_plus(f"ti:{query_title}")
                arxiv_url = f"https://export.arxiv.org/api/query?search_query={search_q}&max_results=1&sortBy=relevance"
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
                    sr = await c.get(arxiv_url, headers={"User-Agent": "AI-Researcher/1.0"})
                if sr.status_code != 200:
                    return None
                ns = {"a": "http://www.w3.org/2005/Atom"}
                for entry in ET.fromstring(sr.text).findall("a:entry", ns):
                    for lnk in entry.findall("a:link", ns):
                        if lnk.get("title") == "pdf":
                            return await _fetch_pdf(lnk.get("href", "").replace("http://", "https://"))
            except Exception as exc:
                _log.warning("arXiv title search failed", extra={"err": str(exc)})
            return None

        pdf_bytes = await _arxiv_search(req.title) or await _arxiv_search(" ".join(req.title.split()[:5]))

    kb = get_kb()

    # ── Ingest: PDF path (page-aware + figures + stored bytes) ───────────────
    if pdf_bytes:
        from app.knowledge_base.pdf_extract import extract_pdf
        result = await asyncio.to_thread(extract_pdf, pdf_bytes)
        full_text = "\n".join(p["text"] for p in result["pages"])
        if full_text.strip() or result["figures"]:
            session_id, doc_id = await asyncio.to_thread(
                lambda: kb.ingest(
                    pages=result["pages"], pdf_bytes=pdf_bytes, figures=result["figures"],
                    page_count=result["page_count"], filename=filename,
                )
            )
            _log.info("Ingested external PDF", extra={"title": title, "session_id": session_id})
            from app.auth import require_owner
            await _persist_paper(session_id, pdf_bytes, "url", owner=require_owner(request))
            meta = kb.get_session_meta(session_id) or {}
            return UploadResp(
                session_id=session_id, doc_id=doc_id, filename=filename,
                text_length=len(full_text), chunks=meta.get("chunk_count", 0),
                text_preview=full_text[:500], page_count=result["page_count"],
                figure_count=len(result["figures"]),
            )

    # ── Fallback: abstract-only (no PDF → /paper/pdf will 404) ───────────────
    if req.abstract and req.abstract.strip():
        text = req.abstract
        filename = filename.replace(".pdf", ".txt")
        session_id, doc_id = await asyncio.to_thread(lambda: kb.ingest(text=text, filename=filename))
        from app.auth import require_owner
        await _persist_paper(session_id, None, "url", owner=require_owner(request))
        meta = kb.get_session_meta(session_id) or {}
        return UploadResp(
            session_id=session_id, doc_id=doc_id, filename=filename,
            text_length=len(text), chunks=meta.get("chunk_count", 0),
            text_preview=text[:500], page_count=0, figure_count=0,
        )

    raise HTTPException(404, "Paper not accessible — PDF URL unavailable, no abstract provided, and no matching arXiv entry found")


@router.delete("/paper/session/{session_id}", response_model=SessionDeleteResp)
async def delete_session(session_id: str):
    """
    Free all Qdrant vectors for this session.

    Call this when the user is done (browser close, "New paper" click, logout).
    Safe to call multiple times — returns 0 chunks if already cleaned up.
    """
    kb = get_kb()
    deleted = kb.delete_session(session_id)
    _log.info("Session freed", extra={"session_id": session_id, "chunks": deleted})
    return SessionDeleteResp(session_id=session_id, chunks_deleted=deleted)


@router.delete("/paper/session/cleanup", response_model=Dict[str, Any])
async def cleanup_sessions():
    """Evict stale non-persisted sessions (persisted papers are never auto-deleted)."""
    cleaned = get_kb().cleanup_old_sessions()
    return {"cleaned": cleaned}


# ══ Library & persistence (P2) ════════════════════════════════════════════════
# ROUTE ORDER: every literal /paper/* route above and below must be declared
# BEFORE the greedy GET /paper/{session_id} (declared last), or e.g. /paper/library
# would be captured as session_id="library".

@router.get("/config")
async def client_config():
    """Runtime flags the frontend needs — e.g. whether to show the Library."""
    from app.llm import provider_chain
    s = get_settings()
    chain = provider_chain()
    return {
        "library_enabled": _library_on(),
        "auth_enabled": s.auth_enabled,
        "llm_providers": chain,          # e.g. ["openai","groq","gemini"] in fallback order
        "llm_primary": chain[0] if chain else None,
    }


@router.get("/llm-selftest")
async def llm_selftest():
    """Diagnostic: call Groq and Gemini directly (tiny prompt) with the live
    keys and report each one's success/error. Reveals why the fallback fails."""
    from app.llm import _build_openai, _build_groq, _build_gemini
    builders = {"openai": _build_openai, "groq": _build_groq, "gemini": _build_gemini}
    out: Dict[str, Any] = {}
    for name, build in builders.items():
        try:
            llm = build(None, 8)
            if llm is None:
                out[name] = {"ok": False, "error": "not configured (no key / package)"}
                continue
            r = await llm.ainvoke("Say hi")
            out[name] = {"ok": True, "sample": (r.content or "")[:40]}
        except Exception as e:  # noqa: BLE001
            out[name] = {"ok": False, "error": str(e)[:400]}
    return out


@router.get("/paper/library", response_model=LibraryResp)
async def paper_library(request: Request):
    if not _library_on():
        return LibraryResp(papers=[])
    from app import storage
    from app.auth import owner_id
    # Auth on → scope to the logged-in user; auth off → the shared "public" set.
    owner = owner_id(request) if get_settings().auth_enabled else None
    papers = await asyncio.to_thread(lambda: storage.list_papers(owner))
    return LibraryResp(papers=[LibraryItem(**{**p, "has_pdf": bool(p.get("has_pdf")),
                                              "has_summary": bool(p.get("has_summary"))}) for p in papers])


@router.get("/paper/{session_id}/chat", response_model=ChatHistoryResp)
async def paper_chat_history(session_id: str):
    from app import storage
    msgs = await asyncio.to_thread(lambda: storage.get_chat(session_id))
    return ChatHistoryResp(messages=[ChatItem(**m) for m in msgs])


@router.get("/paper/{session_id}/highlights", response_model=HighlightsResp)
async def list_highlights(session_id: str):
    from app import storage
    hls = await asyncio.to_thread(lambda: storage.list_highlights(session_id))
    return HighlightsResp(highlights=[Highlight(**h) for h in hls])


@router.post("/paper/{session_id}/highlights", response_model=Highlight)
async def create_highlight(session_id: str, body: HighlightCreate):
    from app import storage
    if not get_kb().get_session_meta(session_id):
        raise HTTPException(404, "Session not found")
    rects = [r.model_dump() for r in body.rects]
    h = await asyncio.to_thread(lambda: storage.add_highlight(
        session_id, body.page, body.color, body.quote, body.note, rects))
    return Highlight(**h)


@router.patch("/paper/highlights/{highlight_id}", response_model=Highlight)
async def update_highlight(highlight_id: str, body: HighlightNoteUpdate):
    from app import storage
    h = await asyncio.to_thread(lambda: storage.update_highlight_note(highlight_id, body.note))
    if not h:
        raise HTTPException(404, "Highlight not found")
    return Highlight(**h)


@router.delete("/paper/highlights/{highlight_id}", response_model=Dict[str, Any])
async def remove_highlight(highlight_id: str):
    from app import storage
    await asyncio.to_thread(lambda: storage.delete_highlight(highlight_id))
    return {"deleted": True}


@router.get("/paper/{session_id}", response_model=ReopenResp)
async def reopen_paper(session_id: str):
    """
    Reopen a paper's metadata + cached summary.

    Prefers the persistent store, but falls back to the live in-memory session
    when the paper was never persisted — e.g. ENABLE_LIBRARY=false (deploy mode),
    where the research "Summarize & visualize" flow ingests a paper into memory
    only and then reopens it here.
    """
    from app import storage
    row = await asyncio.to_thread(lambda: storage.get_paper(session_id))
    if row:
        if not get_kb().get_session_meta(session_id):
            await asyncio.to_thread(get_kb().load_index)
        return ReopenResp(
            session_id=session_id, filename=row.get("filename"), title=row.get("title") or "",
            page_count=row.get("page_count", 0), figure_count=row.get("figure_count", 0),
            created_at=row.get("created_at", 0.0), has_pdf=bool(row.get("pdf_path")),
            summary=row.get("summary"),
        )

    # Fallback: the in-memory session (not persisted).
    meta = get_kb().get_session_meta(session_id)
    if not meta:
        raise HTTPException(404, f"Paper '{session_id}' not found")
    summary = meta.get("summary")
    title = summary.get("title", "") if isinstance(summary, dict) else ""
    return ReopenResp(
        session_id=session_id,
        filename=meta.get("filename"),
        title=title,
        page_count=meta.get("page_count", 0),
        figure_count=len(meta.get("figures") or []),
        created_at=meta.get("created_at", 0.0),
        has_pdf=bool(meta.get("pdf_bytes")) and meta.get("page_count", 0) > 0,
        summary=summary,
    )


@router.get("/graph-topology", response_model=Topology)
async def graph_topology():
    return Topology(
        nodes=[
            TopoNode(id="orchestrator", label="Orchestrator",      description="Validates & routes queries",                  color="orange"),
            TopoNode(id="refiner",      label="Refiner Agent",     description="Modifies user prompt for AI Researcher context", color="orange"),
            TopoNode(id="intent",       label="Intent Agent",      description="Ranks question by intent (Why/How/When)",     color="olive"),
            TopoNode(id="decomposer",   label="Decomposer Agent",  description="Decomposes into simpler sub-questions",       color="olive"),
            TopoNode(id="aggregator",   label="Aggregator Agent",  description="Aggregates results from different APIs",      color="green"),
            TopoNode(id="reasoning",    label="Reasoning Agent",   description="Reasoning & visualization with RAG",          color="green"),
            TopoNode(id="evaluator",    label="Evaluator Agent",   description="Quality gate with feedback loop",             color="green"),
        ],
        edges=[
            TopoEdge(source="orchestrator", target="refiner"),
            TopoEdge(source="refiner",      target="intent"),
            TopoEdge(source="intent",       target="decomposer"),
            TopoEdge(source="decomposer",   target="aggregator",  label="API calls"),
            TopoEdge(source="aggregator",   target="reasoning",   label="Aggregated data"),
            TopoEdge(source="reasoning",    target="evaluator"),
            TopoEdge(source="evaluator",    target="orchestrator", label="Loop back", animated=True),
        ],
    )
