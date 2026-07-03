import React, {
  useRef, useState, useEffect, useCallback,
} from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import { FileWarning, Loader2, MessageSquare, Highlighter, Trash2 } from 'lucide-react';

// Worker must match react-pdf's bundled pdfjs version (pinned in package.json).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const HL_COLORS = ['yellow', 'green', 'pink', 'blue'];

const normalize = (s) =>
  (s || '').toLowerCase().replace(/\s+/g, ' ').replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();

/**
 * PDF viewer with an imperative API via `apiRef` (lazy-safe object prop):
 *   apiRef.current.scrollToPage(n)
 *   apiRef.current.scrollToText(query, { page })
 *   apiRef.current.scrollToHighlight(id)
 *
 * Highlighting: select text → floating toolbar → onCreateHighlight. Saved
 * highlights render as normalized (0..1) overlays with a clickable note marker.
 */
export default function PdfPane({
  file, sessionId, apiRef,
  highlights = [], onCreateHighlight, onUpdateNote, onDeleteHighlight,
}) {
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(0);
  const [status, setStatus] = useState('loading');
  const [pending, setPending] = useState(null);   // {page, rects, quote, vx, vy}
  const [noteFor, setNoteFor] = useState(null);    // {id, vx, vy}
  const [draftNote, setDraftNote] = useState('');
  const scrollRef = useRef(null);
  const pageRefs = useRef({});

  const source = file || (sessionId ? `/api/paper/pdf/${sessionId}` : null);

  useEffect(() => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth - 24));
    ro.observe(el);
    setWidth(el.clientWidth - 24);
    return () => ro.disconnect();
  }, []);

  const onLoad = useCallback(({ numPages }) => { setNumPages(numPages); setStatus('ready'); }, []);
  const onError = useCallback(() => setStatus('error'), []);

  // ── scroll / find ───────────────────────────────────────────────────
  const scrollToPage = useCallback((n) => {
    pageRefs.current[n]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);
  const flashPage = useCallback((n) => {
    const node = pageRefs.current[n];
    if (!node) return;
    node.classList.add('pdf-page-flash');
    setTimeout(() => node.classList.remove('pdf-page-flash'), 1600);
  }, []);

  const scrollToText = useCallback((query, opts = {}) => {
    const norm = normalize(query);
    if (!norm) return;
    const probe = norm.split(' ').slice(0, 10).join(' ');
    const searchPages = opts.page ? [opts.page] : Array.from({ length: numPages }, (_, i) => i + 1);
    const tryFind = (attempt = 0) => {
      for (const p of searchPages) {
        const layer = pageRefs.current[p]?.querySelector('.react-pdf__Page__textContent');
        if (!layer) continue;
        const spans = Array.from(layer.querySelectorAll('span'));
        if (!spans.length) continue;
        let concat = ''; const idx = [];
        for (const span of spans) {
          const t = normalize(span.textContent) + ' ';
          if (!t.trim()) { concat += ' '; continue; }
          idx.push({ start: concat.length, end: concat.length + t.length, span });
          concat += t;
        }
        const hit = concat.indexOf(probe);
        if (hit >= 0) {
          const matched = idx.filter((r) => r.end > hit && r.start < hit + probe.length);
          if (matched.length) {
            matched.forEach((r) => r.span.classList.add('pdf-hl'));
            matched[0].span.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => matched.forEach((r) => r.span.classList.remove('pdf-hl')), 2200);
            return true;
          }
        }
      }
      if (attempt < 6) { setTimeout(() => tryFind(attempt + 1), 250); return false; }
      const p = opts.page || searchPages[0];
      scrollToPage(p); flashPage(p);
      return false;
    };
    if (opts.page) scrollToPage(opts.page);
    setTimeout(() => tryFind(0), opts.page ? 350 : 50);
  }, [numPages, scrollToPage, flashPage]);

  const scrollToHighlight = useCallback((id) => {
    const h = highlights.find((x) => x.id === id);
    if (!h) return;
    scrollToPage(h.page);
    setTimeout(() => {
      const rect = pageRefs.current[h.page]?.querySelector(`[data-hl="${id}"]`);
      if (rect) {
        rect.scrollIntoView({ behavior: 'smooth', block: 'center' });
        rect.classList.add('pdf-hl-pulse');
        setTimeout(() => rect.classList.remove('pdf-hl-pulse'), 1500);
      }
    }, 420);
  }, [highlights, scrollToPage]);

  useEffect(() => {
    if (!apiRef) return undefined;
    apiRef.current = { scrollToPage, scrollToText, scrollToHighlight };
    return () => { apiRef.current = null; };
  }, [apiRef, scrollToPage, scrollToText, scrollToHighlight]);

  // ── highlight capture ───────────────────────────────────────────────
  const onMouseUp = useCallback(() => {
    if (!onCreateHighlight) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
    const range = sel.getRangeAt(0);
    const wrapOf = (node) => (node.nodeType === 1 ? node : node.parentElement)?.closest?.('.pdf-page-wrap');
    const startWrap = wrapOf(range.startContainer);
    const endWrap = wrapOf(range.endContainer);
    if (!startWrap || startWrap !== endWrap) return;       // single page only
    const page = Number(startWrap.dataset.page);
    const box = startWrap.getBoundingClientRect();
    const rects = Array.from(range.getClientRects())
      .filter((r) => r.width > 1 && r.height > 1)
      .map((r) => ({
        x: (r.left - box.left) / box.width, y: (r.top - box.top) / box.height,
        w: r.width / box.width, h: r.height / box.height,
      }));
    if (!rects.length) return;
    const gr = range.getBoundingClientRect();
    setPending({ page, rects, quote: sel.toString().trim(), vx: gr.left, vy: gr.top });
  }, [onCreateHighlight]);

  const confirmHighlight = (color) => {
    if (!pending) return;
    onCreateHighlight?.({ page: pending.page, rects: pending.rects, quote: pending.quote, color, note: '' });
    window.getSelection()?.removeAllRanges();
    setPending(null);
  };

  const openNote = (h, e) => {
    const r = e.currentTarget.getBoundingClientRect();
    setDraftNote(h.note || '');
    setNoteFor({ id: h.id, vx: r.left, vy: r.bottom + 6 });
  };
  const saveNote = () => { if (noteFor) { onUpdateNote?.(noteFor.id, draftNote); setNoteFor(null); } };

  if (!source) {
    return <div className="pdf-empty"><FileWarning size={22} /> No PDF available for this paper.</div>;
  }

  return (
    <div className="pdf-pane" ref={scrollRef} onMouseUp={onMouseUp}>
      <Document
        file={source}
        onLoadSuccess={onLoad}
        onLoadError={onError}
        onSourceError={onError}
        loading={<div className="pdf-loading"><Loader2 size={18} className="spin-svg" /> Loading PDF…</div>}
        error={<div className="pdf-empty"><FileWarning size={22} /> Couldn't render this PDF.</div>}
        noData={<div className="pdf-empty"><FileWarning size={22} /> No PDF available.</div>}
      >
        {status === 'ready' && width > 0 && Array.from({ length: numPages }, (_, i) => i + 1).map((p) => (
          <div key={p} className="pdf-page-wrap" data-page={p} ref={(el) => { pageRefs.current[p] = el; }}>
            <Page
              pageNumber={p}
              width={width}
              renderTextLayer
              renderAnnotationLayer={false}
              loading={<div className="pdf-page-ph" style={{ height: width * 1.29 }} />}
            />
            {/* highlight overlays for this page */}
            <div className="pdf-hl-layer">
              {highlights.filter((h) => h.page === p).map((h) => (
                <React.Fragment key={h.id}>
                  {(h.rects || []).map((r, i) => (
                    <div key={i} data-hl={h.id} className={`pdf-hl-rect hl-${h.color || 'yellow'}`}
                      style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` }} />
                  ))}
                  {h.rects?.[0] && (
                    <button className={`pdf-hl-marker ${h.note ? 'has-note' : ''}`}
                      style={{ left: `${h.rects[0].x * 100}%`, top: `${h.rects[0].y * 100}%` }}
                      title={h.note || 'Add a note'} onClick={(e) => openNote(h, e)}>
                      <MessageSquare size={10} />
                    </button>
                  )}
                </React.Fragment>
              ))}
            </div>
            <div className="pdf-page-num">{p}</div>
          </div>
        ))}
      </Document>

      {/* floating create toolbar */}
      {pending && (
        <div className="pdf-hl-toolbar" style={{ left: pending.vx, top: pending.vy - 46 }}
          onMouseDown={(e) => e.preventDefault()}>
          <Highlighter size={13} style={{ color: 'var(--t2)' }} />
          {HL_COLORS.map((c) => (
            <button key={c} className={`hl-swatch hl-${c}`} title={`Highlight ${c}`} onClick={() => confirmHighlight(c)} />
          ))}
          <button className="hl-cancel" onClick={() => { setPending(null); window.getSelection()?.removeAllRanges(); }}>✕</button>
        </div>
      )}

      {/* note popover */}
      {noteFor && (
        <div className="pdf-hl-popover" style={{ left: noteFor.vx, top: noteFor.vy }}
          onMouseDown={(e) => e.stopPropagation()}>
          <textarea autoFocus placeholder="Add a note…" value={draftNote}
            onChange={(e) => setDraftNote(e.target.value)} />
          <div className="pdf-hl-popover-row">
            <button className="hl-del-btn" onClick={() => { onDeleteHighlight?.(noteFor.id); setNoteFor(null); }}>
              <Trash2 size={12} /> Delete
            </button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-g btn-sm" onClick={() => setNoteFor(null)}>Cancel</button>
            <button className="btn btn-p btn-sm" onClick={saveNote}>Save</button>
          </div>
        </div>
      )}
    </div>
  );
}
