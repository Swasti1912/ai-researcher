import React from 'react';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const COLORS = ['#e87a20', '#2db86a', '#3d8ef0', '#e8b830', '#e54d4d', '#9b59b6'];

export default function VisualizationChart({ config }) {
  if (!config || !config.data) {
    return <p style={{ color: 'var(--text-3)', fontSize: '.8rem' }}>Invalid chart config</p>;
  }

  const { type, title, data } = config;

  // Normalise data: accept array or {labels, values}
  let chartData = [];
  if (Array.isArray(data)) {
    chartData = data;
  } else if (data.labels && data.values) {
    chartData = data.labels.map((l, i) => ({ name: l, value: data.values[i] || 0 }));
  } else if (typeof data === 'object') {
    chartData = Object.entries(data).map(([k, v]) => ({ name: k, value: v }));
  }

  if (!chartData.length) return null;

  // Detect keys for bar/line
  const keys = Object.keys(chartData[0]).filter(k => k !== 'name' && typeof chartData[0][k] === 'number');
  const valueKey = keys[0] || 'value';

  return (
    <div style={{ marginBottom: 20 }}>
      {title && <h5 style={{ fontSize: '.82rem', marginBottom: 10, color: 'var(--text-1)' }}>{title}</h5>}
      <ResponsiveContainer width="100%" height={260}>
        {type === 'bar' ? (
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" stroke="var(--text-3)" fontSize={11} />
            <YAxis stroke="var(--text-3)" fontSize={11} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '.78rem' }}
            />
            <Bar dataKey={valueKey} fill="var(--orange)" radius={[4, 4, 0, 0]} />
          </BarChart>
        ) : type === 'line' ? (
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" stroke="var(--text-3)" fontSize={11} />
            <YAxis stroke="var(--text-3)" fontSize={11} />
            <Tooltip
              contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '.78rem' }}
            />
            <Line type="monotone" dataKey={valueKey} stroke="var(--orange)" strokeWidth={2} dot={{ fill: 'var(--orange)' }} />
          </LineChart>
        ) : type === 'pie' ? (
          <PieChart>
            <Pie data={chartData} dataKey={valueKey} nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
              {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6, fontSize: '.78rem' }}
            />
            <Legend />
          </PieChart>
        ) : type === 'table' ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '.78rem', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {Object.keys(chartData[0]).map(k => (
                    <th key={k} style={{ textAlign: 'left', padding: '6px 10px', borderBottom: '1px solid var(--border)', color: 'var(--text-2)' }}>
                      {k}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chartData.map((row, i) => (
                  <tr key={i}>
                    {Object.values(row).map((v, j) => (
                      <td key={j} style={{ padding: '6px 10px', borderBottom: '1px solid var(--border)', color: 'var(--text-1)' }}>
                        {String(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <pre style={{ fontSize: '.76rem' }}>{JSON.stringify(config, null, 2)}</pre>
        )}
      </ResponsiveContainer>
    </div>
  );
}
