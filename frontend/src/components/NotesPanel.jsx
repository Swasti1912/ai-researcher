import React, { useState } from 'react';
import { NotebookPen, Download, Pencil, Trash2, X } from 'lucide-react';

/**
 * Notes surface (used inside the slide-out drawer). Write your own notes or
 * capture AI output via note.add(source, body); export the lot as Markdown.
 */
export default function NotesPanel({ note, onClose }) {
  const { notes, title, setTitle, add, update, remove, download } = note;
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
      <div className="nw-head">
        <div className="nw-head-l">
          <div className="nw-kicker">{notes.length ? `${notes.length} ${notes.length === 1 ? 'entry' : 'entries'}` : 'start writing'}</div>
          <input className="nw-title" value={title} onChange={e => setTitle(e.target.value)} placeholder="Untitled document" />
        </div>
        <div className="nw-head-actions">
          <button className="nw-download" disabled={!notes.length} onClick={download} title="Download as Markdown">
            <Download size={13} /> .md
          </button>
          {onClose && <button className="nw-icon nw-close" onClick={onClose} title="Close"><X size={16} /></button>}
        </div>
      </div>

      <div className="nw-list">
        {notes.length === 0 ? (
          <div className="nw-empty">
            <NotebookPen size={26} />
            <div className="nw-empty-title">Build your own document</div>
            <div className="nw-empty-sub">Capture a concept, answer, taught section, or highlight with its “Save to notes” button — or write your own below.</div>
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
          placeholder="Write a note in your own words…  (⌘/Ctrl+Enter)"
        />
        <div className="nw-composer-row">
          {editingId && <button className="btn btn-g btn-sm" onClick={() => { setEditingId(null); setDraft(''); }}>Cancel</button>}
          <button className="nw-add" onClick={commit} disabled={!draft.trim()}>
            {editingId ? 'Update note' : 'Add note'}
          </button>
        </div>
      </div>
    </div>
  );
}
