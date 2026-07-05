import React, { useState } from 'react';
import { NotebookPen } from 'lucide-react';
import NotesPanel from './NotesPanel';

/**
 * Floating "Notes" button + slide-out drawer. Reused on both the Paper Q&A and
 * Research pages — pass a note API from useNotes().
 */
export default function NotesDock({ note }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="notes-fab" onClick={() => setOpen(true)} title="Open notes">
        <NotebookPen size={16} /> Notes{note.notes.length ? <span className="notes-fab-count">{note.notes.length}</span> : null}
      </button>
      {open && (
        <div className="notes-drawer-overlay" onClick={e => e.target === e.currentTarget && setOpen(false)}>
          <div className="notes-drawer">
            <NotesPanel note={note} onClose={() => setOpen(false)} />
          </div>
        </div>
      )}
    </>
  );
}
