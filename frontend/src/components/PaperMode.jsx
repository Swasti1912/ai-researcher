import React, { useState, useRef } from 'react';
import { uploadPaper, summarizePaper, askPaper, deleteSession, visualizePaper, teachPaper } from '../services/api';
import PaperVisualization from './PaperVisualization';
import ConceptCards from './ConceptCards';
import PaperTeacher from './PaperTeacher';

// Processing steps shown while a paper is being ingested
const PROC_STEPS = [
  { key: 'parse',   label: 'Extracting text from document',   sub: '' },
  { key: 'embed',   label: 'Chunking & building semantic index', sub: '' },
  { key: 'summary', label: 'AI summarization',                 sub: 'Reading paper deeply with GPT-4o' },
  { key: 'ready',   label: 'Ready for Q&A',                    sub: '' },
];

const DEPTH_COLORS = { beginner: 'bdg-g', intermediate: 'bdg-o', expert: 'bdg-r' };

export default function PaperMode() {
  const [phase, setPhase]         = useState('upload'); // upload | processing | ready
  const [sessionId, setSessionId] = useState(null);
  const [filename, setFilename]   = useState('');
  const [summary, setSummary]     = useState(null);
  const [procStep, setProcStep]   = useState(null);
  const [doneSteps, setDoneSteps] = useState([]);
  const [procMeta, setProcMeta]   = useState({});
  const [messages, setMessages]   = useState([]);
  const [question, setQuestion]   = useState('');
  const [asking, setAsking]       = useState(false);
  const [uploadErr, setUploadErr] = useState('');
  const [askErr, setAskErr]       = useState('');
  const [vizData, setVizData]     = useState(null);
  const [vizLoading, setVizLoading] = useState(false);
  const [vizErr, setVizErr]       = useState('');
  const [sectionsOpen, setSectionsOpen] = useState(false);
  const [teachLesson, setTeachLesson] = useState(null);
  const [teachLoading, setTeachLoading] = useState(false);
  const [teachErr, setTeachErr]   = useState('');
  const fileRef = useRef();
  const chatRef = useRef();

  // ── Upload + summarize ────────────────────────────────────────────
  const handleFile = async (file) => {
    if (!file) return;
    setUploadErr('');
    setFilename(file.name);
    setSummary(null);
    setMessages([]);
    setDoneSteps([]);
    setPhase('processing');

    try {
      setProcStep('parse');
      const uploaded = await uploadPaper(file);
      setProcMeta({ chunks: uploaded.chunks, chars: uploaded.text_length });
      setDoneSteps(['parse', 'embed']);

      setProcStep('summary');
      const sum = await summarizePaper(uploaded.session_id, file.name);
      setSessionId(uploaded.session_id);
      setSummary(sum);

      setDoneSteps(['parse', 'embed', 'summary', 'ready']);
      setProcStep(null);
      setTimeout(() => setPhase('ready'), 600);
    } catch (e) {
      setUploadErr(e.response?.data?.detail || e.message || 'Processing failed');
      setPhase('upload');
      setProcStep(null);
      setDoneSteps([]);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const resetToUpload = () => {
    if (sessionId) deleteSession(sessionId).catch(() => {});
    setPhase('upload');
    setSummary(null);
    setSessionId(null);
    setMessages([]);
    setDoneSteps([]);
    setProcStep(null);
    setProcMeta({});
    setUploadErr('');
    setVizData(null);
    setVizErr('');
    setSectionsOpen(false);
    setTeachLesson(null);
    setTeachErr('');
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
          <div className="paper-drop-icon">📄</div>
          <div className="paper-drop-title">Drop a paper here</div>
          <div className="paper-drop-sub">PDF, TXT, or Markdown · Click or drag</div>
          {uploadErr && <div className="paper-err">{uploadErr}</div>}
        </div>
      )}

      {/* ── Processing phase ── */}
      {phase === 'processing' && (
        <div className="paper-processing">
          <div className="paper-proc-header">
            <div className="paper-proc-icon">📄</div>
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

      {/* ── Ready phase ── */}
      {phase === 'ready' && summary && (
        <div className="paper-ready">

          {/* ── Summary panel ── */}
          <div className="paper-summary">
            <div className="paper-summary-header">
              <div className="dot d-bl">📄</div>
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
              <div className="paper-future">
                <span className="paper-future-label">Future Work</span>
                {summary.future_work}
              </div>
            )}
          </div>

          {/* ── Teach Me ── */}
          {!teachLesson && (
            <div className="teach-card">
              <div className="teach-card-left">
                <div className="teach-card-icon">🎓</div>
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
                  : '🎓 Teach Me'}
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
              disabled={asking}
            />
          )}

          {/* ── Visualize card ── */}
          {!vizData && (
            <div className="viz-card">
              <div className="viz-card-left">
                <div className="viz-card-icon">🗺️</div>
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
            <PaperVisualization data={vizData} onClose={() => setVizData(null)} />
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
                <ChatMessage key={i} msg={m} onFollowUp={sendQuestion} disabled={asking} />
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
                {asking ? <span className="spin" /> : '↑'}
              </button>
            </div>
          </div>
        </div>
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
