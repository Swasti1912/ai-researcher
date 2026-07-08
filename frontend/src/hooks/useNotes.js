import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Per-paper notes, persisted to localStorage and exportable as Markdown.
 * Notes are a private, browser-local scratchpad — they never touch the server,
 * so they work logged-out and survive the ephemeral free-tier Space.
 *
 *   const n = useNotes(sessionId, paperName);
 *   n.add('Concept · Attention', 'text…')   // capture AI output
 *   n.notes / n.update / n.remove / n.setTitle / n.download()
 */
const load = (key) => {
  try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; }
};
const save = (key, data) => {
  try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* quota / private mode */ }
};

export function useNotes(sessionId, paperName = '') {
  const key = `reader-notes-${sessionId || 'default'}`;
  const [notes, setNotes] = useState(() => load(key).notes || []);
  const [title, setTitle] = useState(() => load(key).title || 'Reading notes');

  const keyRef = useRef(key);
  const skipPersist = useRef(false);

  // Reload when the open paper changes.
  useEffect(() => {
    if (key === keyRef.current) return;
    keyRef.current = key;
    skipPersist.current = true;              // don't write the reloaded value back
    const s = load(key);
    setNotes(s.notes || []);
    setTitle(s.title || 'Reading notes');
  }, [key]);

  // Persist on change (keyed to the currently-loaded paper).
  useEffect(() => {
    if (skipPersist.current) { skipPersist.current = false; return; }
    save(keyRef.current, { notes, title });
  }, [notes, title]);

  const add = useCallback((source, body) => {
    const b = (body || '').trim();
    if (!b) return;
    setNotes(prev => [...prev, {
      id: 'n' + Date.now() + Math.floor(Math.random() * 1000),
      source: source || 'My note',
      body: b,
    }]);
  }, []);

  const update = useCallback((id, body) => {
    setNotes(prev => prev.map(n => (n.id === id ? { ...n, body } : n)));
  }, []);

  const remove = useCallback((id) => {
    setNotes(prev => prev.filter(n => n.id !== id));
  }, []);

  const clear = useCallback(() => setNotes([]), []);

  const download = useCallback(() => {
    const t = (title || 'Reading notes').trim();
    const date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    let md = `# ${t}\n\n`;
    md += paperName ? `_Notes on “${paperName}” · ${date}_\n\n` : `_${date}_\n\n`;
    md += notes.length
      ? notes.map(n => `## ${n.source}\n\n${n.body}\n`).join('\n')
      : '_No notes yet._\n';
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (t.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'reading-notes') + '.md';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [notes, title, paperName]);

  return { notes, title, setTitle, add, update, remove, clear, download };
}
