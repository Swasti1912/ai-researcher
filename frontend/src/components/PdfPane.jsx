import React, {
  useRef, useState, useEffect, useCallback,
} from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import { FileWarning, Loader2 } from 'lucide-react';

// Worker must match react-pdf's bundled pdfjs version (pinned in package.json).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

const normalize = (s) =>
  (s || '').toLowerCase().replace(/\s+/g, ' ').replace(/[^\w\s]/g, ' ').replace(/\s+/g, ' ').trim();

/**
 * PDF viewer that exposes an imperative API through `apiRef` (a plain ref
 * object) — this works reliably through React.lazy, unlike forwardRef:
 *   apiRef.current.scrollToPage(n)
 *   apiRef.current.scrollToText(query, { page })  — scrolls + flashes a highlight
 *
 * `file` = a browser File/Blob (uploads); if absent, loads the URL for `sessionId`.
 */
export default function PdfPane({ file, sessionId, apiRef }) {
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(0);
  const [status, setStatus] = useState('loading'); // loading | ready | error | empty
  const scrollRef = useRef(null);
  const pageRefs = useRef({}); // pageNumber -> DOM node

  // Resolve the source: File (uploads) or URL (deep-dive / stored bytes)
  const source = file || (sessionId ? `/api/paper/pdf/${sessionId}` : null);

  // Track container width for responsive page sizing
  useEffect(() => {
    if (!scrollRef.current) return;
    const el = scrollRef.current;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth - 24));
    ro.observe(el);
    setWidth(el.clientWidth - 24);
    return () => ro.disconnect();
  }, []);

  const onLoad = useCallback(({ numPages }) => {
    setNumPages(numPages);
    setStatus('ready');
  }, []);

  const onError = useCallback(() => setStatus('error'), []);

  // ── imperative API ──────────────────────────────────────────────────
  const scrollToPage = useCallback((n) => {
    const node = pageRefs.current[n];
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    const words = norm.split(' ');
    const probe = words.slice(0, Math.min(10, words.length)).join(' ');

    const searchPages = opts.page
      ? [opts.page]
      : Array.from({ length: numPages }, (_, i) => i + 1);

    const tryFind = (attempt = 0) => {
      for (const p of searchPages) {
        const pageNode = pageRefs.current[p];
        if (!pageNode) continue;
        const layer = pageNode.querySelector('.react-pdf__Page__textContent');
        if (!layer) continue;
        const spans = Array.from(layer.querySelectorAll('span'));
        if (!spans.length) continue;

        // Concatenate span text with index map
        let concat = '';
        const idx = []; // [{start, end, span}]
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
      // Text layers may still be rendering — retry briefly
      if (attempt < 6) { setTimeout(() => tryFind(attempt + 1), 250); return false; }
      // Fallback: page-level scroll + flash
      const p = opts.page || searchPages[0];
      scrollToPage(p); flashPage(p);
      return false;
    };

    if (opts.page) scrollToPage(opts.page);
    setTimeout(() => tryFind(0), opts.page ? 350 : 50);
  }, [numPages, scrollToPage, flashPage]);

  // Expose the imperative API via the passed ref object (lazy-safe)
  useEffect(() => {
    if (!apiRef) return undefined;
    apiRef.current = { scrollToPage, scrollToText };
    return () => { apiRef.current = null; };
  }, [apiRef, scrollToPage, scrollToText]);

  if (!source) {
    return <div className="pdf-empty"><FileWarning size={22} /> No PDF available for this paper.</div>;
  }

  return (
    <div className="pdf-pane" ref={scrollRef}>
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
            <div className="pdf-page-num">{p}</div>
          </div>
        ))}
      </Document>
    </div>
  );
}
