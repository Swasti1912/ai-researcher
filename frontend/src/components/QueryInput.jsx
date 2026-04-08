import React, { useRef } from 'react';

export default function QueryInput({ query, setQuery, onSubmit, onUpload, paper, loading }) {
  const ref = useRef(null);
  return (
    <div className="inp">
      <textarea value={query} onChange={e => setQuery(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !loading) { e.preventDefault(); onSubmit(); } }}
        placeholder="Ask a research question, or upload a paper and query it…" disabled={loading} />
      <div className="inp-row">
        <button className="btn btn-p" onClick={onSubmit} disabled={loading || !query.trim()}>
          {loading ? <><span className="spin" /> Researching…</> : 'Run Research'}
        </button>
        <label className={`upl ${paper ? 'on' : ''}`} onClick={() => ref.current?.click()}>
          {paper ? `📄 ${paper.name}` : '+ Upload Paper'}
          <input ref={ref} type="file" accept=".pdf,.txt,.md"
            onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); }} />
        </label>
      </div>
    </div>
  );
}
