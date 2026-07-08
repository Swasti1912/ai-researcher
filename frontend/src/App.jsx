import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Sparkles, AlertCircle } from 'lucide-react';
import Header from './components/Header';
import QueryInput from './components/QueryInput';
import Results from './components/Results';
import Sidebar from './components/Sidebar';
import PaperMode from './components/PaperMode';
import Login from './components/Login';
import { submitResearch, uploadPaper, getAuth, logout } from './services/api';

const STEPS = [
  { key: 'orchestrator', label: 'Orchestrator' },
  { key: 'refiner',      label: 'Refiner' },
  { key: 'intent',       label: 'Intent' },
  { key: 'decomposer',   label: 'Decomposer' },
  { key: 'aggregator',   label: 'Aggregator' },
  { key: 'reasoning',    label: 'Reasoning' },
  { key: 'evaluator',    label: 'Evaluator' },
];

const EXAMPLES = [
  'What is retrieval-augmented generation?',
  'How does the Transformer attention mechanism work?',
  'Latest advances in protein structure prediction',
  'Compare diffusion models and GANs',
];

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);
  const toggleTheme = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'));

  const [auth, setAuth]           = useState(null);   // null=loading; {auth_enabled, authenticated, user}
  useEffect(() => { getAuth().then(setAuth).catch(() => setAuth({ auth_enabled: false, authenticated: true })); }, []);
  const doLogout = async () => { try { await logout(); } catch { /* ignore */ } setAuth(a => ({ ...a, authenticated: false, user: null })); };

  const [mode, setMode]           = useState('research');
  const [query, setQuery]         = useState('');
  const [paper, setPaper]         = useState(null);
  const [paperInfo, setPaperInfo] = useState(null);
  const [loading, setLoading]     = useState(false);
  const [active, setActive]       = useState(-1);
  const [done, setDone]           = useState([]);
  const [result, setResult]       = useState(null);
  const [error, setError]         = useState(null);
  const [openPaper, setOpenPaper] = useState(null);   // paper to open in Paper Q&A from a research deep-dive
  const timers = useRef([]);

  // Research "Summarize & visualize" → open the paper in the full Paper Q&A
  // page (fetch + ingest + summarize + chat + PDF), instead of a parallel modal.
  const openInPaperMode = (p) => {
    setOpenPaper({ url: p.url, title: p.title, abstract: p.abstract });
    setMode('paper');
  };

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
  const clearPaper = () => { setPaper(null); setPaperInfo(null); };

  const runQuery = async (q) => {
    // q may be a string (suggestion chip / explicit call) or nothing. Guard
    // against an event object arriving from a button's onClick={onSubmit}.
    const arg = typeof q === 'string' ? q : null;
    const question = (arg ?? query).trim();
    if (!question || loading) return;
    if (arg) setQuery(arg);
    setLoading(true); setError(null); setResult(null);
    setActive(0); setDone([]); animate();
    try {
      const r = await submitResearch(question, paperInfo?.text_preview || null, paperInfo?.filename || null);
      setResult(r); setDone(STEPS.map(s => s.key)); setActive(STEPS.length);
    } catch (e) {
      setError(e.response?.data?.message || e.response?.data?.detail || e.message);
      setActive(-1);
    } finally { clearTimers(); setLoading(false); }
  };

  const showHero = mode === 'research' && !result && !loading && !error;

  // Auth gate — whole app behind login when auth is enabled server-side.
  if (auth === null) {
    return <div className="app-loading"><span className="spin" /></div>;
  }
  if (auth.auth_enabled && !auth.authenticated) {
    return <Login error={new URLSearchParams(window.location.search).has('auth_error')} />;
  }

  return (
    <div className="app">
      <Header mode={mode} onModeChange={setMode} theme={theme} onThemeToggle={toggleTheme}
        user={auth.user} onLogout={doLogout} />

      {mode === 'research' ? (
        <div className={`body ${!result ? 'body-full' : ''}`}>
          <main className="main">
            <div className="main-inner">
              {showHero && (
                <div className="hero">
                  <span className="hero-badge"><Sparkles size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> Multi-agent research</span>
                  <div className="hero-title">Research anything, deeply.</div>
                  <div className="hero-sub">
                    Ask a question and a pipeline of agents searches arXiv, Semantic Scholar &amp; more —
                    then synthesizes a cited answer.
                  </div>
                </div>
              )}

              <QueryInput
                query={query} setQuery={setQuery} onSubmit={runQuery} loading={loading}
              />

              {showHero && (
                <div className="examples">
                  {EXAMPLES.map((ex, i) => (
                    <button key={i} className="example-chip" onClick={() => runQuery(ex)}>{ex}</button>
                  ))}
                </div>
              )}

              {error && (
                <div className="err-card">
                  <AlertCircle size={20} color="var(--red)" style={{ flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--t0)', fontSize: '.86rem', marginBottom: 2 }}>Something went wrong</div>
                    <div style={{ fontSize: '.8rem', color: 'var(--t2)' }}>{error}</div>
                  </div>
                </div>
              )}

              {loading && !result && (
                <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'center', padding: 28 }}>
                  <span className="spin" />
                  <span style={{ color: 'var(--t2)', fontSize: '.85rem' }}>Running the research pipeline…</span>
                </div>
              )}

              {result && <Results result={result} onOpenPaper={openInPaperMode} />}
            </div>
          </main>

          {result && (
            <aside className="side">
              <Sidebar steps={STEPS} active={active} done={done} loading={loading} result={result} />
            </aside>
          )}
        </div>
      ) : (
        <div className="body body-full">
          <main className="main">
            <div className="main-inner main-inner-wide">
              <PaperMode
                openRequest={openPaper}
                onConsumed={() => setOpenPaper(null)}
                onBack={result ? () => setMode('research') : undefined}
              />
            </div>
          </main>
        </div>
      )}

      <footer className="app-foot">
        Help &amp; support: <a href="mailto:ai.researcher4@gmail.com">ai.researcher4@gmail.com</a>
      </footer>
    </div>
  );
}
