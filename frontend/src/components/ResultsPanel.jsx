import React, { useState } from 'react';
import VisualizationChart from './VisualizationChart';

const TABS = [
  { key: 'answer', label: 'Answer' },
  { key: 'intent', label: 'Intent' },
  { key: 'subq', label: 'Sub-Questions' },
  { key: 'context', label: 'API Context' },
  { key: 'eval', label: 'Evaluation' },
  { key: 'viz', label: 'Visualizations' },
  { key: 'trace', label: 'Agent Trace' },
];

export default function ResultsPanel({ result }) {
  const [tab, setTab] = useState('answer');
  if (!result) return null;

  return (
    <div>
      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'answer' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-green">✦</div>
            <h4>Research Answer</h4>
            {result.status === 'completed' && <span className="badge badge-green">Completed</span>}
          </div>
          <div className="card-body">
            {result.refined_query && (
              <p style={{ color: 'var(--text-3)', fontSize: '.76rem', marginBottom: 10, fontStyle: 'italic' }}>
                Refined: {result.refined_query}
              </p>
            )}
            <div style={{ whiteSpace: 'pre-wrap' }}>
              {result.final_answer || result.reasoning_output || 'No answer generated.'}
            </div>
            {result.rag_references?.length > 0 && (
              <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                <span style={{ fontSize: '.72rem', color: 'var(--text-3)' }}>References: </span>
                {result.rag_references.map((r, i) => (
                  <span key={i} className="badge badge-orange" style={{ marginRight: 4 }}>{r}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'intent' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-blue">◎</div>
            <h4>Intent Classification</h4>
          </div>
          <div className="card-body">
            {result.intent ? (
              <pre>{JSON.stringify(result.intent, null, 2)}</pre>
            ) : 'No intent data.'}
          </div>
        </div>
      )}

      {tab === 'subq' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-orange">⊞</div>
            <h4>Decomposed Sub-Questions</h4>
          </div>
          <div className="card-body">
            {result.sub_questions?.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {result.sub_questions.map((sq, i) => (
                  <div key={i} style={{
                    background: 'var(--bg-0)', padding: '10px 14px',
                    borderRadius: 'var(--radius-sm)', display: 'flex', gap: 10, alignItems: 'flex-start'
                  }}>
                    <span style={{ color: 'var(--orange)', fontWeight: 700, fontFamily: 'var(--mono)', fontSize: '.75rem', minWidth: 20 }}>
                      #{sq.priority || i + 1}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div>{sq.question}</div>
                      <span className="badge badge-orange" style={{ marginTop: 4 }}>{sq.api_source}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : 'No sub-questions.'}
          </div>
        </div>
      )}

      {tab === 'context' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-blue">⊕</div>
            <h4>Aggregated API Context</h4>
          </div>
          <div className="card-body">
            <div style={{ whiteSpace: 'pre-wrap', maxHeight: 500, overflow: 'auto' }}>
              {result.aggregated_context || 'No context available.'}
            </div>
            {result.api_results?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <span style={{ fontSize: '.72rem', color: 'var(--text-3)' }}>
                  API calls: {result.api_results.length} | 
                  Errors: {result.api_results.filter(r => r.error).length}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'eval' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-green">✓</div>
            <h4>Quality Evaluation</h4>
          </div>
          <div className="card-body">
            {result.evaluation ? (
              <>
                <div style={{ display: 'flex', gap: 24, marginBottom: 14 }}>
                  <div>
                    <div style={{
                      fontSize: '1.8rem', fontWeight: 700,
                      color: result.evaluation.is_satisfactory ? 'var(--green)' : 'var(--red)'
                    }}>
                      {(result.evaluation.quality_score * 100).toFixed(0)}%
                    </div>
                    <div style={{ fontSize: '.68rem', color: 'var(--text-3)' }}>Quality Score</div>
                  </div>
                  <div>
                    <div className={`badge ${result.evaluation.is_satisfactory ? 'badge-green' : 'badge-red'}`} style={{ fontSize: '.85rem', padding: '4px 12px' }}>
                      {result.evaluation.is_satisfactory ? 'PASS' : 'FAIL'}
                    </div>
                  </div>
                </div>
                <div className="quality-bar">
                  <div
                    className="quality-fill"
                    style={{
                      width: `${result.evaluation.quality_score * 100}%`,
                      background: result.evaluation.quality_score >= 0.7
                        ? 'var(--green)' : result.evaluation.quality_score >= 0.4
                        ? 'var(--yellow)' : 'var(--red)',
                    }}
                  />
                </div>
                {result.evaluation.feedback && (
                  <p style={{ marginTop: 12 }}>{result.evaluation.feedback}</p>
                )}
                {result.evaluation.suggestions?.length > 0 && (
                  <div style={{ marginTop: 10 }}>
                    <strong style={{ fontSize: '.78rem' }}>Suggestions:</strong>
                    <ul style={{ paddingLeft: 18, marginTop: 4, fontSize: '.82rem' }}>
                      {result.evaluation.suggestions.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
              </>
            ) : 'No evaluation data.'}
          </div>
        </div>
      )}

      {tab === 'viz' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-yellow">📊</div>
            <h4>Visualizations</h4>
          </div>
          <div className="card-body">
            {result.visualizations?.length ? (
              result.visualizations.map((v, i) => (
                <VisualizationChart key={i} config={v} />
              ))
            ) : 'No visualizations generated.'}
          </div>
        </div>
      )}

      {tab === 'trace' && (
        <div className="card">
          <div className="card-head">
            <div className="dot dot-blue">⏱</div>
            <h4>Agent Execution Trace</h4>
          </div>
          <div className="card-body">
            {result.agent_trace?.length ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {result.agent_trace.map((t, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    background: 'var(--bg-0)', padding: '8px 12px', borderRadius: 'var(--radius-sm)'
                  }}>
                    <span style={{ fontWeight: 500 }}>{t.agent}</span>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <span className="badge badge-green">{t.status}</span>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: '.72rem', color: 'var(--text-2)' }}>
                        {t.elapsed_s}s
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : 'No trace data.'}
          </div>
        </div>
      )}
    </div>
  );
}
