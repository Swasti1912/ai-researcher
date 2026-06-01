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

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.paper_summarizer import PaperSummarizerAgent
from app.agents.paper_qa import PaperQAAgent
from app.agents.paper_visualizer import PaperVisualizerAgent
from app.agents.paper_teacher import PaperTeacherAgent
from app.graph import get_graph
from app.knowledge_base import get_kb
from app.state import ResearchState
from app.utils.exceptions import AIResearcherError
from app.utils.logger import get_logger

_log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["AI Researcher"])

_store: Dict[str, Dict[str, Any]] = {}


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
    paper_evidence: List[str] = []
    related_papers: List[Dict[str, Any]] = []
    confidence: str = "medium"
    rag_chunks_used: int = 0
    external_papers_found: int = 0
    follow_up_questions: List[str] = []

class SessionDeleteResp(BaseModel):
    session_id: str
    chunks_deleted: int

class PaperVisualizeReq(BaseModel):
    session_id: str

class PaperVisualizeResp(BaseModel):
    session_id: str = ""
    architecture_diagram: Dict[str, Any] = {}
    concept_map: Dict[str, Any] = {}
    method_flow: Dict[str, Any] = {}
    charts: List[Dict[str, Any]] = []

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
        raise HTTPException(500, str(exc))

    return SubQuestionResp(question=req.question, answer=answer, papers=papers[:6])


@router.get("/health", response_model=HealthResp)
async def health():
    kb = get_kb()
    return HealthResp(kb_docs=kb.doc_count, kb_chunks=kb.chunk_count)


@router.post("/research", response_model=ResearchResp)
async def run_research(req: ResearchReq):
    """Synchronously run the full pipeline and return the result."""
    _log.info("Research request", extra={"q_len": len(req.query)})
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
        raise HTTPException(500, str(exc))


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


@router.post("/upload-paper", response_model=UploadResp)
async def upload_paper(file: UploadFile = File(...)):
    """
    Extract text from PDF/TXT, embed into Qdrant, return a session_id.

    The session_id scopes all subsequent /paper/summarize and /paper/ask
    calls to this user's paper.  Call DELETE /paper/session/{session_id}
    when done to free Qdrant storage.
    """
    _log.info("Upload", extra={"file": file.filename})
    content = await file.read()
    filename = file.filename or ""

    # ── Text extraction (CPU-bound / blocking — run off the event loop) ─
    def _extract_text() -> str:
        if filename.lower().endswith(".pdf"):
            try:
                import PyPDF2
                return "\n".join(
                    p.extract_text() or ""
                    for p in PyPDF2.PdfReader(io.BytesIO(content)).pages
                )
            except Exception:
                return content.decode("utf-8", errors="ignore")
        return content.decode("utf-8", errors="ignore")

    text = await asyncio.to_thread(_extract_text)
    if not text.strip():
        raise HTTPException(400, "No text extracted")

    # ── Embedding + Qdrant ingest (CPU-bound / blocking — run off the event loop) ─
    kb = get_kb()
    session_id, doc_id = await asyncio.to_thread(kb.ingest, text, filename=filename)

    return UploadResp(
        session_id=session_id,
        doc_id=doc_id,
        filename=filename,
        text_length=len(text),
        chunks=kb.get_session_meta(session_id).get("chunk_count", 0) if kb.get_session_meta(session_id) else 0,
        text_preview=text[:500],
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
        return PaperSummarizeResp(
            session_id=req.session_id,
            doc_id=doc_id,
            filename=filename,
            **summary,
        )
    except Exception as exc:
        _log.error("Summarize error", extra={"err": str(exc)})
        raise HTTPException(500, str(exc))


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

    try:
        agent = PaperQAAgent()
        result = await agent.answer(question=req.question, session_id=req.session_id)
        return PaperAskResp(question=req.question, **result)
    except Exception as exc:
        _log.error("PaperAsk error", extra={"err": str(exc)})
        raise HTTPException(500, str(exc))


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
        _log.error("Visualize error", extra={"err": str(exc)})
        raise HTTPException(500, str(exc))


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
        raise HTTPException(500, str(exc))


@router.post("/paper/from-url", response_model=UploadResp)
async def paper_from_url(req: FetchPaperReq):
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
    text = ""

    # ── Try to fetch paper content from arXiv ────────────────────────────────
    if req.url:
        url = req.url.strip()
        # Convert abs URL → PDF URL  e.g. arxiv.org/abs/2401.12345 → /pdf/2401.12345
        pdf_url = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)
        if not pdf_url.endswith(".pdf"):
            pdf_url = pdf_url.rstrip("/")

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(
                    pdf_url,
                    headers={"User-Agent": "AI-Researcher/1.0 (research tool; mailto:noreply@example.com)"},
                )
            if resp.status_code == 200 and resp.content:
                def _parse_pdf(content: bytes) -> str:
                    import PyPDF2, io
                    try:
                        return "\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(io.BytesIO(content)).pages)
                    except Exception:
                        return ""
                text = await asyncio.to_thread(_parse_pdf, resp.content)
        except Exception as exc:
            _log.warning("PDF fetch failed", extra={"url": pdf_url, "err": str(exc)})

    # ── Fallback 1: supplied abstract / summary text ──────────────────────────
    if not text.strip() and req.abstract:
        text = req.abstract
        filename = filename.replace(".pdf", ".txt")

    # ── Fallback 2: search arXiv by title (try full title, then first 5 words) ─
    if not text.strip() and req.title:
        import urllib.parse, xml.etree.ElementTree as ET

        async def _arxiv_search_and_fetch(query_title: str) -> str:
            """Search arXiv for query_title, return extracted PDF text or ''."""
            try:
                search_q = urllib.parse.quote_plus(f"ti:{query_title}")
                arxiv_url = f"https://export.arxiv.org/api/query?search_query={search_q}&max_results=1&sortBy=relevance"
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
                    sr = await c.get(arxiv_url, headers={"User-Agent": "AI-Researcher/1.0"})
                if sr.status_code != 200:
                    return ""
                ns = {"a": "http://www.w3.org/2005/Atom"}
                root = ET.fromstring(sr.text)
                entries = root.findall("a:entry", ns)
                if not entries:
                    return ""
                for entry in entries:
                    for lnk in entry.findall("a:link", ns):
                        if lnk.get("title") == "pdf":
                            pdf_url = lnk.get("href", "").replace("http://", "https://")
                            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c2:
                                pr = await c2.get(pdf_url, headers={"User-Agent": "AI-Researcher/1.0"})
                            if pr.status_code == 200 and pr.content:
                                def _parse_pdf(b: bytes) -> str:
                                    import PyPDF2, io
                                    try:
                                        return "\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(io.BytesIO(b)).pages)
                                    except Exception:
                                        return ""
                                return await asyncio.to_thread(_parse_pdf, pr.content)
            except Exception as exc:
                _log.warning("arXiv title search failed", extra={"err": str(exc)})
            return ""

        # Try full title first, then first 5 words as a broader fallback
        text = await _arxiv_search_and_fetch(req.title)
        if text.strip():
            _log.info("arXiv full-title fallback succeeded", extra={"title": req.title})
        else:
            short_title = " ".join(req.title.split()[:5])
            text = await _arxiv_search_and_fetch(short_title)
            if text.strip():
                _log.info("arXiv short-title fallback succeeded", extra={"short": short_title})

    if not text.strip():
        raise HTTPException(404, "Paper not accessible — PDF URL unavailable, no abstract provided, and no matching arXiv entry found")

    kb = get_kb()
    session_id, doc_id = await asyncio.to_thread(kb.ingest, text, filename=filename)
    _log.info("Ingested external paper", extra={"title": title, "session_id": session_id})
    return UploadResp(
        session_id=session_id,
        doc_id=doc_id,
        filename=filename,
        text_length=len(text),
        chunks=kb.get_session_meta(session_id).get("chunk_count", 0) if kb.get_session_meta(session_id) else 0,
        text_preview=text[:500],
    )


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
    """Delete all sessions older than SESSION_MAX_AGE_HOURS (default 2 h)."""
    cleaned = get_kb().cleanup_old_sessions()
    return {"cleaned": cleaned}


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
