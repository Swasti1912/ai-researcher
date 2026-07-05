import React, { useState } from 'react';
import { NotebookPen, Download, Pencil, Trash2, ChevronDown } from 'lucide-react';

/**
 * Collapsible per-paper notes panel. Write your own notes or capture AI output
 * via note.add(source, body) from anywhere; export the whole thing as Markdown.
 */
export default function NotesPanel({ note }) {
  const { notes, title, setTitle, add, update, remove, download } = note;
  const [open, setOpen] = useState(true);
  const [draft, setDraft] = useState('');
  const [editingId, setEditingId] = useState(null);

  const commit = () => {
    const b = draft.trim();
    if (!b) return;
    if (editingId) { update(editingId, b); setEditingId(null); }
    else { add('My note', b); }
    setDraft('');
  };
  const startEdit = (n) => { setEditingId(n.id); setDraft(n.body); };

  return (
    <div className="nw">
      <button className="nw-toggle" onClick={() => setOpen(o => !o)}>
        <NotebookPen size={14} />
        <span className="nw-toggle-title">Notes</span>
        <span className="nw-count">{notes.length || 'empty'}</span>
        <button
          className="nw-download"
          disabled={!notes.length}
          onClick={(e) => { e.stopPropagation(); download(); }}
          title="Download as Markdown"
        >
          <Download size={13} /> .md
        </button>
        <ChevronDown size={16} className={`nw-chev ${open ? 'up' : ''}`} />
      </button>

      {open && (
        <div className="nw-body-wrap">
          <input
            className="nw-title"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Untitled document"
          />

          <div className="nw-list">
            {notes.length === 0 ? (
              <div className="nw-empty">
                <NotebookPen size={24} />
                <div className="nw-empty-title">Build your own document</div>
                <div className="nw-empty-sub">Capture a concept, answer, or highlight with its “Save to notes” button — or write your own below.</div>
              </div>
            ) : notes.map(n => (
              <div key={n.id} className="nw-card">
                <div className="nw-card-top">
                  <span className="nw-src" title={n.source}>{n.source}</span>
                  <div className="nw-acts">
                    <button className="nw-icon" title="Edit" onClick={() => startEdit(n)}><Pencil size={12} /></button>
                    <button className="nw-icon nw-del" title="Delete" onClick={() => remove(n.id)}><Trash2 size={13} /></button>
                  </div>
                </div>
                <div className="nw-note-body">{n.body}</div>
              </div>
            ))}
          </div>

          <div className="nw-composer">
            <textarea
              className="nw-input"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); commit(); } }}
              placeholder="Write a note in your own words…  (⌘/Ctrl+Enter to add)"
            />
            <div className="nw-composer-row">
              {editingId && <button className="btn btn-g btn-sm" onClick={() => { setEditingId(null); setDraft(''); }}>Cancel</button>}
              <button className="nw-add" onClick={commit} disabled={!draft.trim()}>
                {editingId ? 'Update note' : 'Add note'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
