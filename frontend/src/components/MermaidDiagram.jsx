import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import { AlertTriangle, Code2 } from 'lucide-react';

let _id = 0;

/** Track the app theme (data-theme on <html>) so diagrams recolor live. */
function useAppTheme() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute('data-theme') || 'dark'
  );
  useEffect(() => {
    const obs = new MutationObserver(() =>
      setTheme(document.documentElement.getAttribute('data-theme') || 'dark')
    );
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  return theme;
}

const themeVars = (dark) => dark ? {
  background: '#131a29',
  primaryColor: '#1a2336',
  primaryBorderColor: '#f2822c',
  primaryTextColor: '#f3f6fc',
  secondaryColor: '#16233b',
  tertiaryColor: '#0e1420',
  lineColor: '#5a76a8',
  fontSize: '14px',
  fontFamily: "'Sora', system-ui, sans-serif",
  clusterBkg: 'rgba(76,141,255,.08)',
  clusterBorder: '#2f3d5a',
  actorBkg: '#1a2336',
  actorBorder: '#f2822c',
  actorTextColor: '#f3f6fc',
  signalColor: '#c3ccdb',
  signalTextColor: '#c3ccdb',
  noteBkgColor: '#1c2a1e',
  noteTextColor: '#dfeede',
} : {
  background: '#ffffff',
  primaryColor: '#f7f8fc',
  primaryBorderColor: '#e0741a',
  primaryTextColor: '#131824',
  secondaryColor: '#eef1f8',
  tertiaryColor: '#f5f6fa',
  lineColor: '#8592ab',
  fontSize: '14px',
  fontFamily: "'Sora', system-ui, sans-serif",
  clusterBkg: 'rgba(37,99,235,.06)',
  clusterBorder: '#cfd6e4',
  actorBkg: '#f7f8fc',
  actorBorder: '#e0741a',
  actorTextColor: '#131824',
  signalColor: '#3a4256',
  signalTextColor: '#3a4256',
  noteBkgColor: '#eef7ee',
  noteTextColor: '#14321e',
};

export default function MermaidDiagram({ code }) {
  const theme = useAppTheme();
  const [svg, setSvg] = useState('');
  const [failed, setFailed] = useState(false);
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    if (!code) return;
    let cancelled = false;
    const dark = theme === 'dark';
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      suppressErrorRendering: true,
      theme: 'base',
      themeVariables: themeVars(dark),
      flowchart: { curve: 'basis', htmlLabels: false, useMaxWidth: true, padding: 16, nodeSpacing: 45, rankSpacing: 45 },
      sequence: { useMaxWidth: true, mirrorActors: false },
    });

    const id = `mmd-${++_id}`;
    mermaid
      .render(id, code)
      .then(({ svg }) => { if (!cancelled) { setSvg(svg); setFailed(false); } })
      .catch(() => { if (!cancelled) { setFailed(true); setSvg(''); } });

    return () => { cancelled = true; };
  }, [code, theme]);

  if (failed) {
    return (
      <div className="mmd-fallback">
        <div className="mmd-fallback-msg">
          <AlertTriangle size={15} /> This diagram couldn't be rendered.
          <button className="mmd-code-toggle" onClick={() => setShowCode(s => !s)}>
            <Code2 size={13} /> {showCode ? 'Hide' : 'View'} source
          </button>
        </div>
        {showCode && <pre className="mmd-code">{code}</pre>}
      </div>
    );
  }

  return <div className="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}
