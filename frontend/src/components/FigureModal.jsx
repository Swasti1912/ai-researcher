import React, { useEffect, useRef, useState } from 'react';
import { X, Loader2, MapPin, Send, Sparkles } from 'lucide-react';
import Markdown from './Markdown';
import { explainFigure, paperFigureUrl } from '../services/api';

/**
 * FigureModal — click a figure to get a vision-based explanation of it, grounded
 * in the surrounding paper text, then ask follow-up questions about it.
 *
 * Props:
 *   figure    — { fig_id, page, caption, kind }
 *   sessionId — paper session
 *   onClose   — close the modal
 *   onLocate  — (page) => jump the PDF pane to that page (optional)
 */
export default function FigureModal({ figure, sessionId, onClose, onLocate }) {
  const [explanation, setExplanation] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [turns, setTurns] = useState([]);       // [{role, content}]
  const [q, setQ] = useState('');
  const [asking, setAsking] = useState(false);
  const scrollRef = useRef(null);

  const isTable = figure?.kind === 'table' || !String(figure?.fig_id || '').startsWith('fig');

  // Initial explanation on open.
  useEffect(() => {
    let cancelled = false;
    if (!figure) return;
    setExplanation(''); setError(''); setTurns([]); setLoading(true);
    explainFigure(sessionId, figure.fig_id)
      .then((d) => { if (!cancelled) setExplanation(d.explanation || 'No explanation available.'); })
      .catch(() => { if (!cancelled) setError('Could not explain this figure. Please try again.'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [figure, sessionId]);

  // Esc to close.
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  useEffect(() => {
    scrollRef.current?.scrollTo?.({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, asking]);

  const ask = async () => {
    const question = q.trim();
    if (!question || asking) return;
    setQ('');
    const history = [
      { role: 'assistant', content: explanation },
      ...turns,
    ];
    setTurns((t) => [...t, { role: 'user', content: question }]);
    setAsking(true);
    try {
      const d = await explainFigure(sessionId, figure.fig_id, question, history);
      setTurns((t) => [...t, { role: 'assistant', content: d.explanation || '…' }]);
    } catch {
      setTurns((t) => [...t, { role: 'assistant', content: '_Sorry — that question failed. Try again._' }]);
    } finally {
      setAsking(false);
    }
  };

  if (!figure) return null;

  return (
    <div className="fig-modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className="fig-modal" role="dialog" aria-modal="true">
        <div className="fig-modal-head">
          <div className="fig-modal-title">
            <Sparkles size={14} /> Figure explanation
            <span className="fig-modal-page">· page {figure.page}</span>
          </div>
          <div className="fig-modal-head-actions">
            {onLocate && (
              <button className="fig-modal-locate" onClick={() => onLocate(figure.page)} title="Show in the PDF">
                <MapPin size={13} /> Go to page
              </button>
            )}
            <button className="fig-modal-close" onClick={onClose} aria-label="Close"><X size={18} /></button>
          </div>
        </div>

        <div className="fig-modal-body">
          {/* The figure itself */}
          <div className="fig-modal-image">
            {isTable
              ? <div className="fig-modal-table">Table · page {figure.page}</div>
              : <img src={paperFigureUrl(sessionId, figure.fig_id)} alt={figure.caption || 'figure'} />}
            {figure.caption && <div className="fig-modal-caption">{figure.caption}</div>}
          </div>

          {/* Explanation + follow-up chat */}
          <div className="fig-modal-explain" ref={scrollRef}>
            {loading && (
              <div className="fig-modal-loading"><Loader2 size={16} className="spin-svg" /> Reading the figure…</div>
            )}
            {error && <div className="fig-modal-error">{error}</div>}
            {!loading && !error && <Markdown>{explanation}</Markdown>}

            {turns.map((t, i) => (
              <div key={i} className={`fig-turn fig-turn-${t.role}`}>
                {t.role === 'user'
                  ? <div className="fig-turn-q">{t.content}</div>
                  : <Markdown>{t.content}</Markdown>}
              </div>
            ))}
            {asking && (
              <div className="fig-modal-loading"><Loader2 size={16} className="spin-svg" /> Thinking…</div>
            )}
          </div>
        </div>

        <div className="fig-modal-composer">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') ask(); }}
            placeholder="Ask about this figure…"
            disabled={loading}
          />
          <button onClick={ask} disabled={asking || loading || !q.trim()} aria-label="Send">
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
