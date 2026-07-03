import React, { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { fetchPaperFromUrl, summarizePaper, askPaper, visualizePaper } from '../services/api';
import ConceptCards from './ConceptCards';

const PaperVisualization = lazy(() => import('./PaperVisualization'));
const PdfPane = lazy(() => import('./PdfPane'));

const PROC_STEPS = [
  { key: 'fetch',   label: 'Fetching paper',                       sub: 'Downloading from source…' },
  { key: 'embed',   label: 'Chunking & building semantic index',   sub: '' },
  { key: 'summary', label: 'AI summarization',                     sub: 'Reading paper deeply with Llama 3.3 70B' },
  { key: 'ready',   label: 'Ready',                                sub: '' },
];

const DEPTH_COLORS = { beginner: 'bdg-g', intermediate: 'bdg-o', expert: 'bdg-r' };

const SOURCE_LABELS = {
  arxiv:            { label: 'arXiv',             color: '#e05a14' },
  semantic_scholar: { label: 'Semantic Scholar',  color: '#3880e8' },
  crossref:         { label: 'CrossRef',           color: '#6a5acd' },
};

export default function PaperDeepDive({ paper, onClose }) {
  const [phase, setPhase]         = useState('processing'); // processing | ready | error
  const [procStep, setProcStep]   = useState('fetch');
  const [doneSteps, setDoneSteps] = useState([]);
  const [procMeta, setProcMeta]   = useState({});
  const [sessionId, setSessionId] = useState(null);
  const [summary, setSummary]     = useState(null);
  const [vizData, setVizData]     = useState(null);
  const [vizLoading, setVizLoading] = useState(false);
  const [tab, setTab]             = useState('summary'); // summary | visualize | qa
  const [messages, setMessages]   = useState([]);
  const [question, setQuestion]   = useState('');
  const [asking, setAsking]       = useState(false);
  const [sectionsOpen, setSectionsOpen] = useState(false);
  const [errMsg, setErrMsg]       = useState('');
  const chatRef = useRef();

  // Auto-start fetching on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        // Step 1: fetch + ingest paper
        setProcStep('fetch');
        const uploaded = await fetchPaperFromUrl(
          paper.url || '',
          paper.abstract || '',
          paper.title || '',
        );
        if (cancelled) return;
        const sid = uploaded.session_id;
        setSessionId(sid);
        setProcMeta({ chunks: uploaded.chunks, chars: uploaded.text_length });
        setDoneSteps(['fetch']);

        // Step 2: summarize
        setProcStep('embed');
        setDoneSteps(d => [...d, 'embed']);
        setProcStep('summary');
        const sum = await summarizePaper(sid, uploaded.filename);
        if (cancelled) return;
        setSummary(sum);
        setDoneSteps(d => [...d, 'summary', 'ready']);
        setProcStep('ready');
        setPhase('ready');
      } catch (e) {
        if (cancelled) return;
        setErrMsg(e.response?.data?.detail || e.message || 'Failed to load paper');
        setPhase('error');
      }
    }
    load();
    return () => { cancelled = true; };
  }, [paper]);

  // Load visualization when user switches to that tab
  useEffect(() => {
    if (tab !== 'visualize' || !sessionId || vizData || vizLoading) return;
    setVizLoading(true);
    visualizePaper(sessionId)
      .then(d => { setVizData(d); setVizLoading(false); })
      .catch(() => setVizLoading(false));
  }, [tab, sessionId, vizData, vizLoading]);

  // Scroll chat to bottom on new messages
  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  const sendQuestion = async (q = question) => {
    const text = q.trim();
    if (!text || !sessionId || asking) return;
    setQuestion('');
    setAsking(true);
    setMessages(m => [...m, { role: 'user', content: text }]);
    try {
      const res = await askPaper(text, sessionId);
      setMessages(m => [...m, {
        role: 'assistant',
        content: res.answer || '',
        evidence: res.paper_evidence || [],
        related: res.related_papers || [],
        confidence: res.confidence,
        followUps: res.follow_up_questions || [],
        chunks: res.rag_chunks_used,
      }]);
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', content: '⚠️ ' + (e.response?.data?.detail || e.message) }]);
    } finally {
      setAsking(false);
    }
  };

  const src = SOURCE_LABELS[paper.source] || { label: paper.source || 'External', color: '#888' };

  return (
    <div className="ddive-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="ddive-panel">

        {/* ── Header ── */}
        <div className="ddive-header">
          <div className="ddive-header-left">
            <span className="ddive-source-badge" style={{ background: src.color + '22', color: src.color, border: `1px solid ${src.color}55` }}>
              {src.label}
            </span>
            <div className="ddive-title">{paper.title || 'Paper'}</div>
            {paper.url && (
              <a href={paper.url} target="_blank" rel="noopener noreferrer" className="ddive-ext-link">
                ↗ Open source
              </a>
            )}
          </div>
          <button className="ddive-close" onClick={onClose}>✕</button>
        </div>

        {/* ── Processing phase ── */}
        {phase === 'processing' && (
          <div className="ddive-body ddive-body-proc">
            <div className="paper-processing" style={{ maxWidth: 540, margin: '0 auto' }}>
              <div className="paper-proc-header">
                <div className="paper-proc-icon">📄</div>
                <div>
                  <div className="paper-proc-name">{paper.title || 'Paper'}</div>
                  <div className="paper-proc-sub">Loading paper deeply…</div>
                </div>
              </div>
              <div className="proc-steps">
                {PROC_STEPS.map(step => {
                  const isDone   = doneSteps.includes(step.key);
                  const isActive = procStep === step.key;
                  let label = step.label;
                  if (step.key === 'embed' && isDone && procMeta.chunks)
                    label = `${label} — ${procMeta.chunks} chunks indexed`;
                  if (step.key === 'fetch' && isDone && procMeta.chars)
                    label = `${label} — ${(procMeta.chars / 1000).toFixed(1)}k characters`;
                  return (
                    <div key={step.key} className={`proc-step ${isDone ? 'ps-done' : isActive ? 'ps-active' : 'ps-pending'}`}>
                      <div className="proc-step-icon">
                        {isDone   && <span className="ps-tick">✓</span>}
                        {isActive  && <div className="spin" style={{ width: 14, height: 14 }} />}
                        {!isDone && !isActive && <span className="ps-dot" />}
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
          </div>
        )}

        {/* ── Error phase — paper not accessible, show metadata + open link ── */}
        {phase === 'error' && (
          <div className="ddive-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
            <div style={{ maxWidth: 480, width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <span style={{ fontSize: '1.5rem' }}>📄</span>
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--t0)', fontSize: '.88rem' }}>{paper.title}</div>
                  {paper.year && <div style={{ fontSize: '.72rem', color: 'var(--t3)', marginTop: 2 }}>{paper.year}</div>}
                </div>
              </div>
              <div style={{ background: 'var(--bg0)', border: '1px solid var(--bdr)', borderRadius: 'var(--r)', padding: '12px 16px', marginBottom: 14 }}>
                <div style={{ fontSize: '.72rem', fontWeight: 700, color: 'var(--yellow)', fontFamily: 'var(--m)', marginBottom: 6 }}>
                  ⚠️ Full text not accessible
                </div>
                <div style={{ fontSize: '.78rem', color: 'var(--t2)', lineHeight: 1.6 }}>
                  This paper ({src.label}) doesn't have a publicly accessible PDF or abstract.
                  {paper.url && ' You can open the source page below to read it directly.'}
                </div>
              </div>
              {paper.url && (
                <a href={paper.url} target="_blank" rel="noopener noreferrer"
                   style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--orange)', color: '#fff',
                            borderRadius: 'var(--rs)', padding: '8px 16px', fontSize: '.78rem', fontWeight: 600,
                            textDecoration: 'none', transition: 'opacity .15s' }}>
                  ↗ Open paper on {src.label}
                </a>
              )}
              {!paper.url && (
                <div style={{ fontSize: '.72rem', color: 'var(--t3)' }}>
                  Search for "{paper.title}" on Google Scholar or Semantic Scholar to find this paper.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Ready phase ── */}
        {phase === 'ready' && summary && (
          <>
            {/* Sub-tabs */}
            <div className="ddive-tabs">
              {[['summary', '📋 Summary'], ['pdf', '📄 Paper'], ['visualize', '🗺️ Visualize'], ['qa', '💬 Ask']].map(([k, l]) => (
                <button key={k} className={`ddive-tab${tab === k ? ' ddive-tab-on' : ''}`} onClick={() => setTab(k)}>{l}</button>
              ))}
            </div>

            {/* ── Summary tab ── */}
            {tab === 'summary' && (
              <div className="ddive-body ddive-scrollable">
                {/* Core innovation */}
                {summary.core_innovation && (
                  <div className="paper-innovation" style={{ margin: '0 0 10px' }}>
                    <span className="paper-innovation-label">Core Innovation</span>
                    {summary.core_innovation}
                  </div>
                )}
                {summary.tldr && (
                  <div className="paper-tldr" style={{ margin: '0 0 10px' }}>
                    <span className="paper-tldr-label">TL;DR</span>
                    {summary.tldr}
                  </div>
                )}

                <div className="paper-summary-grid">
                  {summary.abstract_summary && <SummaryCard icon="🔍" label="Overview"    text={summary.abstract_summary} />}
                  {summary.methodology      && <SummaryCard icon="⚙️" label="Methodology" text={summary.methodology} />}
                  {summary.key_results      && <SummaryCard icon="📊" label="Key Results" text={summary.key_results} />}
                  {summary.limitations      && <SummaryCard icon="⚠️" label="Limitations" text={summary.limitations} />}
                </div>

                {summary.prior_work_comparison && (
                  <div className="paper-prior-work" style={{ margin: '10px 0' }}>
                    <span className="paper-prior-label">vs. Prior Work</span>
                    {summary.prior_work_comparison}
                  </div>
                )}

                {summary.key_concepts?.length > 0 && (
                  <ConceptCards concepts={summary.key_concepts} onSelect={c => { setTab('qa'); setQuestion(c.name); }} />
                )}

                {summary.section_breakdown?.length > 0 && (
                  <div className="paper-sections">
                    <button className="paper-sections-toggle" onClick={() => setSectionsOpen(v => !v)}>
                      <span>📑 Section Breakdown</span>
                      <span className="paper-sections-count">{summary.section_breakdown.length} sections</span>
                      <span style={{ marginLeft: 'auto' }}>{sectionsOpen ? '▴' : '▾'}</span>
                    </button>
                    {sectionsOpen && (
                      <div className="paper-sections-list">
                        {summary.section_breakdown.map((s, i) => (
                          <div key={i} className="paper-section-row">
                            <div className="paper-section-name">{s.section}</div>
                            <div className="paper-section-summary">{s.summary}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {summary.future_work && (
                  <div className="paper-future" style={{ marginTop: 10 }}>
                    <span className="paper-future-label">Future Work</span>
                    {summary.future_work}
                  </div>
                )}
              </div>
            )}

            {/* ── Paper (PDF) tab ── */}
            {tab === 'pdf' && (
              <div className="ddive-body" style={{ padding: 0, height: 'calc(92vh - 210px)' }}>
                <Suspense fallback={<div style={{ padding: 30, textAlign: 'center', color: 'var(--t2)' }}><span className="spin" /> Loading PDF…</div>}>
                  <PdfPane sessionId={sessionId} />
                </Suspense>
              </div>
            )}

            {/* ── Visualize tab ── */}
            {tab === 'visualize' && (
              <div className="ddive-body ddive-scrollable">
                {vizLoading && (
                  <div style={{ textAlign: 'center', padding: 40, color: 'var(--t3)' }}>
                    <div className="spin" style={{ width: 28, height: 28, margin: '0 auto 12px' }} />
                    Building visualization…
                  </div>
                )}
                {!vizLoading && vizData && (
                  <Suspense fallback={<div style={{ padding: 30, textAlign: 'center', color: 'var(--t2)' }}><span className="spin" /> Loading…</div>}>
                    <PaperVisualization data={vizData} />
                  </Suspense>
                )}
              </div>
            )}

            {/* ── Q&A tab ── */}
            {tab === 'qa' && (
              <div className="ddive-body ddive-qa">
                <div className="ddive-chat" ref={chatRef}>
                  {messages.length === 0 && (
                    <div className="ddive-chat-empty">
                      Ask anything about this paper
                    </div>
                  )}
                  {messages.map((msg, i) => (
                    <ChatMessage key={i} msg={msg} onFollowUp={q => sendQuestion(q)} disabled={asking} />
                  ))}
                  {asking && (
                    <div className="chat-msg chat-msg-assistant">
                      <div className="chat-bubble">
                        <div className="spin" style={{ width: 16, height: 16 }} />
                      </div>
                    </div>
                  )}
                </div>
                <div className="ddive-input-row">
                  <input
                    className="ddive-input"
                    placeholder="Ask a question about this paper…"
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendQuestion()}
                    disabled={asking}
                  />
                  <button className="ddive-send" onClick={() => sendQuestion()} disabled={asking || !question.trim()}>
                    {asking ? <span className="spin" style={{ width: 14, height: 14 }} /> : '↑'}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
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

function ChatMessage({ msg, onFollowUp, disabled }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-assistant'}`}>
      <div className="chat-bubble">
        <div className="chat-content">{msg.content}</div>
        {!isUser && msg.evidence?.length > 0 && (
          <details className="chat-evidence">
            <summary>Paper evidence ({msg.evidence.length})</summary>
            <ul>{msg.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
          </details>
        )}
        {!isUser && msg.related?.length > 0 && (
          <details className="chat-related">
            <summary>Related papers ({msg.related.length})</summary>
            <ul>{msg.related.map((p, i) => (
              <li key={i}><strong>{p.title}</strong>{p.relevance && <span> — {p.relevance}</span>}</li>
            ))}</ul>
          </details>
        )}
        {!isUser && msg.confidence && (
          <div className="chat-meta">
            <span className={`bdg ${msg.confidence === 'high' ? 'bdg-g' : msg.confidence === 'low' ? 'bdg-r' : 'bdg-o'}`}>
              {msg.confidence} confidence
            </span>
            {msg.chunks > 0 && <span className="chat-meta-stat">{msg.chunks} paper sections used</span>}
          </div>
        )}
        {!isUser && msg.followUps?.length > 0 && (
          <div className="follow-up-section">
            <div className="follow-up-label">Dive deeper</div>
            <div className="follow-up-chips">
              {msg.followUps.map((q, i) => (
                <button key={i} className="follow-up-chip" onClick={() => onFollowUp(q)} disabled={disabled}>{q}</button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
