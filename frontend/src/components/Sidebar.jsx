import React from 'react';
import Pipeline from './Pipeline';

export default function Sidebar({ steps, active, done, loading, result: r }) {
  const sqN = r?.sub_questions?.length || 0;
  const srcs = r?.sub_questions ? new Set(r.sub_questions.map(s => s.api_source)).size : 0;
  const score = r?.evaluation?.quality_score;

  return (
    <>
      <div>
        <div className="sec-title">Metrics</div>
        <div className="stats">
          <div className="st"><div className="n">{sqN}</div><div className="l">Sub-Q</div></div>
          <div className="st"><div className="n">{srcs}</div><div className="l">Sources</div></div>
          <div className="st">
            <div className="n" style={{ color: score != null && score >= 0.7 ? 'var(--green)' : undefined }}>
              {score != null ? `${(score * 100).toFixed(0)}%` : '—'}
            </div>
            <div className="l">Quality</div>
          </div>
          <div className="st">
            <div className="n" style={{ color: r?.status === 'completed' ? 'var(--green)' : undefined }}>
              {r?.status === 'completed' ? '✓' : loading ? '…' : '—'}
            </div>
            <div className="l">Status</div>
          </div>
        </div>
      </div>

      <div>
        <div className="sec-title">Pipeline</div>
        <Pipeline steps={steps} active={active} done={done} loading={loading} />
      </div>

      {r?.intent && (
        <div>
          <div className="sec-title">Intent</div>
          <div className="card" style={{ padding: 13, boxShadow: 'none' }}>
            <div style={{ fontSize: '.78rem', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div><span style={{ color: 'var(--t3)' }}>Type </span><span className="bdg bdg-o">{r.intent.primary_intent}</span></div>
              <div><span style={{ color: 'var(--t3)' }}>Domain </span><b>{r.intent.research_domain || 'N/A'}</b></div>
              <div><span style={{ color: 'var(--t3)' }}>Confidence </span><b>{(r.intent.confidence * 100).toFixed(0)}%</b></div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
