---
title: AI Researcher
emoji: 📖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Read papers deeply — AI summary, lessons, PDF-linked Q&A
---

# AI Researcher – Multi-Agent Research Assistant

Production-grade agentic pipeline built with **LangGraph**, **FastAPI**, and **React**.

## Architecture (matches diagram exactly)

```
User Query / Paper
       │
       ▼
┌────────────────┐
│  Orchestrator   │ ◄──────────────────────────────────────┐
└───────┬────────┘                                         │
        ▼                                                   │
┌────────────────┐                                         │
│ Refiner Agent  │  Modify prompt for AI Researcher ctx    │
└───────┬────────┘                                         │
        ▼                                                   │
┌────────────────┐                                         │
│  Intent Agent  │  Why? How? When? + domain               │
└───────┬────────┘                                         │
        ▼                                                   │
┌────────────────┐                                         │
│Decomposer Agent│  Break into sub-questions               │
└───────┬────────┘                                         │
        ▼           ┌─────────────────┐                    │
┌────────────────┐  │ arXiv / S2 / CR │                    │
│Aggregator Agent│◄►│ External APIs   │                    │
└───────┬────────┘  └─────────────────┘                    │
        ▼           ┌─────────────────┐                    │
┌────────────────┐  │ Knowledge Base  │                    │
│Reasoning Agent │◄►│ (RAG)           │                    │
└───────┬────────┘  └─────────────────┘                    │
        ▼                                                   │
┌────────────────┐                                         │
│Evaluator Agent │──── Loop back if quality < 0.7 ─────────┘
└────────────────┘
        │
        ▼
   Final Answer → React UI
```

## Folder Structure

```
backend/
├── app/
│   ├── agents/nodes/        # 7 agent implementations + base class
│   ├── graph/               # LangGraph workflow definition
│   ├── state/               # Typed state dataclass + Pydantic models
│   ├── llm/                 # LLM provider factory
│   ├── utils/               # logger, exceptions, constants, helpers
│   ├── api/                 # FastAPI routes (sync + SSE streaming)
│   ├── services/            # External API adapters (arXiv, S2, CrossRef)
│   ├── knowledge_base/      # RAG module
│   ├── config.py            # Pydantic Settings
│   └── main.py              # FastAPI entry point
│
frontend/
├── src/
│   ├── components/          # Header, QueryInput, Pipeline, Results, Sidebar, Viz
│   ├── services/            # API service layer
│   └── styles/              # CSS
```

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev
# UI: http://localhost:3000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/research | Run full pipeline (sync) |
| POST | /api/research/stream | SSE streaming per-agent events |
| POST | /api/upload-paper | Upload PDF/text → KB |
| GET | /api/research/{id} | Poll result |
| GET | /api/health | Health check |
| GET | /api/graph-topology | Pipeline metadata for UI |
