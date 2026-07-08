"""
PDF extraction with PyMuPDF (fitz).

Isolated here so the knowledge base stays importable without fitz for
plain-text (.txt/.md) ingestion. Produces page-aware text plus embedded
figures/tables with best-effort captions.

    from app.knowledge_base.pdf_extract import extract_pdf
    result = extract_pdf(pdf_bytes)
    # -> {"pages": [{"page_number": 1, "text": ...}], "figures": [...], "page_count": N}

Each figure: {"fig_id", "page", "caption", "png": bytes|None, "kind": "figure"|"table"}.
Always failure-tolerant: on any error, falls back to single-page text so upload never breaks.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

_log = get_logger(__name__)

_FIG_RE = re.compile(r"^(figure|fig\.?|table)\s*\d+", re.IGNORECASE)
_MIN_DIM = 50            # px — drop icons/rules/logos
_MIN_PNG_BYTES = 2048    # drop tiny images
_MAX_FIGURES = 30        # bound memory per paper
_MAX_CAPTION = 300


def extract_pdf(content: bytes) -> Dict[str, Any]:
    """Extract page text + figures from PDF bytes. Never raises."""
    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover
        _log.warning("PyMuPDF unavailable, using text fallback", extra={"err": str(exc)})
        return _fallback(content)

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        _log.warning("fitz.open failed, using text fallback", extra={"err": str(exc)})
        return _fallback(content)

    pages: List[Dict[str, Any]] = []
    figures: List[Dict[str, Any]] = []
    try:
        for pno in range(len(doc)):
            page = doc[pno]
            try:
                text = page.get_text("text") or ""
            except Exception:
                text = ""
            pages.append({"page_number": pno + 1, "text": text})

            if len(figures) < _MAX_FIGURES:
                captions = _page_captions(page)
                _extract_page_figures(fitz, doc, page, pno + 1, captions, figures)
        page_count = len(doc)
    except Exception as exc:
        _log.warning("PDF extract error, partial result", extra={"err": str(exc)})
        page_count = len(pages) or 1
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if not any(p["text"].strip() for p in pages):
        # No extractable text (scanned PDF) — keep pages for the viewer but
        # let caller decide; still return so /paper/pdf works.
        _log.info("PDF had no extractable text (possibly scanned)")

    return {"pages": pages or [{"page_number": 1, "text": ""}],
            "figures": figures[:_MAX_FIGURES],
            "page_count": page_count}


# ── caption heuristics ────────────────────────────────────────────────────────

def _page_captions(page) -> List[Dict[str, Any]]:
    caps: List[Dict[str, Any]] = []
    try:
        d = page.get_text("dict")
    except Exception:
        return caps
    for block in d.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue
        txt = " ".join(
            span.get("text", "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        ).strip()
        if txt and _FIG_RE.match(txt):
            caps.append({
                "text": txt[:_MAX_CAPTION],
                "bbox": tuple(block.get("bbox") or ()),
                "kind": "table" if txt.lower().startswith("table") else "figure",
            })
    return caps


def _nearest_caption_idx(bbox: Optional[Tuple], captions: List[Dict], used: set) -> Optional[int]:
    """Index of the nearest unused caption to an image bbox (captions sit near figures)."""
    best, best_d = None, 1e18
    for i, c in enumerate(captions):
        if i in used:
            continue
        cb = c.get("bbox")
        if bbox and cb and len(cb) >= 4 and len(bbox) >= 4:
            d = abs(cb[1] - bbox[3])  # caption-top to image-bottom
            if d < best_d:
                best_d, best = d, i
        elif best is None:
            best = i
    return best


def _extract_page_figures(fitz, doc, page, page_no: int, captions: List[Dict], figures: List[Dict]) -> None:
    used: set = set()
    seen_xref: set = set()
    try:
        imgs = page.get_images(full=True)
    except Exception:
        imgs = []

    for idx, img in enumerate(imgs):
        if len(figures) >= _MAX_FIGURES:
            return
        xref = img[0]
        if xref in seen_xref:
            continue
        seen_xref.add(xref)

        png = _render_image_png(fitz, doc, xref)
        if png is None:
            continue

        # locate caption
        bbox = None
        try:
            rects = page.get_image_rects(xref)
            if rects:
                bbox = tuple(rects[0])
        except Exception:
            bbox = None
        cap_i = _nearest_caption_idx(bbox, captions, used)
        caption, kind = "", "figure"
        if cap_i is not None:
            caption = captions[cap_i]["text"]
            kind = captions[cap_i]["kind"]
            used.add(cap_i)

        figures.append({
            "fig_id": f"fig-p{page_no}-{idx}",
            "page": page_no,
            "caption": caption,
            "png": png,
            "kind": kind,
        })

    # Unmatched "Table N" captions → caption-only cards (tables are often vector/text)
    for i, c in enumerate(captions):
        if len(figures) >= _MAX_FIGURES:
            return
        if i in used or c["kind"] != "table":
            continue
        figures.append({
            "fig_id": f"tab-p{page_no}-{i}",
            "page": page_no,
            "caption": c["text"],
            "png": None,
            "kind": "table",
        })


def _render_image_png(fitz, doc, xref: int) -> Optional[bytes]:
    try:
        pix = fitz.Pixmap(doc, xref)
    except Exception:
        return None
    try:
        if pix.width < _MIN_DIM or pix.height < _MIN_DIM:
            return None
        # Convert CMYK / alpha to RGB so PNG encodes correctly
        if pix.alpha or (pix.n - (1 if pix.alpha else 0)) >= 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        png = pix.tobytes("png")
    except Exception:
        return None
    finally:
        pix = None
    if not png or len(png) < _MIN_PNG_BYTES:
        return None
    return png


# ── fallback ──────────────────────────────────────────────────────────────────

def _fallback(content: bytes) -> Dict[str, Any]:
    text = ""
    try:
        import PyPDF2
        text = "\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(io.BytesIO(content)).pages)
    except Exception:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
    return {"pages": [{"page_number": 1, "text": text}], "figures": [], "page_count": 1}
