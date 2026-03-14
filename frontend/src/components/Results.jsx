import React, { useState } from 'react';
import Viz from './Viz';

const TABS = [
  { k: 'answer', l: 'Answer' }, { k: 'intent', l: 'Intent' },
  { k: 'subq', l: 'Sub-Questions' }, { k: 'ctx', l: 'API Context' },
  { k: 'eval', l: 'Evaluation' }, { k: 'viz', l: 'Visualizations' },
  { k: 'trace', l: 'Trace' },
];

export default function Results({ result: r }) {
  const [tab, setTab] = useState('answer');
  if (!r) return null;

  return (
    <div>
      <div className="tabs">{TABS.map(t => (
        <button key={t.k} className={`tb${tab === t.k ? ' on' : ''}`} onClick={() => setTab(t.k)}>{t.l}</button>
      ))}</div>

      {tab === 'answer' && (
        <div className="card">
          <div className="card-h"><div className="dot d-gr">✦</div><h4>Research Answer</h4>
            {r.status === 'completed' && <span className="bdg bdg-g">Done</span>}</div>
          <div className="card-b">
            {r.refined_query && <p style={{ color: 'var(--t3)', fontSize: '.72rem', marginBottom: 8, fontStyle: 'italic' }}>Refined: {r.refined_query}</p>}
            <div style={{ whiteSpace: 'pre-wrap' }}>{r.final_answer || r.reasoning_output || 'No answer.'}</div>
            {r.rag_references?.length > 0 && (
              <div style={{ marginTop: 12, paddingTop: 8, borderTop: '1px solid var(--bdr)' }}>
                <span style={{ fontSize: '.68rem', color: 'var(--t3)' }}>Refs: </span>
                {r.rag_references.map((x, i) => <span key={i} className="bdg bdg-o" style={{ marginRight: 3 }}>{x}</span>)}
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
    </div>
  );
}
