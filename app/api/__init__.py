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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalise(raw: Any, query: str) -> Dict[str, Any]:
    """Turn the LangGraph result (dict or dataclass) into a flat dict."""
    if hasattr(raw, "to_api_dict"):
        d = raw.to_api_dict()
    elif isinstance(raw, dict):
        d = {}
        for k in ResearchResp.model_fields:
            v = raw.get(k)
            if v is None:
                continue
            if hasattr(v, "model_dump"):
                d[k] = v.model_dump()
            elif isinstance(v, list):
                d[k] = [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
            else:
                d[k] = v
    else:
        d = {}
    d.setdefault("original_query", query)
    return d


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResp)
async def health():
    kb = get_kb()
    return HealthResp(kb_docs=kb.doc_count, kb_chunks=kb.chunk_count)


@router.post("/research", response_model=ResearchResp)
async def run_research(req: ResearchReq):
    """Synchronously run the full pipeline and return the result."""
    _log.info("Research request", extra={"q_len": len(req.query)})
    if req.paper_text:
        get_kb().ingest(req.paper_text, filename=req.paper_filename)  # session_id discarded — research mode

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
        get_kb().ingest(req.paper_text, filename=req.paper_filename)

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
            async for chunk in graph.astream(state):
                # chunk is a dict keyed by the node name
                for node_name, node_output in chunk.items():
                    trace = node_output.get("agent_trace", [])
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
    text = ""
    if file.filename and file.filename.lower().endswith(".pdf"):
        try:
            import PyPDF2
            text = "\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(io.BytesIO(content)).pages)
        except Exception:
            text = content.decode("utf-8", errors="ignore")
    else:
        text = content.decode("utf-8", errors="ignore")
    if not text.strip():
        raise HTTPException(400, "No text extracted")

    kb = get_kb()
    session_id, doc_id = kb.ingest(text, filename=file.filename)
    return UploadResp(
        session_id=session_id,
        doc_id=doc_id,
        filename=file.filename,
        text_length=len(text),
        chunks=kb.chunk_count,
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
