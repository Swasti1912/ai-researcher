import React, { useState, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

// ── Colour palette matching the app theme ────────────────────────────────────
const TYPE_COLORS = {
  concept:  { bg: 'rgba(224,117,32,.18)', border: '#e07520', text: '#f0993a' },
  finding:  { bg: 'rgba(36,178,100,.18)', border: '#24b264', text: '#48d480' },
  method:   { bg: 'rgba(56,128,232,.18)', border: '#3880e8', text: '#6aa0f0' },
  theory:   { bg: 'rgba(212,168,32,.18)', border: '#d4a820', text: '#e8c840' },
  step:     { bg: 'rgba(56,128,232,.18)', border: '#3880e8', text: '#6aa0f0' },
  default:  { bg: 'rgba(30,48,80,.6)',    border: '#1e3050', text: '#b0bdd4' },
};
const CHART_COLORS = ['#e07520','#24b264','#3880e8','#d4a820','#d94040','#6e82a6'];

const TABS = ['Concept Map', 'Method Flow', 'Results'];

// ── Layout helpers ────────────────────────────────────────────────────────────

/** Circular layout: first node at centre, rest around it */
function circularLayout(nodes) {
  if (!nodes.length) return [];
  const cx = 400, cy = 280, r = 220;
  return nodes.map((n, i) => {
    let x, y;
    if (i === 0) { x = cx; y = cy; }
    else {
      const angle = (2 * Math.PI * (i - 1)) / (nodes.length - 1) - Math.PI / 2;
      x = cx + r * Math.cos(angle);
      y = cy + r * Math.sin(angle);
    }
    return { ...n, position: { x, y } };
  });
}

/** Top-to-bottom linear layout for method steps */
function linearLayout(nodes) {
  return nodes.map((n, i) => ({
    ...n,
    position: { x: 320, y: i * 110 + 40 },
  }));
}

// ── Node/edge builders ────────────────────────────────────────────────────────

function buildFlowNodes(rawNodes, type = 'concept') {
  return rawNodes.map(n => {
    const c = TYPE_COLORS[n.type] || TYPE_COLORS[type] || TYPE_COLORS.default;
    return {
      id: n.id,
      data: { label: n.label, description: n.description },
      style: {
        background: c.bg,
        border: `1.5px solid ${c.border}`,
        borderRadius: 8,
        color: c.text,
        fontFamily: "'Sora', system-ui, sans-serif",
        fontSize: 12,
        fontWeight: 600,
        padding: '8px 14px',
        maxWidth: 160,
        textAlign: 'center',
      },
    };
  });
}

function buildFlowEdges(rawEdges, animated = false) {
  return rawEdges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || '',
    animated,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#1e3050' },
    style: { stroke: '#1e3050', strokeWidth: 1.5 },
    labelStyle: { fill: '#6e82a6', fontSize: 10, fontFamily: 'Fira Code, monospace' },
    labelBgStyle: { fill: '#0b1120', fillOpacity: 0.8 },
  }));
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function FlowGraph({ rawNodes, rawEdges, layout = 'circular', animated = false }) {
  const positioned = layout === 'circular'
    ? circularLayout(buildFlowNodes(rawNodes, 'concept'))
    : linearLayout(buildFlowNodes(rawNodes, 'step'));

  const [nodes, , onNodesChange] = useNodesState(positioned);
  const [edges, , onEdgesChange] = useEdgesState(buildFlowEdges(rawEdges, animated));

  if (!rawNodes.length) {
    return <div className="viz-empty">No data extracted for this view</div>;
  }

  return (
    <div className="viz-flow-wrap">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e3050" gap={20} size={1} />
        <Controls showInteractive={false} style={{ background: '#0b1120', border: '1px solid #1e3050' }} />
        <MiniMap
          nodeColor={n => n.style?.border || '#1e3050'}
          maskColor="rgba(6,10,17,.7)"
          style={{ background: '#0b1120', border: '1px solid #1e3050' }}
        />
      </ReactFlow>
      {/* Legend for concept map */}
      {layout === 'circular' && (
        <div className="viz-legend">
          {Object.entries(TYPE_COLORS).filter(([k]) => k !== 'default' && k !== 'step').map(([k, v]) => (
            <span key={k} className="viz-legend-item">
              <span className="viz-legend-dot" style={{ background: v.border }} />
              {k}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ResultsCharts({ charts }) {
  if (!charts.length) {
    return (
      <div className="viz-empty">
        No numerical data found in this paper.<br />
        <span style={{ fontSize: '.72rem', color: 'var(--t3)' }}>
          Results charts only appear when the paper contains specific numbers, percentages, or scores.
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
                  {chart.data.map((_, idx) => (
                    <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #1e3050', borderRadius: 6 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            ) : (
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <XAxis dataKey="name" tick={{ fill: '#6e82a6', fontSize: 11 }} />
                <YAxis tick={{ fill: '#6e82a6', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #1e3050', borderRadius: 6 }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chart.data.map((_, idx) => (
                    <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PaperVisualization({ data, onClose }) {
  const [tab, setTab] = useState(0);

  const { concept_map = {}, method_flow = {}, charts = [] } = data;

  return (
    <div className="viz-panel">
      <div className="viz-header">
        <div className="viz-header-left">
          <span className="viz-icon">🗺️</span>
          <div>
            <div className="viz-title">Paper Visualization</div>
            <div className="viz-subtitle">Concept map · Method flow · Results</div>
          </div>
        </div>
        <button className="btn btn-g viz-close" onClick={onClose}>✕ Close</button>
      </div>

      <div className="tabs" style={{ padding: '0 0 4px' }}>
        {TABS.map((t, i) => (
          <button key={i} className={`tb ${tab === i ? 'on' : ''}`} onClick={() => setTab(i)}>
            {i === 0 && '🔗 '}{i === 1 && '⚙️ '}{i === 2 && '📊 '}{t}
            {i === 2 && charts.length > 0 && (
              <span className="bdg bdg-g" style={{ marginLeft: 5 }}>{charts.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="viz-content">
        {tab === 0 && (
          <FlowGraph
            rawNodes={concept_map.nodes || []}
            rawEdges={concept_map.edges || []}
            layout="circular"
          />
        )}
        {tab === 1 && (
          <FlowGraph
            rawNodes={method_flow.nodes || []}
            rawEdges={method_flow.edges || []}
            layout="linear"
            animated
          />
        )}
        {tab === 2 && <ResultsCharts charts={charts} />}
      </div>
    </div>
  );
}
