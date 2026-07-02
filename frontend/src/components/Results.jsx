import React, { useState, useMemo } from 'react';
import {
  FileText, GraduationCap, Link2, ChevronDown, Sparkles,
  BadgeCheck, Library, SlidersHorizontal, ExternalLink,
} from 'lucide-react';
import Markdown from './Markdown';
import Viz from './Viz';
import PaperDeepDive from './PaperDeepDive';
import { explainSubQuestion } from '../services/api';

const SOURCE_META = {
  arxiv:            { label: 'arXiv',            Icon: FileText,       color: '#f2822c' },
  semantic_scholar: { label: 'Semantic Scholar', Icon: GraduationCap,  color: '#4c8dff' },
  crossref:         { label: 'CrossRef',          Icon: Link2,          color: '#a07cff' },
};

/** Flatten unique papers out of api_results */
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
      const url = p.url || '';
      const abstract = p.summary || p.abstract || '';
      out.push({
        title: p.title || 'Untitled', url, abstract,
        year: p.year || '', doi: p.doi || '', source,
        canDive: !!(url || abstract),
      });
    }
  }
  return out;
}

/* ── Reusable paper card ─────────────────────────────────────────────── */
function PaperCard({ p, onDive }) {
  const sm = SOURCE_META[p.source] || SOURCE_META.arxiv;
  const Head = (
    <>
      <div className="ref-top">
        <span className="ref-src" style={{ color: sm.color }}><sm.Icon size={12} /> {sm.label}</span>
        {p.year && <span className="ref-year">{p.year}</span>}
      </div>
      <div className="ref-title">{p.title}</div>
      {p.abstract && <div className="ref-abstract">{p.abstract.slice(0, 130)}{p.abstract.length > 130 ? '…' : ''}</div>}
    </>
  );

  if (p.canDive) {
    return (
      <button className="ref-card" onClick={() => onDive(p)}>
        {Head}
        <span className="ref-cta"><Sparkles size={11} /> Summarize &amp; visualize</span>
      </button>
    );
  }
  if (p.url) {
    return (
      <a className="ref-card" href={p.url} target="_blank" rel="noopener noreferrer">
        {Head}
        <span className="ref-cta"><ExternalLink size={11} /> Open source</span>
      </a>
    );
  }
  return (
    <div className="ref-card static">
      {Head}
      <span className="ref-cta muted">Search this title externally</span>
    </div>
  );
}

/* ── Sub-question accordion item (fetches its own answer on open) ─────── */
function SubQItem({ index, question, context, apiResults, onDive }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !data && !loading) {
      setLoading(true);
      try {
        setData(await explainSubQuestion(question, context || '', apiResults || []));
      } catch {
        setData({ answer: '⚠️ Failed to load explanation.', papers: [] });
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className={`subq-item ${open ? 'open' : ''}`}>
      <button className="subq-trigger" onClick={toggle}>
        <span className="subq-num">{index + 1}</span>
        <span className="subq-q">{question}</span>
        <ChevronDown size={17} className="subq-chevron" />
      </button>
      {open && (
        <div className="subq-body">
          {loading && <div className="subq-loading"><span className="spin" /> Researching this sub-question…</div>}
          {data && (
            <>
              <Markdown>{data.answer}</Markdown>
              {data.papers?.length > 0 && (
                <div className="ref-section">
                  <div className="ref-heading"><Library size={13} /> Sources · {data.papers.length}</div>
                  <div className="ref-grid">
                    {data.papers.map((p, i) => <PaperCard key={i} p={p} onDive={onDive} />)}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Details drawer (technical) ──────────────────────────────────────── */
const DETAIL_TABS = [
  { k: 'context', l: 'API Context' },
  { k: 'eval',    l: 'Evaluation' },
  { k: 'viz',     l: 'Visualizations' },
  { k: 'trace',   l: 'Agent Trace' },
];

function DetailsDrawer({ r }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState('context');

  return (
    <div className={`details ${open ? 'open' : ''}`}>
      <button className="details-trigger" onClick={() => setOpen(o => !o)}>
        <SlidersHorizontal size={15} /> Technical details
        <ChevronDown size={16} className="chev" />
      </button>
      {open && (
        <div className="details-body">
          <div className="details-tabs tabs">
            {DETAIL_TABS.map(t => (
              <button key={t.k} className={`tb ${tab === t.k ? 'on' : ''}`} onClick={() => setTab(t.k)}>{t.l}</button>
            ))}
          </div>
          <div className="details-content card-b">
            {tab === 'context' && (
              <>
                <div style={{ whiteSpace: 'pre-wrap', maxHeight: 420, overflow: 'auto', fontSize: '.8rem' }}>
                  {r.aggregated_context || 'No aggregated context.'}
                </div>
                {r.api_results?.length > 0 && (
                  <div style={{ marginTop: 10, fontSize: '.68rem', color: 'var(--t3)' }}>
                    APIs called: {r.api_results.length} · Errors: {r.api_results.filter(x => x.error).length}
                  </div>
                )}
              </>
            )}

            {tab === 'eval' && (r.evaluation ? (
              <>
                <div style={{ display: 'flex', gap: 20, marginBottom: 10, alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: '1.7rem', fontWeight: 800, color: r.evaluation.is_satisfactory ? 'var(--green)' : 'var(--red)' }}>
                      {(r.evaluation.quality_score * 100).toFixed(0)}%
                    </div>
                    <div style={{ fontSize: '.62rem', color: 'var(--t3)' }}>Quality</div>
                  </div>
                  <span className={`bdg ${r.evaluation.is_satisfactory ? 'bdg-g' : 'bdg-r'}`} style={{ fontSize: '.78rem', padding: '4px 11px' }}>
                    {r.evaluation.is_satisfactory ? 'PASS' : 'FAIL'}
                  </span>
                </div>
                <div className="qbar">
                  <div className="qfill" style={{
                    width: `${r.evaluation.quality_score * 100}%`,
                    background: r.evaluation.quality_score >= .7 ? 'var(--green)' : r.evaluation.quality_score >= .4 ? 'var(--yellow)' : 'var(--red)',
                  }} />
                </div>
                {r.evaluation.feedback && <p style={{ marginTop: 12 }}>{r.evaluation.feedback}</p>}
                {r.evaluation.suggestions?.length > 0 && (
                  <ul style={{ paddingLeft: 18, marginTop: 8, fontSize: '.78rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {r.evaluation.suggestions.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                )}
              </>
            ) : 'No evaluation.')}

            {tab === 'viz' && (r.visualizations?.length
              ? r.visualizations.map((v, i) => <Viz key={i} config={v} />)
              : <span style={{ color: 'var(--t3)' }}>No visualizations generated.</span>)}

            {tab === 'trace' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {(r.agent_trace || []).map((t, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--bg0)', padding: '8px 12px', borderRadius: 'var(--rs)', border: '1px solid var(--bdr)' }}>
                    <span style={{ fontWeight: 500 }}>{t.agent}</span>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="bdg bdg-g">{t.status}</span>
                      <span style={{ fontFamily: 'var(--m)', fontSize: '.66rem', color: 'var(--t2)' }}>{t.elapsed_s}s</span>
                    </div>
                  </div>
                ))}
                {!(r.agent_trace?.length) && <span style={{ color: 'var(--t3)' }}>No trace.</span>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────────── */
export default function Results({ result: r }) {
  const [divePaper, setDivePaper] = useState(null);
  if (!r) return null;

  const papers = useMemo(() => extractPapers(r.api_results), [r.api_results]);
  const answer = r.final_answer || r.reasoning_output || '_No answer produced._';
  const qualityPct = r.evaluation ? (r.evaluation.quality_score * 100).toFixed(0) : null;
  const qClass = qualityPct >= 70 ? 'pill-g' : 'pill-o';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>

      {/* Answer */}
      <div>
        <div className="answer-head">
          <div className="dot d-gr"><Sparkles size={16} /></div>
          <h2>Answer</h2>
          <div className="answer-metrics">
            {qualityPct && <span className={`pill ${qClass}`}><BadgeCheck size={13} /> {qualityPct}% quality</span>}
            {papers.length > 0 && <span className="pill"><Library size={13} /> {papers.length} sources</span>}
          </div>
        </div>
        <div className="answer-card">
          <Markdown>{answer}</Markdown>
        </div>
      </div>

      {/* Sub-questions */}
      {r.sub_questions?.length > 0 && (
        <div>
          <div className="ref-heading" style={{ marginBottom: 12 }}>
            <Sparkles size={13} /> Explore the sub-questions
          </div>
          <div className="subq-list">
            {r.sub_questions.map((sq, i) => (
              <SubQItem
                key={i} index={i} question={sq.question}
                context={r.aggregated_context} apiResults={r.api_results}
                onDive={setDivePaper}
              />
            ))}
          </div>
        </div>
      )}

      {/* Referenced papers */}
      {papers.length > 0 && (
        <div className="ref-section">
          <div className="ref-heading"><Library size={13} /> Referenced papers · {papers.length}</div>
          <div className="ref-grid">
            {papers.map((p, i) => <PaperCard key={i} p={p} onDive={setDivePaper} />)}
          </div>
        </div>
      )}

      {/* Technical details */}
      <DetailsDrawer r={r} />

      {divePaper && <PaperDeepDive paper={divePaper} onClose={() => setDivePaper(null)} />}
    </div>
  );
}
