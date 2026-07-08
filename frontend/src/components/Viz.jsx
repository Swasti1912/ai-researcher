import React from 'react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const C = ['#e07520','#24b264','#3880e8','#d4a820','#d94040','#9b59b6'];

export default function Viz({ config }) {
  if (!config?.data) return null;
  const { type, title, data } = config;
  let d = Array.isArray(data) ? data
    : data.labels ? data.labels.map((l, i) => ({ name: l, value: data.values?.[i] || 0 }))
    : Object.entries(data).map(([k, v]) => ({ name: k, value: v }));
  if (!d.length) return null;
  const vk = Object.keys(d[0]).find(k => k !== 'name' && typeof d[0][k] === 'number') || 'value';
  const tip = { contentStyle: { background: 'var(--bg2)', border: '1px solid var(--bdr)', borderRadius: 6, fontSize: '.74rem' } };

  return (
    <div style={{ marginBottom: 16 }}>
      {title && <h5 style={{ fontSize: '.78rem', marginBottom: 8, color: 'var(--t1)' }}>{title}</h5>}
      <ResponsiveContainer width="100%" height={240}>
        {type === 'bar' ? (
          <BarChart data={d}><CartesianGrid strokeDasharray="3 3" stroke="var(--bdr)" />
            <XAxis dataKey="name" stroke="var(--t3)" fontSize={10} /><YAxis stroke="var(--t3)" fontSize={10} />
            <Tooltip {...tip} /><Bar dataKey={vk} fill="var(--orange)" radius={[3,3,0,0]} /></BarChart>
        ) : type === 'line' ? (
          <LineChart data={d}><CartesianGrid strokeDasharray="3 3" stroke="var(--bdr)" />
            <XAxis dataKey="name" stroke="var(--t3)" fontSize={10} /><YAxis stroke="var(--t3)" fontSize={10} />
            <Tooltip {...tip} /><Line type="monotone" dataKey={vk} stroke="var(--orange)" strokeWidth={2} /></LineChart>
        ) : type === 'pie' ? (
          <PieChart><Pie data={d} dataKey={vk} nameKey="name" cx="50%" cy="50%" outerRadius={85} label>
            {d.map((_, i) => <Cell key={i} fill={C[i % C.length]} />)}</Pie>
            <Tooltip {...tip} /><Legend /></PieChart>
        ) : <pre style={{ fontSize: '.72rem' }}>{JSON.stringify(config, null, 2)}</pre>}
      </ResponsiveContainer>
    </div>
  );
}
