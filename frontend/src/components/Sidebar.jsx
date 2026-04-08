import React from 'react';
import Pipeline from './Pipeline';

export default function Sidebar({ steps, active, done, loading, result: r }) {
  const sqN = r?.sub_questions?.length || 0;
  const srcs = r?.sub_questions ? new Set(r.sub_questions.map(s => s.api_source)).size : 0;
  const score = r?.evaluation?.quality_score;
  const apiErr = r?.api_results?.filter(x => x.error)?.length || 0;
  const apiN = r?.api_results?.length || 0;

  return (
    <>
      <div><div className="sec-title">Pipeline</div>
        <Pipeline steps={steps} active={active} done={done} loading={loading} /></div>

      <div><div className="sec-title">Metrics</div>
        <div className="stats">
          <div className="st"><div className="n">{sqN}</div><div className="l">Sub-Q</div></div>
          <div className="st"><div className="n">{srcs}</div><div className="l">Sources</div></div>
          <div className="st"><div className="n" style={{ color: score != null && score >= .7 ? 'var(--green)' : undefined }}>
            {score != null ? `${(score * 100).toFixed(0)}%` : '—'}</div><div className="l">Quality</div></div>
          <div className="st"><div className="n">{r?.status === 'completed' ? '✓' : loading ? '…' : '—'}</div><div className="l">Status</div></div>
        </div></div>

      {r?.intent && (
        <div><div className="sec-title">Intent</div>
          <div className="card" style={{ padding: 11 }}>
            <div style={{ fontSize: '.76rem', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div><span style={{ color: 'var(--t3)' }}>Type: </span><span className="bdg bdg-o">{r.intent.primary_intent}</span></div>
              <div><span style={{ color: 'var(--t3)' }}>Domain: </span><b>{r.intent.research_domain || 'N/A'}</b></div>
              <div><span style={{ color: 'var(--t3)' }}>Confidence: </span><b>{(r.intent.confidence * 100).toFixed(0)}%</b></div>
              {r.intent.sub_intents?.length > 0 && <div><span style={{ color: 'var(--t3)' }}>Tags: </span>
                {r.intent.sub_intents.map((t, i) => <span key={i} className="bdg bdg-g" style={{ marginRight: 3 }}>{t}</span>)}</div>}
            </div>
          </div></div>
      )}

      {apiN > 0 && (
        <div><div className="sec-title">API Results</div>
          <div className="card" style={{ padding: 11, fontSize: '.74rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Total</span><b>{apiN}</b></div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}><span>OK</span><b style={{ color: 'var(--green)' }}>{apiN - apiErr}</b></div>
            {apiErr > 0 && <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}><span>Errors</span><b style={{ color: 'var(--red)' }}>{apiErr}</b></div>}
          </div></div>
      )}

      {!r && !loading && (
        <div><div className="sec-title">Guide</div>
          <div className="card" style={{ padding: 12, fontSize: '.76rem', color: 'var(--t2)' }}>
            <p>Enter a research question and press <b>Run Research</b>.</p>
            <p style={{ marginTop: 6 }}>Optionally upload a PDF paper for context-aware answers.</p>
          </div></div>
      )}
    </>
  );
}
