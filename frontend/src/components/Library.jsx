import React, { useEffect, useState } from 'react';
import { FileText, Trash2, Images, Clock } from 'lucide-react';
import { getLibrary, deleteSession } from '../services/api';

const fmtDate = (ts) => {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

/**
 * The reader's saved papers. Click a card to reopen; trash to delete.
 * Rendered under the drop zone in the upload phase. Hidden when empty.
 */
export default function Library({ onOpen, refreshKey }) {
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    getLibrary()
      .then((d) => setPapers(d.papers || []))
      .catch(() => setPapers([]))
      .finally(() => setLoading(false));
  };

  useEffect(load, [refreshKey]);

  const remove = async (e, sid) => {
    e.stopPropagation();
    setPapers((p) => p.filter((x) => x.session_id !== sid));
    try { await deleteSession(sid); } catch { /* ignore */ }
  };

  if (loading || papers.length === 0) return null;

  return (
    <div className="library">
      <div className="sec-title" style={{ marginBottom: 10 }}>Your library · {papers.length}</div>
      <div className="library-grid">
        {papers.map((p) => (
          <button key={p.session_id} className="library-card" onClick={() => onOpen(p.session_id)}>
            <div className="library-card-icon"><FileText size={18} /></div>
            <div className="library-card-body">
              <div className="library-card-title">{p.title || p.filename || 'Untitled paper'}</div>
              <div className="library-card-meta">
                <span><Clock size={11} /> {fmtDate(p.created_at)}</span>
                {p.page_count > 0 && <span>· {p.page_count}p</span>}
                {p.figure_count > 0 && <span>· <Images size={11} /> {p.figure_count}</span>}
                {p.source === 'url' && <span className="bdg bdg-b">arXiv</span>}
              </div>
            </div>
            <span className="library-card-del" title="Delete from library"
              onClick={(e) => remove(e, p.session_id)}>
              <Trash2 size={14} />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
