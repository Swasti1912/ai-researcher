import React, { useState } from 'react';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Workflow, BarChart3, X, Network, Sigma } from 'lucide-react';
import MermaidDiagram from './MermaidDiagram';
import Markdown from './Markdown';

const CHART_COLORS = ['#f2822c', '#2ecc71', '#4c8dff', '#e0b23a', '#f2545b', '#a07cff'];

/* ── Concept / workflow diagrams (Mermaid) ───────────────────────────── */
function DiagramsView({ diagrams }) {
  if (!diagrams.length) {
    return <div className="viz-empty"><Network size={26} /> No diagrams were generated for this paper.</div>;
  }
  return (
    <div className="diagrams-scroll">
      {diagrams.map((d, i) => (
        <div key={i} className="diagram-card">
          <div className="diagram-head">
            <div className="diagram-title">
              {d.title || `Diagram ${i + 1}`}
              {d.type && <span className="diagram-type-badge">{d.type}</span>}
            </div>
            {d.description && <div className="diagram-desc">{d.description}</div>}
          </div>
          <MermaidDiagram code={d.mermaid} />
        </div>
      ))}
    </div>
  );
}

/* ── Explained equations (KaTeX) ─────────────────────────────────────── */
function EquationsView({ equations }) {
  if (!equations.length) {
    return <div className="viz-empty"><Sigma size={26} /> No key equations found in this paper.</div>;
  }
  return (
    <div className="diagrams-scroll">
      {equations.map((eq, i) => (
        <div key={i} className="eq-card">
          <div className="eq-name">{eq.name}</div>
          <div className="eq-formula">
            <Markdown>{`$$${eq.latex}$$`}</Markdown>
          </div>
          {eq.explanation && <div className="eq-explain">{eq.explanation}</div>}
          {eq.terms?.length > 0 && (
            <div className="eq-terms">
              {eq.terms.map((t, j) => (
                <div key={j} className="eq-term">
                  <span className="eq-term-sym"><Markdown>{`$${t.symbol}$`}</Markdown></span>
                  <span className="eq-term-mean">{t.meaning}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Numeric result charts (Recharts) ────────────────────────────────── */
function ResultsCharts({ charts }) {
  if (!charts.length) {
    return (
      <div className="viz-empty">
        <BarChart3 size={26} />
        No numerical results found in this paper.
        <span style={{ fontSize: '.72rem', color: 'var(--t3)' }}>
          Charts appear when the paper reports specific numbers, percentages, or scores.
        </span>
      </div>
    );
  }
  return (
    <div className="viz-charts">
      {charts.map((chart, i) => (
        <div key={i} className="viz-chart-card">
          <div className="viz-chart-title">{chart.title}</div>
          <ResponsiveContainer width="100%" height={220}>
            {chart.type === 'pie' ? (
              <PieChart>
                <Pie data={chart.data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {chart.data.map((_, idx) => <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={{ background: 'var(--bg1)', border: '1px solid var(--bdr)', borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            ) : (
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <XAxis dataKey="name" tick={{ fill: 'var(--t2)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--t2)', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: 'var(--bg1)', border: '1px solid var(--bdr)', borderRadius: 8 }} cursor={{ fill: 'rgba(242,130,44,.08)' }} />
                <Bar dataKey="value" radius={[5, 5, 0, 0]}>
                  {chart.data.map((_, idx) => <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />)}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────────── */
export default function PaperVisualization({ data, onClose }) {
  const { concept_diagrams = [], equations = [], charts = [] } = data || {};
  const hasCharts = charts.length > 0;
  const hasEquations = equations.length > 0;
  const isEmpty = concept_diagrams.length === 0 && !hasEquations && !hasCharts;
  const [tab, setTab] = useState('diagrams');

  return (
    <div className="viz-panel">
      <div className="viz-header">
        <div className="viz-header-left">
          <Workflow className="viz-icon" />
          <div>
            <div className="viz-title">Concept Visualizations</div>
            <div className="viz-subtitle">Workflows &amp; diagrams explaining the paper</div>
          </div>
        </div>
        {onClose && <button className="btn btn-g viz-close" onClick={onClose}><X size={14} /> Close</button>}
      </div>

      {isEmpty && (
        <div className="viz-empty viz-empty-top">
          <Network size={30} />
          <div className="viz-empty-title">Nothing to visualize for this paper</div>
          <div className="viz-empty-sub">
            It doesn't contain diagrams, workflows, algorithms, or quantitative results to chart.
            Try <strong>Teach Me</strong> for a section-by-section explanation instead.
          </div>
        </div>
      )}

      {!isEmpty && (
        <div className="tabs" style={{ padding: '0 0 4px' }}>
          <button className={`tb ${tab === 'diagrams' ? 'on' : ''}`} onClick={() => setTab('diagrams')}>
            <Workflow size={13} style={{ verticalAlign: '-2px' }} /> Diagrams
            {concept_diagrams.length > 0 && <span className="bdg bdg-b" style={{ marginLeft: 5 }}>{concept_diagrams.length}</span>}
          </button>
          {hasEquations && (
            <button className={`tb ${tab === 'equations' ? 'on' : ''}`} onClick={() => setTab('equations')}>
              <Sigma size={13} style={{ verticalAlign: '-2px' }} /> Equations
              <span className="bdg bdg-o" style={{ marginLeft: 5 }}>{equations.length}</span>
            </button>
          )}
          <button className={`tb ${tab === 'charts' ? 'on' : ''}`} onClick={() => setTab('charts')}>
            <BarChart3 size={13} style={{ verticalAlign: '-2px' }} /> Charts
            {hasCharts && <span className="bdg bdg-g" style={{ marginLeft: 5 }}>{charts.length}</span>}
          </button>
        </div>
      )}

      {!isEmpty && (
        <div className="viz-content" style={{ height: 520 }}>
          {tab === 'diagrams' && <DiagramsView diagrams={concept_diagrams} />}
          {tab === 'equations' && <EquationsView equations={equations} />}
          {tab === 'charts' && <ResultsCharts charts={charts} />}
        </div>
      )}
    </div>
  );
}
