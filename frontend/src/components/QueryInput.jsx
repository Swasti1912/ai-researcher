import React from 'react';
import { Search } from 'lucide-react';

export default function QueryInput({ query, setQuery, onSubmit, loading }) {
  return (
    <div className="searchbox">
      <textarea
        value={query}
        onChange={e => setQuery(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !loading) { e.preventDefault(); onSubmit(); }
        }}
        placeholder="Ask a research question…"
        disabled={loading}
        rows={1}
      />
      <div className="searchbox-row">
        <div className="searchbox-spacer" />
        <button className="btn btn-p" onClick={onSubmit} disabled={loading || !query.trim()}>
          {loading ? <><span className="spin" /> Researching…</> : <><Search size={15} /> Research</>}
        </button>
      </div>
    </div>
  );
}
