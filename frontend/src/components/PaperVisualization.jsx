import React, { useState, useMemo } from 'react';
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

// ── Colour palettes ───────────────────────────────────────────────────────────

const CONCEPT_COLORS = {
  concept:  { bg: 'rgba(224,117,32,.18)', border: '#e07520', text: '#f0993a' },
  finding:  { bg: 'rgba(36,178,100,.18)', border: '#24b264', text: '#48d480' },
  method:   { bg: 'rgba(56,128,232,.18)', border: '#3880e8', text: '#6aa0f0' },
  theory:   { bg: 'rgba(212,168,32,.18)', border: '#d4a820', text: '#e8c840' },
  step:     { bg: 'rgba(56,128,232,.18)', border: '#3880e8', text: '#6aa0f0' },
  default:  { bg: 'rgba(30,48,80,.6)',    border: '#1e3050', text: '#b0bdd4' },
};

const ARCH_COLORS = {
  input:         { bg: 'rgba(110,130,166,.22)', border: '#6e82a6', text: '#c0cce0' },
  embedding:     { bg: 'rgba(56,128,232,.22)',  border: '#3880e8', text: '#7ab0f8' },
  attention:     { bg: 'rgba(224,117,32,.28)',  border: '#e07520', text: '#f5a84a' },
  feedforward:   { bg: 'rgba(36,178,100,.22)',  border: '#24b264', text: '#4cd480' },
  normalization: { bg: 'rgba(212,168,32,.22)',  border: '#d4a820', text: '#e8c840' },
  encoder:       { bg: 'rgba(56,128,232,.14)',  border: '#3880e8', text: '#7ab0f8' },
  decoder:       { bg: 'rgba(224,117,32,.14)',  border: '#e07520', text: '#f5a84a' },
  conv:          { bg: 'rgba(56,196,196,.22)',  border: '#38c4c4', text: '#60e0e0' },
  pooling:       { bg: 'rgba(148,56,232,.22)',  border: '#9438e8', text: '#c088f8' },
  output:        { bg: 'rgba(36,178,100,.30)',  border: '#1ecc78', text: '#48e880' },
  linear:        { bg: 'rgba(56,128,232,.22)',  border: '#3880e8', text: '#7ab0f8' },
  general:       { bg: 'rgba(30,48,80,.6)',     border: '#1e3050', text: '#b0bdd4' },
  default:       { bg: 'rgba(30,48,80,.6)',     border: '#1e3050', text: '#b0bdd4' },
};

const CHART_COLORS = ['#e07520','#24b264','#3880e8','#d4a820','#d94040','#6e82a6'];

// ── Layout helpers ────────────────────────────────────────────────────────────

function circularLayout(nodes) {
  if (!nodes.length) return [];
  const cx = 400, cy = 280, r = 220;
  return nodes.map((n, i) => {
    if (i === 0) return { ...n, position: { x: cx, y: cy } };
    const angle = (2 * Math.PI * (i - 1)) / (nodes.length - 1) - Math.PI / 2;
    return { ...n, position: { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) } };
  });
}

function linearLayout(nodes) {
  return nodes.map((n, i) => ({ ...n, position: { x: 320, y: i * 110 + 40 } }));
}

/**
 * Layered layout for architecture diagrams.
 * Groups nodes by their `layer` integer, places each group as a horizontal
 * row, with rows spaced vertically from top (layer 0) to bottom.
 */
function layeredLayout(nodes) {
  if (!nodes.length) return [];

  // Group by layer
  const groups = {};
  for (const n of nodes) {
    const l = typeof n.layer === 'number' ? n.layer : 0;
    if (!groups[l]) groups[l] = [];
    groups[l].push(n);
  }

  const sortedLayers = Object.keys(groups).map(Number).sort((a, b) => a - b);
  const NODE_W = 180, NODE_H = 60, H_GAP = 24, V_GAP = 90;
  const positioned = [];

  sortedLayers.forEach((layerIdx, rowNum) => {
    const group = groups[layerIdx];
    const totalW = group.length * NODE_W + (group.length - 1) * H_GAP;
    const startX = (800 - totalW) / 2;
    const y = rowNum * (NODE_H + V_GAP) + 20;

    group.forEach((n, colNum) => {
      positioned.push({
        ...n,
        position: { x: startX + colNum * (NODE_W + H_GAP), y },
      });
    });
  });

  return positioned;
}

// ── Node/edge builders ────────────────────────────────────────────────────────

function buildConceptNodes(rawNodes, fallbackType = 'concept') {
  return rawNodes.map(n => {
    const c = CONCEPT_COLORS[n.type] || CONCEPT_COLORS[fallbackType] || CONCEPT_COLORS.default;
    return {
      id: n.id,
      data: { label: n.label, description: n.description },
      style: {
        background: c.bg, border: `1.5px solid ${c.border}`,
        borderRadius: 8, color: c.text,
        fontFamily: "'Sora', system-ui, sans-serif",
        fontSize: 12, fontWeight: 600,
        padding: '8px 14px', maxWidth: 160, textAlign: 'center',
      },
    };
  });
}

function buildArchNodes(rawNodes) {
  return rawNodes.map(n => {
    const c = ARCH_COLORS[n.type] || ARCH_COLORS.default;
    const isWide = ['encoder', 'decoder', 'attention', 'feedforward'].includes(n.type);
    return {
      id: n.id,
      data: {
        label: (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 700, fontSize: 11, lineHeight: 1.3 }}>{n.label}</div>
            {n.description && (
              <div style={{ fontSize: 9, opacity: 0.75, marginTop: 3, lineHeight: 1.3, whiteSpace: 'pre-wrap' }}>
                {n.description.slice(0, 80)}
              </div>
            )}
          </div>
        ),
      },
      style: {
        background: c.bg, border: `2px solid ${c.border}`,
        borderRadius: 10, color: c.text,
        fontFamily: "'Sora', system-ui, sans-serif",
        width: isWide ? 200 : 165,
        padding: '10px 12px',
        boxShadow: `0 0 12px ${c.border}33`,
      },
    };
  });
}

function buildEdges(rawEdges, opts = {}) {
  const { animated = false, color = '#1e3050' } = opts;
  return rawEdges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label || '',
    animated,
    markerEnd: { type: MarkerType.ArrowClosed, color },
    style: { stroke: color, strokeWidth: 1.8 },
    labelStyle: { fill: '#6e82a6', fontSize: 10, fontFamily: 'Fira Code, monospace' },
    labelBgStyle: { fill: '#0b1120', fillOpacity: 0.85 },
  }));
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ArchitectureGraph({ data }) {
  const { title = '', nodes: rawNodes = [], edges: rawEdges = [] } = data;

  const positioned = useMemo(() => layeredLayout(buildArchNodes(rawNodes)), [rawNodes]);
  const flowEdges = useMemo(() => buildEdges(rawEdges, { animated: true, color: '#3880e8' }), [rawEdges]);

  const [nodes, , onNodesChange] = useNodesState(positioned);
  const [edges, , onEdgesChange] = useEdgesState(flowEdges);

  if (!rawNodes.length) {
    return <div className="viz-empty">No architecture data extracted for this paper</div>;
  }

  // Build layer legend
  const typeSet = [...new Set(rawNodes.map(n => n.type).filter(Boolean))];

  return (
    <div className="viz-flow-wrap">
      {title && (
        <div className="arch-title">{title}</div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
        nodesDraggable
      >
        <Background color="#1e3050" gap={24} size={1} />
        <Controls showInteractive={false} style={{ background: '#0b1120', border: '1px solid #1e3050' }} />
        <MiniMap
          nodeColor={n => n.style?.border || '#1e3050'}
          maskColor="rgba(6,10,17,.7)"
          style={{ background: '#0b1120', border: '1px solid #1e3050' }}
        />
      </ReactFlow>
      <div className="viz-legend">
        {typeSet.map(t => {
          const c = ARCH_COLORS[t] || ARCH_COLORS.default;
          return (
            <span key={t} className="viz-legend-item">
              <span className="viz-legend-dot" style={{ background: c.border }} />
              {t}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function ConceptFlowGraph({ rawNodes, rawEdges, layout = 'circular', animated = false }) {
  const positioned = useMemo(() => {
    const built = buildConceptNodes(rawNodes);
    return layout === 'circular' ? circularLayout(built) : linearLayout(built);
  }, [rawNodes, layout]);

  const flowEdges = useMemo(() => buildEdges(rawEdges, { animated }), [rawEdges, animated]);

  const [nodes, , onNodesChange] = useNodesState(positioned);
  const [edges, , onEdgesChange] = useEdgesState(flowEdges);

  if (!rawNodes.length) return <div className="viz-empty">No data extracted for this view</div>;

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
      {layout === 'circular' && (
        <div className="viz-legend">
          {Object.entries(CONCEPT_COLORS).filter(([k]) => k !== 'default' && k !== 'step').map(([k, v]) => (
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
          Results charts appear when the paper contains specific numbers, percentages, or scores.
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
                <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #1e3050', borderRadius: 6 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            ) : (
              <BarChart data={chart.data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <XAxis dataKey="name" tick={{ fill: '#6e82a6', fontSize: 11 }} />
                <YAxis tick={{ fill: '#6e82a6', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#111b2e', border: '1px solid #1e3050', borderRadius: 6 }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
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

// ── Main component ────────────────────────────────────────────────────────────

const TABS = [
  { key: 'arch',    icon: '🏗️', label: 'Architecture' },
  { key: 'concept', icon: '🔗', label: 'Concept Map'  },
  { key: 'method',  icon: '⚙️', label: 'Method Flow'  },
  { key: 'results', icon: '📊', label: 'Results'      },
];

export default function PaperVisualization({ data, onClose }) {
  const [tab, setTab] = useState('arch');

  const { architecture_diagram = {}, concept_map = {}, method_flow = {}, charts = [] } = data;

  const hasArch    = (architecture_diagram.nodes || []).length > 0;
  const hasConcept = (concept_map.nodes || []).length > 0;
  const hasMethod  = (method_flow.nodes || []).length > 0;
  const hasCharts  = charts.length > 0;

  return (
    <div className="viz-panel">
      <div className="viz-header">
        <div className="viz-header-left">
          <span className="viz-icon">🗺️</span>
          <div>
            <div className="viz-title">Paper Visualization</div>
            <div className="viz-subtitle">Architecture · Concept map · Method flow · Results</div>
          </div>
        </div>
        {onClose && <button className="btn btn-g viz-close" onClick={onClose}>✕ Close</button>}
      </div>

      <div className="tabs" style={{ padding: '0 0 4px' }}>
        {TABS.map(t => (
          <button key={t.key} className={`tb ${tab === t.key ? 'on' : ''}`} onClick={() => setTab(t.key)}>
            {t.icon} {t.label}
            {t.key === 'results' && hasCharts && (
              <span className="bdg bdg-g" style={{ marginLeft: 5 }}>{charts.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="viz-content">
        {tab === 'arch'    && <ArchitectureGraph data={architecture_diagram} />}
        {tab === 'concept' && (
          <ConceptFlowGraph
            rawNodes={concept_map.nodes || []}
            rawEdges={concept_map.edges || []}
            layout="circular"
          />
        )}
        {tab === 'method' && (
          <ConceptFlowGraph
            rawNodes={method_flow.nodes || []}
            rawEdges={method_flow.edges || []}
            layout="linear"
            animated
          />
        )}
        {tab === 'results' && <ResultsCharts charts={charts} />}
      </div>
    </div>
  );
}
