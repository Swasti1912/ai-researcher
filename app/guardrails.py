"""
Lightweight content guardrails for a public deployment.

A single cheap LLM classification (via the normal provider chain) decides whether
an input should be processed. Two concerns:
  • Safety   — block harmful / hateful / sexual / illegal / harassing content.
  • Relevance — this is an academic paper assistant; block inputs that are
    clearly unrelated to research / scientific papers.

Fail-OPEN: if the check errors or can't parse, we allow the request through —
a flaky guardrail must never block legitimate users.
"""
from __future__ import annotations

from typing import Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import make_agent_llm
from app.utils.helpers import safe_json_parse
from app.utils.logger import get_logger

_log = get_logger(__name__)

_PROMPTS = {
    "query": (
        "You are the safety + relevance gate for an academic research assistant that "
        "searches scientific literature. Decide whether to process the user's QUERY.\n"
        "BLOCK it if: it is harmful, hateful, sexual, harassing, or asks for illegal/dangerous "
        "instructions; OR it is clearly not a research/academic/technical question "
        "(e.g. chit-chat, personal advice, weather).\n"
    ),
    "question": (
        "You are the safety gate for an assistant answering questions about an uploaded "
        "research paper. Decide whether to process the user's QUESTION.\n"
        "BLOCK it if: it is harmful, hateful, sexual, harassing, or requests illegal/dangerous "
        "instructions. Allow any genuine question about the paper or its topic — even if broad.\n"
    ),
    "document": (
        "You are the intake gate for an academic paper reader. Decide whether to accept this "
        "DOCUMENT excerpt.\n"
        "BLOCK it if: it contains harmful/hateful/sexual/illegal content; OR it is clearly not "
        "an academic / scientific / technical paper or report (e.g. an invoice, resume, contract, "
        "marketing flyer, or random text).\n"
    ),
}

_SUFFIX = (
    '\nRespond with ONLY JSON: {"allowed": true|false, "reason": "<one short, friendly '
    'user-facing sentence explaining why, only when blocked>"}'
)

_DEFAULT_MSG = {
    "query": "This doesn't look like a research question I can help with. Try asking about a scientific or technical topic.",
    "question": "I can't help with that request. Please ask something about this paper.",
    "document": "This doesn't look like a research paper, so results may be poor. Try uploading an academic paper or article.",
}


async def screen(text: str, kind: str = "question") -> Tuple[bool, str]:
    """Return (allowed, user_message). Fails open (allowed=True) on any error."""
    if not text or not text.strip():
        return True, ""
    prompt = _PROMPTS.get(kind, _PROMPTS["question"]) + _SUFFIX
    try:
        llm = make_agent_llm("guardrail", temperature=0.0, max_tokens=120)
        resp = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=text[:4000]),
        ])
        data = safe_json_parse(resp.content)
        if not isinstance(data, dict) or "allowed" not in data:
            return True, ""                       # unparseable → allow
        allowed = bool(data.get("allowed"))
        reason = (data.get("reason") or "").strip() or _DEFAULT_MSG.get(kind, "")
        if not allowed:
            _log.info("guardrail blocked", extra={"kind": kind, "reason": reason})
        return allowed, ("" if allowed else reason)
    except Exception as exc:  # noqa: BLE001 — never block on a guardrail failure
        _log.warning("guardrail check failed (allowing)", extra={"err": str(exc)})
        return True, ""
