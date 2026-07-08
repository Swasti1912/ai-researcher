# AI Researcher — Architecture

## System Overview

Two independent modes share the same FastAPI backend and React frontend:

1. **Research Mode** — multi-agent pipeline that answers open research questions by searching arXiv, Semantic Scholar, and CrossRef, then synthesising with RAG.
2. **Paper Q&A Mode** — upload a paper → session-scoped RAG → rich summary, guided lesson, concept explorer, visualizations, and contextual Q&A.

---

## Research Mode — Multi-Agent Pipeline

```
User Query
    │
    ▼
┌─────────────────┐
│   Orchestrator   │ ◄─────────────────────────────────────────┐
└────────┬────────┘                                            │
         ▼                                                     │
┌─────────────────┐                                            │
│  Refiner Agent  │  Rewrites query for AI research context    │
└────────┬────────┘                                            │
         ▼                                                     │
┌─────────────────┐                                            │
│  Intent Agent   │  Classifies: Why / How / When + domain     │
└────────┬────────┘                                            │
         ▼                                                     │
┌─────────────────┐                                            │
│Decomposer Agent │  Splits into sub-questions                 │
└────────┬────────┘                                            │
         ▼        ┌──────────────────────────┐                 │
┌─────────────────┐│ arXiv · Semantic Scholar │                 │
│Aggregator Agent │◄│ CrossRef · External APIs│                 │
└────────┬────────┘└──────────────────────────┘                 │
         ▼        ┌──────────────────────────┐                 │
┌─────────────────┐│  Qdrant Vector DB (RAG)  │                 │
│ Reasoning Agent │◄│  session-scoped chunks   │                 │
└────────┬────────┘└──────────────────────────┘                 │
         ▼                                                     │
┌─────────────────┐                                            │
│ Evaluator Agent │──── quality < 0.7 → loop back ────────────┘
└─────────────────┘
         │
         ▼
   Final Answer → React UI
```

**Agents** (`app/agents/nodes/`):

| Agent | Role |
|-------|------|
| Orchestrator | Entry point: validates query, routes, manages iteration loop |
| Refiner | Rewrites user query for research-assistant context |
| Intent | Classifies intent (Why/How/When) and domain |
| Decomposer | Breaks query into focused sub-questions |
| Aggregator | Fans out to external APIs, merges results |
| Reasoning | RAG retrieval + LLM synthesis + visualization generation |
| Evaluator | Quality gate (0–1 score); triggers loop-back if < 0.7 |

---

## Paper Q&A Mode

```
PDF / TXT Upload
      │
      ▼
┌──────────────────────────────────────────────────────────┐
│                    FastAPI  /upload-paper                 │
│  PyPDF2 text extraction → chunk → embed → Qdrant         │
│  Returns: session_id  (scopes all subsequent calls)       │
└──────────────────────────┬───────────────────────────────┘
                           │
          ┌────────────────┼────────────────────────────┐
          ▼                ▼                            ▼
  /paper/summarize   /paper/teach              /paper/visualize
  PaperSummarizerAgent  PaperTeacherAgent      PaperVisualizerAgent
          │                │                            │
          ▼                ▼                            ▼
  Rich summary       Chapter lesson plan        concept_map (React Flow)
  + key concepts     + analogies                method_flow (React Flow)
  + section          + key takeaways            charts (Recharts)
  breakdown          + synthesis
  + core innovation

                    /paper/ask
                    PaperQAAgent
                          │
               ┌──────────┴──────────┐
               ▼                     ▼
       Qdrant RAG search    arXiv + Semantic Scholar
       (session-scoped)     (concurrent async fetch)
               └──────────┬──────────┘
                           ▼
                  LLM answer + follow_up_questions
```

**Paper Agents** (`app/agents/`):

| Agent | Output |
|-------|--------|
| `PaperSummarizerAgent` | `title, authors, domain, technical_depth, core_innovation, tldr, abstract_summary, section_breakdown[], key_concepts[], methodology, key_results, limitations, future_work, prior_work_comparison` |
| `PaperTeacherAgent` | `lesson_title, big_picture, prerequisite_knowledge, chapters[]{number, title, explanation, analogy, key_takeaway}, how_it_all_fits, paper_in_one_sentence` |
| `PaperQAAgent` | `answer, paper_evidence[], related_papers[], confidence, follow_up_questions[], rag_chunks_used, external_papers_found` |
| `PaperVisualizerAgent` | `concept_map{nodes, edges}, method_flow{nodes, edges}, charts[]{type, title, data}` |

---

## Vector Database — Qdrant

- **Mode**: in-memory (`:memory:`) — no Docker required for local dev
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs locally)
- **Session scoping**: every chunk tagged with `session_id` payload field
- **Search**: `client.query_points()` with `FieldCondition` filter on `session_id`
- **Cleanup**: `DELETE /paper/session/{session_id}` calls `FilterSelector` delete
- **Session TTL**: `SESSION_MAX_AGE_HOURS` (default 2 h), enforced by `/paper/session/cleanup`

---

## LLM Provider

| Setting | Value |
|---------|-------|
| Provider | Groq (`langchain-groq`) |
| Model | `openai/gpt-oss-120b` |
| Temperature | `1.0` |
| Max tokens | `4000` (Groq free tier: ~8000 TPM) |
| Fallback | Set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` |

---

## Folder Structure

```
├── app/
│   ├── agents/
│   │   ├── nodes/              # Research pipeline agents (7)
│   │   │   ├── orchestrator.py
│   │   │   ├── refiner.py
│   │   │   ├── intent_agent.py
│   │   │   ├── decomposer.py
│   │   │   ├── aggregator.py
│   │   │   ├── reasoning.py
│   │   │   └── evaluator.py
│   │   ├── paper_summarizer.py # Rich structured summary
│   │   ├── paper_teacher.py    # Guided chapter lesson plan
│   │   ├── paper_qa.py         # RAG Q&A + follow-up questions
│   │   ├── paper_visualizer.py # Concept map / flow / charts
│   │   └── base.py             # BaseAgent (call_llm, system_prompt)
│   ├── api/__init__.py         # All FastAPI routes + Pydantic schemas
│   ├── graph/__init__.py       # LangGraph pipeline definition
│   ├── knowledge_base/         # Qdrant client + embedding + session store
│   ├── llm/__init__.py         # LLM factory (Groq / OpenAI)
│   ├── config.py               # Pydantic Settings (env-driven)
│   ├── main.py                 # FastAPI app + CORS + lifespan
│   ├── state/__init__.py       # ResearchState typed dataclass
│   └── utils/                  # logger, exceptions, helpers, constants
│
├── frontend/src/
│   ├── components/
│   │   ├── PaperMode.jsx       # Upload → processing → ready state machine
│   │   ├── PaperTeacher.jsx    # Stepped lesson UI (chapters + nav)
│   │   ├── ConceptCards.jsx    # Clickable concept glossary grid
│   │   ├── PaperVisualization.jsx  # 3-tab React Flow + Recharts panel
│   │   └── ...                 # Research mode components
│   ├── services/api.js         # Axios API layer
│   └── styles/global.css       # Design system (dark theme, all components)
│
├── requirements.txt
├── .env                        # LLM + Qdrant + embedding config
└── .claude/launch.json         # Dev server definitions
```

---

## API Reference

### Research Mode

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/research` | Run full pipeline (sync) |
| POST | `/api/research/stream` | SSE — per-agent events |
| GET | `/api/research/{id}` | Poll cached result |
| POST | `/api/upload-paper` | Upload paper for Research mode |
| GET | `/api/health` | Health + KB stats |
| GET | `/api/graph-topology` | Pipeline node/edge metadata |

### Paper Q&A Mode

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload-paper` | Extract text, embed into Qdrant, return `session_id` |
| POST | `/api/paper/summarize` | Rich structured summary (key concepts, sections, etc.) |
| POST | `/api/paper/teach` | Guided lesson plan (chapters + analogies + takeaways) |
| POST | `/api/paper/ask` | RAG Q&A + external search + follow-up suggestions |
| POST | `/api/paper/visualize` | Concept map, method flow, results charts |
| DELETE | `/api/paper/session/{id}` | Free Qdrant vectors for session |
| DELETE | `/api/paper/session/cleanup` | Delete all sessions older than TTL |

---

## Environment Variables

```env
# LLM
LLM_PROVIDER=groq               # groq | openai
GROQ_API_KEY=gsk_...
LLM_MODEL=openai/gpt-oss-120b
LLM_TEMPERATURE=1.0
LLM_MAX_TOKENS=4000

# Vector DB
QDRANT_URL=:memory:             # :memory: or http://localhost:6333
QDRANT_COLLECTION=paper_chunks
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Sessions
SESSION_MAX_AGE_HOURS=2.0
```

---

## Quick Start

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY
venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev            # http://localhost:3000
# Swagger: http://localhost:8000/docs
```
