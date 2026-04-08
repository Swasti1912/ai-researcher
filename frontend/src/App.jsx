import React, { useState, useCallback, useRef } from 'react';
import Header from './components/Header';
import QueryInput from './components/QueryInput';
import Pipeline from './components/Pipeline';
import Results from './components/Results';
import Sidebar from './components/Sidebar';
import { submitResearch, uploadPaper } from './services/api';

const STEPS = [
  { key: 'orchestrator', label: 'Orchestrator' },
  { key: 'refiner',      label: 'Refiner Agent' },
  { key: 'intent',       label: 'Intent Agent' },
  { key: 'decomposer',   label: 'Decomposer Agent' },
  { key: 'aggregator',   label: 'Aggregator Agent' },
  { key: 'reasoning',    label: 'Reasoning Agent' },
  { key: 'evaluator',    label: 'Evaluator Agent' },
];

export default function App() {
  const [query, setQuery]       = useState('');
  const [paper, setPaper]       = useState(null);   // File
  const [paperInfo, setPaperInfo] = useState(null); // upload response
  const [loading, setLoading]   = useState(false);
  const [active, setActive]     = useState(-1);
  const [done, setDone]         = useState([]);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);
  const timers = useRef([]);

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  const animate = useCallback(() => {
    clearTimers();
    [150, 600, 1400, 2400, 4200, 6400, 8600].forEach((ms, i) => {
      timers.current.push(setTimeout(() => {
        setActive(i);
        if (i > 0) setDone(p => [...p, STEPS[i - 1].key]);
      }, ms));
    });
  }, []);

  const handleUpload = async (file) => {
    setPaper(file);
    try { setPaperInfo(await uploadPaper(file)); } catch { setPaperInfo({ filename: file.name, text_preview: '' }); }
  };

  const handleSubmit = async () => {
    if (!query.trim() || loading) return;
    setLoading(true); setError(null); setResult(null);
    setActive(0); setDone([]); animate();
    try {
      const r = await submitResearch(query, paperInfo?.text_preview || null, paperInfo?.filename || null);
      setResult(r); setDone(STEPS.map(s => s.key)); setActive(STEPS.length);
    } catch (e) {
      setError(e.response?.data?.message || e.response?.data?.detail || e.message);
      setActive(-1);
    } finally { clearTimers(); setLoading(false); }
  };

  return (
    <div className="app">
      <Header />
      <div className="body">
        <main className="main">
          <QueryInput query={query} setQuery={setQuery} onSubmit={handleSubmit}
            onUpload={handleUpload} paper={paper} loading={loading} />
          {error && (
            <div className="card" style={{ borderColor: 'var(--red)' }}>
              <div className="card-h"><div className="dot d-rd">✕</div><h4>Error</h4></div>
              <div className="card-b">{error}</div>
            </div>
          )}
          {result && <Results result={result} />}
        </main>
        <aside className="side">
          <Sidebar steps={STEPS} active={active} done={done} loading={loading} result={result} />
        </aside>
      </div>
    </div>
  );
}
