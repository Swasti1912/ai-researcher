# ── AI Researcher — Hugging Face Spaces (Docker SDK) ──────────────────────────
# Multi-stage build:
#   Stage 1 (node)   → compiles the React frontend to static files
#   Stage 2 (python) → runs FastAPI, which serves both /api and the built UI
#
# HF Spaces requirements honoured here:
#   - app must listen on port 7860
#   - container runs as a non-root user → all writable paths live in /tmp

# ── Stage 1: build frontend ───────────────────────────────────────────────────
FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: backend ──────────────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /code

# git is required by HF Spaces "Dev Mode" (it injects `git config` + openvscode
# stages on top of this image). The slim base omits it, which fails the build
# with `git: not found` when Dev Mode is enabled. Harmless when it's off.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# CPU-only PyTorch first — an order of magnitude smaller than the default
# CUDA build and all sentence-transformers needs on Spaces' free CPU tier.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model at build time so cold starts are fast
# and the Space works even if hf.co is briefly unreachable at runtime.
ENV HF_HOME=/tmp/hf
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY app/ app/
COPY --from=ui /ui/dist frontend/dist

# Writable dirs for the non-root runtime user (SQLite DB, PDFs, Qdrant vectors).
# NOTE: /tmp is ephemeral on free Spaces — the library resets on restart.
ENV DATA_DIR=/tmp/data \
    PORT=7860
RUN mkdir -p /tmp/data && chmod 777 /tmp/data /tmp/hf

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
