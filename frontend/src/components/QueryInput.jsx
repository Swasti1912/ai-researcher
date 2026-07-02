import React, { useRef } from 'react';
import { Search, Paperclip, X } from 'lucide-react';

export default function QueryInput({ query, setQuery, onSubmit, onUpload, onClearPaper, paper, loading }) {
  const ref = useRef(null);
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
        <label className={`upl ${paper ? 'on' : ''}`} onClick={() => !paper && ref.current?.click()}>
          {paper ? (
            <>
              <Paperclip size={13} /> {paper.name.length > 22 ? paper.name.slice(0, 22) + '…' : paper.name}
              <X size={13} style={{ marginLeft: 2 }} onClick={e => { e.stopPropagation(); onClearPaper?.(); }} />
            </>
          ) : (
            <><Paperclip size={13} /> Attach paper</>
          )}
          <input ref={ref} type="file" accept=".pdf,.txt,.md"
            onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); }} />
        </label>

        <div className="searchbox-spacer" />

        <button className="btn btn-p" onClick={onSubmit} disabled={loading || !query.trim()}>
          {loading ? <><span className="spin" /> Researching…</> : <><Search size={15} /> Research</>}
        </button>
      </div>
    </div>
  );
}
