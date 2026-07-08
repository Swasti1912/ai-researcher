"""
External Research API Adapters.

Async functions that query arXiv (XML), Semantic Scholar (JSON),
and CrossRef (JSON).  All return normalised dicts.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict
from urllib.parse import quote_plus

import httpx

from app.config import get_settings
from app.utils.exceptions import ExternalAPIError
from app.utils.helpers import truncate
from app.utils.logger import get_logger

_log = get_logger(__name__)
_TIMEOUT = 25.0


async def fetch_arxiv(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search arXiv.

    Args:
        query:       Free-text search string.
        max_results: Maximum papers.

    Returns:
        ``{"papers": [{"title", "summary", "url", "authors"}]}``

    Raises:
        ExternalAPIError: On HTTP or parse failure.
    """
    url = (
        f"{get_settings().arxiv_base_url}?"
        f"search_query=all:{quote_plus(query)}&start=0"
        f"&max_results={max_results}&sortBy=relevance"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(url)
            r.raise_for_status()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(r.text)
        papers = []
        for e in root.findall("a:entry", ns):
            title = (e.findtext("a:title", "", ns) or "").strip().replace("\n", " ")
            summary = (e.findtext("a:summary", "", ns) or "").strip().replace("\n", " ")
            authors = [a.findtext("a:name", "", ns) for a in e.findall("a:author", ns)]
            link = ""
            for lk in e.findall("a:link", ns):
                if lk.get("title") == "pdf" or lk.get("type") == "text/html":
                    link = lk.get("href", ""); break
            papers.append({"title": title, "summary": truncate(summary, 400), "url": link, "authors": authors[:4]})
        return {"papers": papers}
    except Exception as exc:
        raise ExternalAPIError("arxiv", str(exc)) from exc


async def fetch_semantic_scholar(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search Semantic Scholar.

    Returns:
        ``{"papers": [{"title", "abstract", "year", "citations", "url"}]}``
    """
    params = {"query": query, "limit": limit, "fields": "title,abstract,year,citationCount,url"}
    headers = {}
    key = get_settings().semantic_scholar_api_key
    if key:
        headers["x-api-key"] = key
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get("https://api.semanticscholar.org/graph/v1/paper/search", params=params, headers=headers)
            r.raise_for_status()
            d = r.json()
        return {"papers": [
            {"title": p.get("title", ""), "abstract": truncate(p.get("abstract") or "", 400),
             "year": p.get("year"), "citations": p.get("citationCount", 0), "url": p.get("url", "")}
            for p in d.get("data", [])
        ]}
    except Exception as exc:
        raise ExternalAPIError("semantic_scholar", str(exc)) from exc


async def fetch_crossref(query: str, rows: int = 5) -> Dict[str, Any]:
    """
    Search CrossRef.

    Returns:
        ``{"works": [{"title", "doi", "publisher", "type", "year"}]}``
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{get_settings().crossref_base_url}/works", params={"query": query, "rows": rows})
            r.raise_for_status()
            d = r.json()
        works = []
        for item in d.get("message", {}).get("items", []):
            titles = item.get("title", ["Untitled"])
            year = None
            dp = item.get("published-print") or item.get("published-online")
            if dp and dp.get("date-parts") and dp["date-parts"][0]:
                year = dp["date-parts"][0][0]
            works.append({"title": titles[0] if titles else "Untitled", "doi": item.get("DOI", ""),
                          "publisher": item.get("publisher", ""), "type": item.get("type", ""), "year": year})
        return {"works": works}
    except Exception as exc:
        raise ExternalAPIError("crossref", str(exc)) from exc


API_REGISTRY = {
    "arxiv": fetch_arxiv,
    "semantic_scholar": fetch_semantic_scholar,
    "crossref": fetch_crossref,
}
