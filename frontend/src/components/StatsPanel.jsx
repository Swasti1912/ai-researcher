import React from 'react';

export default function StatsPanel({ result, loading }) {
  if (!result && !loading) {
    return (
      <div>
        <h3>Overview</h3>
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 32 }}>
          Submit a query to see pipeline metrics
        </div>
      </div>
    );
  }

  const subQCount = result?.sub_questions?.length || 0;
  const apiCount = result?.sub_questions?.reduce(
    (s, sq) => s.add(sq.api_source) && s, new Set()
  )?.size || 0;
  const score = result?.evaluation?.quality_score;
  const iterations = result?.evaluation ? 1 : 0;

  return (
    <div>
      <h3>Metrics</h3>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{subQCount}</div>
          <div className="label">Sub-Questions</div>
        </div>
        <div className="stat-card">
          <div className="value">{apiCount}</div>
          <div className="label">API Sources</div>
        </div>
        <div className="stat-card">
          <div className="value">{score != null ? `${(score * 100).toFixed(0)}%` : '—'}</div>
          <div className="label">Quality Score</div>
        </div>
        <div className="stat-card">
          <div className="value">{result?.status === 'completed' ? '✓' : loading ? '…' : '—'}</div>
          <div className="label">Status</div>
        </div>
      </div>

      {result?.intent && (
        <div style={{ marginTop: 16 }}>
          <h3>Intent</h3>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ fontSize: '0.82rem' }}>
              <strong>Type:</strong> {result.intent.primary_intent}
            </div>
            <div style={{ fontSize: '0.82rem', marginTop: 4 }}>
              <strong>Domain:</strong> {result.intent.research_domain || 'N/A'}
            </div>
            <div style={{ fontSize: '0.82rem', marginTop: 4 }}>
              <strong>Confidence:</strong> {(result.intent.confidence * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
