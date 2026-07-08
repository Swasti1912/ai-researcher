import React, { useEffect, useState } from 'react';
import { Images, Table2 } from 'lucide-react';
import { getPaperFigures, paperFigureUrl } from '../services/api';

/**
 * Horizontal strip of figures/tables extracted from the paper.
 * Click a figure → onLocate(page) scrolls the PDF pane to that page.
 * Renders nothing if the paper has no figures (txt/md or figure-less PDF).
 */
export default function FiguresStrip({ sessionId, onLocate, onExplain }) {
  const [figures, setFigures] = useState([]);

  useEffect(() => {
    let cancelled = false;
    if (!sessionId) return;
    getPaperFigures(sessionId)
      .then((d) => { if (!cancelled) setFigures(d.figures || []); })
      .catch(() => { if (!cancelled) setFigures([]); });
    return () => { cancelled = true; };
  }, [sessionId]);

  if (!figures.length) return null;

  return (
    <div className="figures-strip-wrap">
      <div className="sec-title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Images size={13} /> Figures &amp; Tables · {figures.length}
      </div>
      <div className="figures-strip">
        {figures.map((f) => (
          <div key={f.fig_id} className="figure-card">
            <button className="figure-card-main" title="Explain this figure"
              onClick={() => onExplain?.(f)}>
              <div className="figure-thumb">
                {f.kind === 'table' ? (
                  <div className="figure-table-ph"><Table2 size={26} /></div>
                ) : (
                  <img src={paperFigureUrl(sessionId, f.fig_id)} loading="lazy" alt={f.caption || 'figure'} />
                )}
              </div>
              <div className="figure-caption">{f.caption || `Page ${f.page}`}</div>
            </button>
            <button className="figure-page" title="Go to this page in the PDF"
              onClick={() => onLocate?.(f.page)}>p{f.page}</button>
          </div>
        ))}
      </div>
    </div>
  );
}
