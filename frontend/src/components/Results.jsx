import React, { useState, useMemo, useRef } from 'react';
import Viz from './Viz';
import PaperDeepDive from './PaperDeepDive';
import { explainSubQuestion } from '../services/api';

const TABS = [
  { k: 'answer', l: 'Answer' }, { k: 'intent', l: 'Intent' },
  { k: 'subq', l: 'Sub-Questions' }, { k: 'ctx', l: 'API Context' },
  { k: 'eval', l: 'Evaluation' }, { k: 'viz', l: 'Visualizations' },
  { k: 'trace', l: 'Trace' },
];

const SOURCE_META = {
  arxiv:            { label: 'arXiv',            icon: '📄', color: '#e05a14' },
  semantic_scholar: { label: 'Semantic Scholar', icon: '🎓', color: '#3880e8' },
  crossref:         { label: 'CrossRef',          icon: '🔗', color: '#6a5acd' },
};

/** Flatten all papers out of the api_results array */
function extractPapers(api_results) {
  if (!Array.isArray(api_results)) return [];
  const seen = new Set();
  const out = [];
  for (const res of api_results) {
    const items = res.data?.papers || res.data?.works || [];
    const source = res.source || 'arxiv';
    for (const p of items) {
      const key = (p.url || p.title || '').toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const url      = p.url   || '';
      const abstract = p.summary || p.abstract || '';
      const canDive  = !!(url || abstract);  // arXiv/S2 have these; CrossRef usually doesn't
      out.push({
        title:   p.title || 'Untitled',
        url,
        abstract,
        year:    p.year  || '',
        doi:     p.doi   || '',
        source,
        canDive,
      });
    }
  }
  return out;
}

export default function Results({ result: r }) {
  const [tab, setTab]             = useState('answer');
  const [divePaper, setDivePaper] = useState(null);
  const [activeSubQ, setActiveSubQ] = useState(null);
  const [subQLoading, setSubQLoading] = useState(false);
  const [subQData, setSubQData]   = useState(null);
  const subQRef = useRef(null);
  if (!r) return null;

  const papers = useMemo(() => extractPapers(r.api_results), [r.api_results]);
  const qualityPct = r.evaluation ? (r.evaluation.quality_score * 100).toFixed(0) : null;
  const confClass = qualityPct >= 70 ? 'bdg-g' : qualityPct >= 40 ? 'bdg-o' : 'bdg-r';

  const handleSubQClick = async (question) => {
    if (activeSubQ === question) { setActiveSubQ(null); setSubQData(null); return; }
    setActiveSubQ(question);
    setSubQData(null);
    setSubQLoading(true);
    // Scroll to panel after React renders it
    setTimeout(() => subQRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    try {
      const data = await explainSubQuestion(question, r.aggregated_context || '', r.api_results || []);
      setSubQData(data);
    } catch (e) {
      setSubQData({ answer: '⚠️ Failed to load explanation.', papers: [] });
    } finally {
      setSubQLoading(false);
    }
  };

  return (
    <div>
      <div className="tabs">{TABS.map(t => (
        <button key={t.k} className={`tb${tab === t.k ? ' on' : ''}`} onClick={() => setTab(t.k)}>{t.l}</button>
      ))}</div>

      {/* ── Answer tab ── */}
      {tab === 'answer' && (
        <div className="card">
          <div className="card-h">
            <div className="dot d-gr">✦</div>
            <h4>Research Answer</h4>
            {r.status === 'completed' && <span className="bdg bdg-g">Done</span>}
            {qualityPct && (
              <span className={`bdg ${confClass}`} style={{ marginLeft: 4 }}>{qualityPct}% quality</span>
            )}
          </div>
          <div className="card-b">
            {r.refined_query && (
              <p style={{ color: 'var(--t3)', fontSize: '.72rem', marginBottom: 10, fontStyle: 'italic' }}>
                Refined: {r.refined_query}
              </p>
            )}

            {/* Answer bubble — same style as Paper Q&A chat */}
            <div className="chat-msg chat-msg-assistant" style={{ marginBottom: 14 }}>
              <div className="chat-bubble" style={{ maxWidth: '100%' }}>
                <div className="chat-content">{r.final_answer || r.reasoning_output || 'No answer.'}</div>

                {/* RAG references as collapsible */}
                {r.rag_references?.length > 0 && (
                  <details className="chat-evidence">
                    <summary>Paper references ({r.rag_references.length})</summary>
                    <ul>{r.rag_references.map((x, i) => <li key={i}>{x}</li>)}</ul>
                  </details>
                )}

                {/* Evaluation feedback */}
                {r.evaluation?.feedback && (
                  <div className="chat-meta" style={{ marginTop: 8 }}>
                    <span className={`bdg ${confClass}`}>
                      {r.evaluation.is_satisfactory ? 'PASS' : 'FAIL'} · {qualityPct}%
                    </span>
                    <span className="chat-meta-stat" style={{ fontSize: '.7rem', color: 'var(--t3)', marginLeft: 6 }}>
                      {r.evaluation.feedback}
                    </span>
                  </div>
                )}

                {/* Sub-questions — clickable to expand focused answer */}
                {r.sub_questions?.length > 0 && (
                  <div className="follow-up-section">
                    <div className="follow-up-label">Sub-questions explored — click to dive deeper</div>
                    <div className="follow-up-chips">
                      {r.sub_questions.map((sq, i) => (
                        <button
                          key={i}
                          className={`follow-up-chip${activeSubQ === sq.question ? ' follow-up-chip-active' : ''}`}
                          onClick={() => handleSubQClick(sq.question)}
                        >
                          {sq.question}
                          <span style={{ marginLeft: 6, fontSize: '.65rem', opacity: 0.6 }}>
                            {activeSubQ === sq.question ? '▴' : '▾'}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ── Sub-question detail panel ── */}
            {activeSubQ && (
              <div className="subq-panel" ref={subQRef}>
                <div className="subq-panel-header">
                  <span className="subq-panel-icon">🔍</span>
                  <div className="subq-panel-question">{activeSubQ}</div>
                </div>
                {subQLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '16px 0', color: 'var(--t3)', fontSize: '.78rem' }}>
                    <div className="spin" style={{ width: 16, height: 16 }} /> Researching this sub-question…
                  </div>
                )}
                {subQData && (
                  <>
                    <div className="subq-answer">{subQData.answer}</div>
                    {subQData.papers?.length > 0 && (
                      <div style={{ marginTop: 14 }}>
                        <div className="ref-papers-heading" style={{ marginBottom: 8 }}>
                          <span className="ref-papers-icon">📄</span> Sources
                          <span className="bdg bdg-o" style={{ marginLeft: 6 }}>{subQData.papers.length}</span>
                        </div>
                        <div className="ref-papers-grid">
                          {subQData.papers.map((p, i) => {
                            const sm = SOURCE_META[p.source] || SOURCE_META.arxiv;
                            if (p.canDive || p.abstract) return (
                              <button key={i} className="ref-paper-card" onClick={() => setDivePaper(p)}>
                                <div className="ref-paper-top">
                                  <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                                  {p.year && <span className="ref-paper-year">{p.year}</span>}
                                </div>
                                <div className="ref-paper-title">{p.title}</div>
                                {p.abstract && <div className="ref-paper-abstract">{p.abstract.slice(0,120)}{p.abstract.length>120?'…':''}</div>}
                                <div className="ref-paper-cta">Summarize &amp; Visualize →</div>
                              </button>
                            );
                            if (p.url) return (
                              <a key={i} className="ref-paper-card" href={p.url} target="_blank" rel="noopener noreferrer"
                                 style={{ textDecoration:'none', display:'flex', flexDirection:'column', gap:5 }}>
                                <div className="ref-paper-top">
                                  <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                                  {p.year && <span className="ref-paper-year">{p.year}</span>}
                                </div>
                                <div className="ref-paper-title">{p.title}</div>
                                <div className="ref-paper-cta">↗ Open source</div>
                              </a>
                            );
                            return (
                              <div key={i} className="ref-paper-card" style={{ cursor:'default' }}>
                                <div className="ref-paper-top">
                                  <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                                  {p.year && <span className="ref-paper-year">{p.year}</span>}
                                </div>
                                <div className="ref-paper-title">{p.title}</div>
                                <div className="ref-paper-cta" style={{ color:'var(--t3)', fontSize:'.62rem' }}>
                                  Search this title on Scholar or Semantic Scholar
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ── Referenced papers — click to deep-dive ── */}
            {papers.length > 0 && (
              <div className="ref-papers-section">
                <div className="ref-papers-heading">
                  <span className="ref-papers-icon">🔗</span>
                  Referenced Papers
                  <span className="bdg bdg-o" style={{ marginLeft: 6 }}>{papers.length}</span>
                </div>
                <div className="ref-papers-grid">
                  {papers.map((p, i) => {
                    const sm = SOURCE_META[p.source] || SOURCE_META.arxiv;
                    // canDive = has URL or abstract → open deep-dive modal
                    // has URL only → open as anchor link
                    // nothing → non-interactive info card
                    if (p.canDive) {
                      return (
                        <button key={i} className="ref-paper-card" onClick={() => setDivePaper(p)}>
                          <div className="ref-paper-top">
                            <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                            {p.year && <span className="ref-paper-year">{p.year}</span>}
                          </div>
                          <div className="ref-paper-title">{p.title}</div>
                          {p.abstract && <div className="ref-paper-abstract">{p.abstract.slice(0,120)}{p.abstract.length>120?'…':''}</div>}
                          <div className="ref-paper-cta">Summarize &amp; Visualize →</div>
                        </button>
                      );
                    }
                    if (p.url) {
                      return (
                        <a key={i} className="ref-paper-card" href={p.url} target="_blank" rel="noopener noreferrer"
                           style={{ textDecoration: 'none', display: 'flex', flexDirection: 'column', gap: 5 }}>
                          <div className="ref-paper-top">
                            <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                            {p.year && <span className="ref-paper-year">{p.year}</span>}
                          </div>
                          <div className="ref-paper-title">{p.title}</div>
                          <div className="ref-paper-cta">↗ Open source</div>
                        </a>
                      );
                    }
                    // No URL, no abstract — info card only
                    return (
                      <div key={i} className="ref-paper-card" style={{ cursor: 'default' }}>
                        <div className="ref-paper-top">
                          <span className="ref-paper-src" style={{ color: sm.color }}>{sm.icon} {sm.label}</span>
                          {p.year && <span className="ref-paper-year">{p.year}</span>}
                        </div>
                        <div className="ref-paper-title">{p.title}</div>
                        <div className="ref-paper-cta" style={{ color: 'var(--t3)', fontSize: '.62rem' }}>
                          Search this title on Scholar or Semantic Scholar
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'intent' && (
        <div className="card"><div className="card-h"><div className="dot d-bl">◎</div><h4>Intent</h4></div>
          <div className="card-b">{r.intent ? <pre>{JSON.stringify(r.intent, null, 2)}</pre> : 'N/A'}</div></div>
      )}

      {tab === 'subq' && (
        <div className="card"><div className="card-h"><div className="dot d-or">⊞</div><h4>Sub-Questions</h4></div>
          <div className="card-b" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {(r.sub_questions || []).map((sq, i) => (
              <div key={i} style={{ background: 'var(--bg0)', padding: '8px 12px', borderRadius: 'var(--rs)', display: 'flex', gap: 8 }}>
                <span style={{ color: 'var(--orange)', fontWeight: 700, fontFamily: 'var(--m)', fontSize: '.7rem', minWidth: 18 }}>#{sq.priority || i + 1}</span>
                <div style={{ flex: 1 }}><div>{sq.question}</div><span className="bdg bdg-o" style={{ marginTop: 3 }}>{sq.api_source}</span></div>
              </div>
            ))}
            {!(r.sub_questions?.length) && 'None'}
          </div></div>
      )}

      {tab === 'ctx' && (
        <div className="card"><div className="card-h"><div className="dot d-bl">⊕</div><h4>Aggregated Context</h4></div>
          <div className="card-b"><div style={{ whiteSpace: 'pre-wrap', maxHeight: 450, overflow: 'auto' }}>{r.aggregated_context || 'N/A'}</div>
            {r.api_results?.length > 0 && <div style={{ marginTop: 8, fontSize: '.68rem', color: 'var(--t3)' }}>
              APIs: {r.api_results.length} | Errors: {r.api_results.filter(x => x.error).length}</div>}
          </div></div>
      )}

      {tab === 'eval' && (
        <div className="card"><div className="card-h"><div className="dot d-gr">✓</div><h4>Evaluation</h4></div>
          <div className="card-b">{r.evaluation ? (<>
            <div style={{ display: 'flex', gap: 20, marginBottom: 10 }}>
              <div><div style={{ fontSize: '1.6rem', fontWeight: 700, color: r.evaluation.is_satisfactory ? 'var(--green)' : 'var(--red)' }}>
                {(r.evaluation.quality_score * 100).toFixed(0)}%</div>
                <div style={{ fontSize: '.64rem', color: 'var(--t3)' }}>Quality</div></div>
              <div className={`bdg ${r.evaluation.is_satisfactory ? 'bdg-g' : 'bdg-r'}`} style={{ fontSize: '.8rem', padding: '3px 10px', alignSelf: 'center' }}>
                {r.evaluation.is_satisfactory ? 'PASS' : 'FAIL'}</div>
            </div>
            <div className="qbar"><div className="qfill" style={{ width: `${r.evaluation.quality_score * 100}%`,
              background: r.evaluation.quality_score >= .7 ? 'var(--green)' : r.evaluation.quality_score >= .4 ? 'var(--yellow)' : 'var(--red)' }} /></div>
            {r.evaluation.feedback && <p style={{ marginTop: 10 }}>{r.evaluation.feedback}</p>}
            {r.evaluation.suggestions?.length > 0 && <ul style={{ paddingLeft: 16, marginTop: 6, fontSize: '.78rem' }}>
              {r.evaluation.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>}
          </>) : 'N/A'}</div></div>
      )}

      {tab === 'viz' && (
        <div className="card"><div className="card-h"><div className="dot d-yl">📊</div><h4>Visualizations</h4></div>
          <div className="card-b">{r.visualizations?.length
            ? r.visualizations.map((v, i) => <Viz key={i} config={v} />)
            : 'None generated.'}</div></div>
      )}

      {tab === 'trace' && (
        <div className="card"><div className="card-h"><div className="dot d-bl">⏱</div><h4>Agent Trace</h4></div>
          <div className="card-b" style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {(r.agent_trace || []).map((t, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--bg0)', padding: '6px 10px', borderRadius: 'var(--rs)' }}>
                <span style={{ fontWeight: 500 }}>{t.agent}</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className="bdg bdg-g">{t.status}</span>
                  <span style={{ fontFamily: 'var(--m)', fontSize: '.66rem', color: 'var(--t2)' }}>{t.elapsed_s}s</span>
                </div>
              </div>
            ))}
            {!(r.agent_trace?.length) && 'No trace.'}
          </div></div>
      )}

      {/* ── Paper Deep Dive modal ── */}
      {divePaper && (
        <PaperDeepDive paper={divePaper} onClose={() => setDivePaper(null)} />
      )}
    </div>
  );
}
