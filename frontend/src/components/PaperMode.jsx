import React, { useState, useRef, useEffect, lazy, Suspense } from 'react';
import { FileText, UploadCloud, AlertTriangle, ArrowUp, GraduationCap, Map, RotateCcw, ScrollText, PanelsTopLeft, ExternalLink, ArrowLeft } from 'lucide-react';
import { uploadPaper, summarizePaper, askPaper, deleteSession, visualizePaper, teachPaper, fetchPaperFromUrl,
  getConfig, getPaperMeta, getPaperChat, getHighlights, createHighlight, updateHighlightNote, deleteHighlight } from '../services/api';
import ConceptCards from './ConceptCards';
import PaperTeacher from './PaperTeacher';
import FiguresStrip from './FiguresStrip';
import SectionBreakdown from './SectionBreakdown';
import Library from './Library';
import HighlightsPanel from './HighlightsPanel';
import Markdown from './Markdown';

// Lazy-loaded: pulls in Mermaid + Recharts only when a visualization is opened.
const PaperVisualization = lazy(() => import('./PaperVisualization'));
const VizFallback = () => (
  <div className="viz-panel" style={{ padding: 40, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, color: 'var(--t2)' }}>
    <span className="spin" /> Loading visualizations…
  </div>
);

// Lazy-loaded: pulls in pdf.js only when a paper is open in the reader.
const PdfPane = lazy(() => import('./PdfPane'));
const PdfFallback = () => (
  <div className="pdf-loading"><span className="spin" /> Loading PDF viewer…</div>
);

// Processing steps shown while a paper is being ingested
const PROC_STEPS = [
  { key: 'parse',   label: 'Extracting text from document',      sub: '' },
  { key: 'embed',   label: 'Chunking & building semantic index',  sub: '' },
  { key: 'summary', label: 'AI summarization',                    sub: 'Reading paper deeply with Llama 3.3 70B' },
  { key: 'ready',   label: 'Ready for Q&A',                       sub: '' },
];

const DEPTH_COLORS = { beginner: 'bdg-g', intermediate: 'bdg-o', expert: 'bdg-r' };

export default function PaperMode({ openRequest = null, onConsumed, onBack }) {
  const [phase, setPhase]         = useState('upload'); // upload | processing | ready
  const [sessionId, setSessionId] = useState(null);
  const [libraryEnabled, setLibraryEnabled] = useState(true);  // shared Library/persistence (off in public deploy)
  const [openErr, setOpenErr]     = useState(null);     // { message, url, title } for inaccessible from-URL papers
  const [filename, setFilename]   = useState('');
  const [summary, setSummary]     = useState(null);
  const [procStep, setProcStep]   = useState(null);
  const [doneSteps, setDoneSteps] = useState([]);
  const [procMeta, setProcMeta]   = useState({});
  const [messages, setMessages]   = useState([]);
  const [question, setQuestion]   = useState('');
  const [asking, setAsking]       = useState(false);
  const [uploadErr, setUploadErr] = useState('');
  const [summarizeErr, setSummarizeErr] = useState('');
  const [pendingSummarize, setPendingSummarize] = useState(null); // { sessionId, filename }
  const [askErr, setAskErr]       = useState('');
  const [vizData, setVizData]     = useState(null);
  const [vizLoading, setVizLoading] = useState(false);
  const [vizErr, setVizErr]       = useState('');
  const [sectionsOpen, setSectionsOpen] = useState(false);
  const [teachLesson, setTeachLesson] = useState(null);
  const [teachLoading, setTeachLoading] = useState(false);
  const [teachErr, setTeachErr]   = useState('');
  const [paperFile, setPaperFile] = useState(null);   // browser File for client-side PDF render
  const [hasPdf, setHasPdf]       = useState(false);  // true when a renderable PDF exists
  const [mobileView, setMobileView] = useState('ai'); // 'pdf' | 'ai' (narrow screens)
  const [highlights, setHighlights] = useState([]);   // persisted PDF highlights/notes
  const [libraryKey, setLibraryKey] = useState(0);    // bump to refresh the library list
  const fileRef = useRef();
  const chatRef = useRef();
  const pdfPaneRef = useRef();

  const locateInPdf = (text, page) => pdfPaneRef.current?.scrollToText?.(text, page ? { page } : {});
  const locatePage = (page) => pdfPaneRef.current?.scrollToPage?.(page);

  // ── Highlights (persisted) ────────────────────────────────────────
  const handleCreateHighlight = async ({ page, rects, quote, color = 'yellow', note = '' }) => {
    try {
      const h = await createHighlight(sessionId, { page, rects, quote, color, note });
      setHighlights(prev => [...prev, h]);
    } catch { /* ignore */ }
  };
  const handleUpdateNote = async (id, note) => {
    try {
      const h = await updateHighlightNote(id, note);
      setHighlights(prev => prev.map(x => x.id === id ? h : x));
    } catch { /* ignore */ }
  };
  const handleDeleteHighlight = async (id) => {
    setHighlights(prev => prev.filter(x => x.id !== id));
    try { await deleteHighlight(id); } catch { /* ignore */ }
  };

  // ── Reopen a saved paper from the library ─────────────────────────
  const reopenPaper = async (sid) => {
    setPhase('processing');
    setProcStep('summary'); setDoneSteps(['parse', 'embed']);
    setPaperFile(null); setMessages([]); setHighlights([]); setVizData(null); setTeachLesson(null);
    try {
      const meta = await getPaperMeta(sid);
      setSessionId(sid);
      setFilename(meta.filename || meta.title || 'paper');
      setHasPdf(!!meta.has_pdf && meta.page_count > 0);
      setSummary(meta.summary || null);
      const [chat, hl] = await Promise.all([
        getPaperChat(sid).catch(() => ({ messages: [] })),
        getHighlights(sid).catch(() => ({ highlights: [] })),
      ]);
      setMessages((chat.messages || []).map(m => ({
        role: m.role, content: m.content, evidence: m.evidence || [],
      })));
      setHighlights(hl.highlights || []);
      if (!meta.summary) { await runSummarize(sid, meta.filename); }
      else { setDoneSteps(['parse', 'embed', 'summary', 'ready']); setProcStep(null); setPhase('ready'); }
    } catch (e) {
      setUploadErr('Could not reopen this paper.');
      setPhase('upload');
    }
  };

  // ── Open a paper the parent asked us to (from the research deep-dive) ──
  // A request is either { sid } (already-ingested session) or
  // { url, title, abstract } (fetch + ingest from an external source). Either
  // way we route through reopenPaper, which auto-summarizes a fresh session —
  // so the research "Summarize & visualize" reuses this whole page instead of a
  // parallel modal.
  const openFromRequest = async (req) => {
    if (!req) return;
    setOpenErr(null);
    if (req.sid) { reopenPaper(req.sid); return; }
    if (!req.url) return;

    setPaperFile(null); setMessages([]); setHighlights([]);
    setVizData(null); setTeachLesson(null); setSummary(null);
    setFilename(req.title || 'Fetching paper…');
    setPhase('processing');
    setProcStep('parse'); setDoneSteps([]); setProcMeta({});
    try {
      setProcStep('embed'); setDoneSteps(['parse']);
      const up = await fetchPaperFromUrl(req.url, req.abstract || '', req.title || '');
      setProcMeta({ chunks: up.chunks, chars: up.text_length });
      await reopenPaper(up.session_id);   // loads meta + auto-summarizes
    } catch (e) {
      setOpenErr({
        message: "This paper doesn't have an accessible full text to summarize.",
        url: req.url,
        title: req.title,
      });
      setPhase('upload');
    }
  };

  // Whether this deployment exposes the shared Library / persistence.
  useEffect(() => {
    getConfig().then(c => setLibraryEnabled(c.library_enabled !== false)).catch(() => {});
  }, []);

  const openTokenRef = useRef(null);
  useEffect(() => {
    if (!openRequest || openTokenRef.current === openRequest) return;
    openTokenRef.current = openRequest;
    openFromRequest(openRequest);
    onConsumed?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest]);

  // ── Upload + summarize ────────────────────────────────────────────
  const handleFile = async (file) => {
    if (!file) return;
    setUploadErr('');
    setSummarizeErr('');
    setOpenErr(null);
    setPendingSummarize(null);
    setFilename(file.name);
    setPaperFile(file);           // keep the File so the PDF renders client-side
    setHasPdf(/\.pdf$/i.test(file.name));
    setSummary(null);
    setMessages([]);
    setDoneSteps([]);
    setPhase('processing');

    let uploadedId = null;
    try {
      setProcStep('parse');
      const uploaded = await uploadPaper(file);
      uploadedId = uploaded.session_id;

      // Store session ID immediately so it's available even if summarize fails
      setSessionId(uploaded.session_id);
      setHasPdf((uploaded.page_count || 0) > 0);
      setProcMeta({ chunks: uploaded.chunks, chars: uploaded.text_length });
      setDoneSteps(['parse', 'embed']);

      await runSummarize(uploaded.session_id, file.name);
    } catch (e) {
      // Upload itself failed — clean up any partially-created session
      if (uploadedId) {
        deleteSession(uploadedId).catch(() => {});
        setSessionId(null);
      }
      setUploadErr(e.response?.data?.detail || e.message || 'Upload failed. Please try again.');
      setPhase('upload');
      setProcStep(null);
      setDoneSteps([]);
    }
  };

  // ── Run summarization (separate so it can be retried independently) ──
  const runSummarize = async (sid, fname) => {
    setSummarizeErr('');
    setPendingSummarize(null);
    setProcStep('summary');
    try {
      const sum = await summarizePaper(sid, fname);
      setSummary(sum);
      setDoneSteps(['parse', 'embed', 'summary', 'ready']);
      setProcStep(null);
      setTimeout(() => setPhase('ready'), 600);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || 'Summarization failed.';
      setSummarizeErr(msg);
      setPendingSummarize({ sessionId: sid, filename: fname });
      setProcStep(null);
      setPhase('upload');
      setDoneSteps([]);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const resetToUpload = () => {
    // "New paper" keeps the current paper in the library (persisted).
    // Deletion is explicit via the library trash button.
    setPhase('upload');
    setLibraryKey(k => k + 1);   // refresh library so the just-saved paper shows
    setHighlights([]);
    setSummary(null);
    setSessionId(null);
    setMessages([]);
    setDoneSteps([]);
    setProcStep(null);
    setProcMeta({});
    setUploadErr('');
    setSummarizeErr('');
    setOpenErr(null);
    setPendingSummarize(null);
    setVizData(null);
    setVizErr('');
    setSectionsOpen(false);
    setTeachLesson(null);
    setTeachErr('');
    setPaperFile(null);
    setHasPdf(false);
    setMobileView('ai');
  };

  const handleTeach = async () => {
    if (teachLoading || !sessionId) return;
    setTeachErr('');
    setTeachLoading(true);
    try {
      const data = await teachPaper(sessionId);
      setTeachLesson(data);
    } catch (e) {
      setTeachErr(e.response?.data?.detail || e.message || 'Failed to generate lesson');
    } finally {
      setTeachLoading(false);
    }
  };

  const handleVisualize = async () => {
    if (vizLoading || !sessionId) return;
    setVizErr('');
    setVizLoading(true);
    try {
      const data = await visualizePaper(sessionId);
      setVizData(data);
    } catch (e) {
      setVizErr(e.response?.data?.detail || e.message || 'Visualization failed');
    } finally {
      setVizLoading(false);
    }
  };

  // ── Q&A (also used by ConceptCards deep-dive) ─────────────────────
  const sendQuestion = async (q) => {
    if (!q || asking) return;
    setAskErr('');
    setAsking(true);
    setMessages(prev => [...prev, { role: 'user', content: q }]);
    setQuestion('');
    // scroll to chat
    setTimeout(() => chatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    try {
      const res = await askPaper(q, sessionId);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.answer,
        evidence: res.paper_evidence || [],
        related: res.related_papers || [],
        confidence: res.confidence,
        chunks: res.rag_chunks_used,
        followUps: res.follow_up_questions || [],
      }]);
      setTimeout(() => chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' }), 100);
    } catch (e) {
      setAskErr(e.response?.data?.detail || e.message || 'Failed to answer');
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setAsking(false);
    }
  };

  const handleAsk = () => sendQuestion(question.trim());

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAsk(); }
  };

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div className="paper-mode">

      {/* ── Back to research results (shown when opened from a deep-dive) ── */}
      {onBack && (
        <button className="paper-back" onClick={onBack}>
          <ArrowLeft size={15} /> Back to results
        </button>
      )}

      {/* ── Upload phase ── */}
      {phase === 'upload' && (
        <div
          className="paper-drop"
          onDrop={onDrop}
          onDragOver={e => e.preventDefault()}
          onClick={() => fileRef.current.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md"
            style={{ display: 'none' }}
            onChange={e => handleFile(e.target.files[0])}
          />
          <UploadCloud className="paper-drop-icon" />
          <div className="paper-drop-title">Drop a paper here</div>
          <div className="paper-drop-sub">PDF, TXT, or Markdown · Click or drag</div>
          {uploadErr && <div className="paper-err">{uploadErr}</div>}
        </div>
      )}

      {/* ── Inaccessible external paper (from the research deep-dive) ── */}
      {phase === 'upload' && openErr && (
        <div className="paper-drop" style={{ marginTop: 12, cursor: 'default' }}
          onClick={e => e.stopPropagation()}>
          <AlertTriangle className="paper-drop-icon" style={{ color: 'var(--yellow)' }} />
          <div className="paper-drop-title">{openErr.title || 'Paper'}</div>
          <div className="paper-drop-sub">{openErr.message}</div>
          {openErr.url && (
            <a className="btn btn-p" href={openErr.url} target="_blank" rel="noopener noreferrer"
              style={{ marginTop: 10, textDecoration: 'none' }}>
              <ExternalLink size={14} /> Open source
            </a>
          )}
        </div>
      )}

      {/* ── Library of saved papers (hidden when persistence is off) ── */}
      {libraryEnabled && phase === 'upload' && !pendingSummarize && (
        <Library onOpen={reopenPaper} refreshKey={libraryKey} />
      )}

      {/* ── Summarize-retry panel (shown when upload succeeded but summarize failed) ── */}
      {phase === 'upload' && pendingSummarize && (
        <div className="paper-drop" style={{ marginTop: 12, cursor: 'default' }}
          onClick={e => e.stopPropagation()}>
          <AlertTriangle className="paper-drop-icon" style={{ color: 'var(--yellow)' }} />
          <div className="paper-drop-title">Summarization failed</div>
          <div className="paper-drop-sub">
            Your paper was uploaded successfully but the AI summary timed out.
            Your paper is still in memory — click below to retry without re-uploading.
          </div>
          {summarizeErr && <div className="paper-err">{summarizeErr}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button
              className="btn btn-p"
              onClick={() => {
                setPhase('processing');
                setDoneSteps(['parse', 'embed']);
                runSummarize(pendingSummarize.sessionId, pendingSummarize.filename);
              }}
            >
              <RotateCcw size={14} /> Retry summarization
            </button>
            <button className="btn btn-g" onClick={resetToUpload}>
              Start over
            </button>
          </div>
        </div>
      )}

      {/* ── Processing phase ── */}
      {phase === 'processing' && (
        <div className="paper-processing">
          <div className="paper-proc-header">
            <FileText className="paper-proc-icon" />
            <div>
              <div className="paper-proc-name">{filename}</div>
              <div className="paper-proc-sub">Processing your paper…</div>
            </div>
          </div>

          <div className="proc-steps">
            {PROC_STEPS.map(step => {
              const isDone    = doneSteps.includes(step.key);
              const isActive  = procStep === step.key;
              const isPending = !isDone && !isActive;

              let label = step.label;
              if (step.key === 'embed' && isDone && procMeta.chunks)
                label = `${label} — ${procMeta.chunks} chunks indexed`;
              if (step.key === 'parse' && isDone && procMeta.chars)
                label = `${label} — ${(procMeta.chars / 1000).toFixed(1)}k characters`;

              return (
                <div key={step.key} className={`proc-step ${isDone ? 'ps-done' : isActive ? 'ps-active' : 'ps-pending'}`}>
                  <div className="proc-step-icon">
                    {isDone   && <span className="ps-tick">✓</span>}
                    {isActive  && <div className="spin" style={{ width: 14, height: 14 }} />}
                    {isPending && <span className="ps-dot" />}
                  </div>
                  <div className="proc-step-body">
                    <div className="proc-step-label">{label}</div>
                    {isActive && step.sub && <div className="proc-step-sub">{step.sub}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Ready phase: split reader (PDF ‖ AI insights) ── */}
      {phase === 'ready' && summary && (
        <>
          {hasPdf && (
            <div className="paper-viewtoggle">
              <button className={mobileView === 'pdf' ? 'on' : ''} onClick={() => setMobileView('pdf')}>
                <ScrollText size={14} /> Paper
              </button>
              <button className={mobileView === 'ai' ? 'on' : ''} onClick={() => setMobileView('ai')}>
                <PanelsTopLeft size={14} /> Insights
              </button>
            </div>
          )}

          <div className={hasPdf ? `paper-split mv-${mobileView}` : 'paper-nopdf'}>
            {/* Left: the actual PDF (only when a PDF is available) */}
            {hasPdf && (
              <div className="paper-split-pdf">
                <Suspense fallback={<PdfFallback />}>
                  <PdfPane
                    apiRef={pdfPaneRef} file={paperFile} sessionId={sessionId}
                    highlights={libraryEnabled ? highlights : []}
                    onCreateHighlight={libraryEnabled ? handleCreateHighlight : undefined}
                    onUpdateNote={libraryEnabled ? handleUpdateNote : undefined}
                    onDeleteHighlight={libraryEnabled ? handleDeleteHighlight : undefined}
                  />
                </Suspense>
              </div>
            )}

            {/* Right: AI insight panels */}
            <div className="paper-split-panels">

          {/* ── Summary panel ── */}
          <div className="paper-summary">
            <div className="paper-summary-header">
              <div className="dot d-bl"><FileText size={16} /></div>
              <div>
                <div className="paper-summary-title">{summary.title || filename}</div>
                {summary.authors && <div className="paper-summary-authors">{summary.authors}</div>}
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                  {summary.domain         && <span className="bdg bdg-o">{summary.domain}</span>}
                  {summary.technical_depth && (
                    <span className={`bdg ${DEPTH_COLORS[summary.technical_depth] || 'bdg-o'}`}>
                      {summary.technical_depth}
                    </span>
                  )}
                </div>
              </div>
              <button className="btn btn-g" style={{ marginLeft: 'auto', fontSize: '.7rem' }}
                onClick={resetToUpload}>
                ↩ New paper
              </button>
            </div>

            {/* Core innovation highlight */}
            {summary.core_innovation && (
              <div className="paper-innovation">
                <span className="paper-innovation-label">Core Innovation</span>
                {summary.core_innovation}
              </div>
            )}

            {summary.tldr && (
              <div className="paper-tldr">
                <span className="paper-tldr-label">TL;DR</span>
                {summary.tldr}
              </div>
            )}

            <div className="paper-summary-grid">
              {summary.abstract_summary && (
                <SummaryCard icon="🔍" label="Overview"     text={summary.abstract_summary} />
              )}
              {summary.methodology && (
                <SummaryCard icon="⚙️" label="Methodology"  text={summary.methodology} />
              )}
              {summary.key_results && (
                <SummaryCard icon="📊" label="Key Results"  text={summary.key_results} />
              )}
              {summary.limitations && (
                <SummaryCard icon="⚠️" label="Limitations"  text={summary.limitations} />
              )}
            </div>

            {/* Prior work comparison */}
            {summary.prior_work_comparison && (
              <div className="paper-prior-work">
                <span className="paper-prior-label">vs. Prior Work</span>
                {summary.prior_work_comparison}
              </div>
            )}

            {/* Section breakdown — collapsible */}
            {summary.section_breakdown?.length > 0 && (
              <div className="paper-sections">
                <button
                  className="paper-sections-toggle"
                  onClick={() => setSectionsOpen(v => !v)}
                >
                  <span>📑 Section Breakdown</span>
                  <span className="paper-sections-count">
                    {summary.section_breakdown.length} sections
                  </span>
                  <span style={{ marginLeft: 'auto' }}>{sectionsOpen ? '▴' : '▾'}</span>
                </button>
                {sectionsOpen && (
                  <SectionBreakdown
                    sections={summary.section_breakdown}
                    sessionId={sessionId}
                    onLocate={locateInPdf}
                    onLocatePage={locatePage}
                  />
                )}
              </div>
            )}

            {summary.future_work && (
              <div className="paper-future">
                <span className="paper-future-label">Future Work</span>
                {summary.future_work}
              </div>
            )}
          </div>

          {/* ── Figures & tables (P1) ── */}
          <FiguresStrip sessionId={sessionId} onLocate={locatePage} />

          {/* ── Highlights & notes (P2; hidden when persistence is off) ── */}
          {libraryEnabled && hasPdf && (
            <HighlightsPanel
              highlights={highlights}
              onOpen={(id) => pdfPaneRef.current?.scrollToHighlight?.(id)}
              onDelete={handleDeleteHighlight}
            />
          )}

          {/* ── Teach Me ── */}
          {!teachLesson && (
            <div className="teach-card">
              <div className="teach-card-left">
                <GraduationCap className="teach-card-icon" />
                <div>
                  <div className="teach-card-title">Teach me this paper</div>
                  <div className="teach-card-sub">
                    Step-by-step guided lesson with analogies and key takeaways — like having an expert explain it to you
                  </div>
                </div>
              </div>
              <button
                className="btn btn-p"
                onClick={handleTeach}
                disabled={teachLoading}
              >
                {teachLoading
                  ? <><span className="spin" /> Preparing lesson…</>
                  : <><GraduationCap size={15} /> Teach Me</>}
              </button>
              {teachErr && <div className="paper-err" style={{ width: '100%', marginTop: 6 }}>{teachErr}</div>}
            </div>
          )}

          {/* ── Teacher lesson ── */}
          {teachLesson && (
            <PaperTeacher lesson={teachLesson} onClose={() => setTeachLesson(null)} />
          )}

          {/* ── Concept cards ── */}
          {summary.key_concepts?.length > 0 && (
            <ConceptCards
              concepts={summary.key_concepts}
              onAsk={(q) => { sendQuestion(q); }}
              onLocate={(name) => locateInPdf(name)}
              disabled={asking}
            />
          )}

          {/* ── Visualize card ── */}
          {!vizData && (
            <div className="viz-card">
              <div className="viz-card-left">
                <Map className="viz-card-icon" />
                <div>
                  <div className="viz-card-title">Visualize this paper</div>
                  <div className="viz-card-sub">
                    Concept map · Methodology flow · Results charts — generated by AI
                  </div>
                </div>
              </div>
              <button
                className="btn btn-p"
                onClick={handleVisualize}
                disabled={vizLoading}
              >
                {vizLoading
                  ? <><span className="spin" /> Generating…</>
                  : '✦ Visualize'}
              </button>
              {vizErr && <div className="paper-err" style={{ width: '100%', marginTop: 6 }}>{vizErr}</div>}
            </div>
          )}

          {/* ── Visualization panel ── */}
          {vizData && (
            <Suspense fallback={<VizFallback />}>
              <PaperVisualization data={vizData} onClose={() => setVizData(null)} />
            </Suspense>
          )}

          {/* ── Q&A chat ── */}
          <div className="paper-qa" ref={chatRef}>
            <div className="sec-title" style={{ marginBottom: 10 }}>
              Ask a question about this paper
            </div>

            <div className="paper-chat">
              {messages.length === 0 && (
                <div className="paper-chat-empty">
                  Ask anything — or click a concept card above to auto deep-dive
                </div>
              )}
              {messages.map((m, i) => (
                <ChatMessage key={i} msg={m} onFollowUp={sendQuestion} onLocate={locateInPdf} disabled={asking} />
              ))}
              {asking && (
                <div className="chat-msg chat-msg-assistant">
                  <div className="chat-bubble">
                    <div className="chat-thinking">
                      <div className="spin" style={{ width: 12, height: 12 }} />
                      Searching paper + external literature…
                    </div>
                  </div>
                </div>
              )}
            </div>

            {askErr && <div className="paper-err" style={{ marginBottom: 8 }}>{askErr}</div>}

            <div className="paper-qa-input">
              <textarea
                placeholder="e.g. How does the attention mechanism work? What datasets were used?"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                disabled={asking}
              />
              <button className="btn btn-p" onClick={handleAsk} disabled={!question.trim() || asking}>
                {asking ? <span className="spin" /> : <ArrowUp size={16} />}
              </button>
            </div>
          </div>
            </div>{/* .paper-split-panels */}
          </div>{/* .paper-split */}
        </>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, text }) {
  return (
    <div className="paper-card">
      <div className="paper-card-h">
        <span>{icon}</span>
        <span className="paper-card-label">{label}</span>
      </div>
      <div className="paper-card-body">{text}</div>
    </div>
  );
}

function ChatMessage({ msg, onFollowUp, onLocate, disabled }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-assistant'}`}>
      <div className="chat-bubble">
        {isUser
          ? <div className="chat-content">{msg.content}</div>
          : <div className="chat-content"><Markdown>{msg.content}</Markdown></div>}

        {!isUser && msg.evidence?.length > 0 && (
          <details className="chat-evidence" open>
            <summary>Paper evidence ({msg.evidence.length}) — click to find in PDF</summary>
            <ul>{msg.evidence.map((e, i) => {
              const text = typeof e === 'string' ? e : e.text;
              const page = typeof e === 'string' ? undefined : e.page;
              return (
                <li key={i} className="evidence-link" onClick={() => onLocate?.(text, page)}
                    title="Jump to this passage in the PDF">
                  {text}{page ? <span className="evidence-page"> · p{page}</span> : null}
                </li>
              );
            })}</ul>
          </details>
        )}

        {!isUser && msg.related?.length > 0 && (
          <details className="chat-related">
            <summary>Related papers ({msg.related.length})</summary>
            <ul>
              {msg.related.map((p, i) => (
                <li key={i}>
                  <strong>{p.title}</strong>
                  {p.relevance && <span> — {p.relevance}</span>}
                </li>
              ))}
            </ul>
          </details>
        )}

        {!isUser && msg.confidence && (
          <div className="chat-meta">
            <span className={`bdg ${msg.confidence === 'high' ? 'bdg-g' : msg.confidence === 'low' ? 'bdg-r' : 'bdg-o'}`}>
              {msg.confidence} confidence
            </span>
            {msg.chunks > 0 && (
              <span className="chat-meta-stat">{msg.chunks} paper sections used</span>
            )}
          </div>
        )}

        {/* Follow-up question chips */}
        {!isUser && msg.followUps?.length > 0 && (
          <div className="follow-up-section">
            <div className="follow-up-label">Dive deeper</div>
            <div className="follow-up-chips">
              {msg.followUps.map((q, i) => (
                <button
                  key={i}
                  className="follow-up-chip"
                  onClick={() => onFollowUp(q)}
                  disabled={disabled}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
