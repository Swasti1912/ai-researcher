import React from 'react';
import { Highlighter, Trash2, StickyNote, NotebookPen } from 'lucide-react';

/**
 * Lists the saved highlights/notes for the open paper. Click one to jump to it
 * in the PDF; trash to delete; save into your notes doc. Hidden when empty.
 */
export default function HighlightsPanel({ highlights = [], onOpen, onDelete, onSave }) {
  if (!highlights.length) return null;
  return (
    <div className="hl-panel">
      <div className="sec-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Highlighter size={13} /> Highlights &amp; notes · {highlights.length}
      </div>
      <div className="hl-list">
        {highlights.map((h) => (
          <div key={h.id} className="hl-row" onClick={() => onOpen?.(h.id)} title="Jump to highlight">
            <span className={`hl-chip hl-${h.color || 'yellow'}`} />
            <div className="hl-row-body">
              <div className="hl-quote">{h.quote || '(no text)'}</div>
              {h.note && <div className="hl-note"><StickyNote size={11} /> {h.note}</div>}
            </div>
            <span className="hl-page">p{h.page}</span>
            {onSave && (
              <button className="hl-del" title="Save to notes" onClick={(e) => { e.stopPropagation(); onSave(h); }}>
                <NotebookPen size={13} />
              </button>
            )}
            <button className="hl-del" title="Delete" onClick={(e) => { e.stopPropagation(); onDelete?.(h.id); }}>
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
