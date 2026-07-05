import React, { useState } from 'react';
import { ChevronDown, MapPin, GraduationCap, Table2, NotebookPen } from 'lucide-react';
import { teachSection, paperFigureUrl } from '../services/api';
import Markdown from './Markdown';

/**
 * Section breakdown where each section expands into an extensive, tutor-style
 * lesson — including its equations (rendered via KaTeX) and the figures/charts
 * that live on that section's pages. Teaching is fetched on demand.
 *
 *   onLocate(text)      — jump PDF to the section heading
 *   onLocatePage(page)  — jump PDF to a figure's page
 */
export default function SectionBreakdown({ sections = [], sessionId, onLocate, onLocatePage, onSave }) {
  if (!sections.length) return null;
  return (
    <div className="paper-sections-list">
      {sections.map((s, i) => (
        <SectionItem key={i} section={s} sessionId={sessionId}
          onLocate={onLocate} onLocatePage={onLocatePage} onSave={onSave} />
      ))}
    </div>
  );
}

function SectionItem({ section, sessionId, onLocate, onLocatePage, onSave }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [err, setErr] = useState('');

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !data && !loading) {
      setLoading(true); setErr('');
      try {
        setData(await teachSection(sessionId, section.section, section.summary));
      } catch (e) {
        setErr(e.response?.data?.detail || e.message || 'Failed to load lesson');
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className={`section-item ${open ? 'open' : ''}`}>
      <div className="section-head">
        <button className="section-head-main" onClick={toggle}>
          <div className="section-info">
            <div className="paper-section-name">{section.section}</div>
            <div className="paper-section-summary">{section.summary}</div>
          </div>
          <ChevronDown size={17} className="section-chev" />
        </button>
        {onLocate && (
          <button className="section-locate" title="Find this section in the PDF"
            onClick={() => onLocate(section.section)}>
            <MapPin size={13} />
          </button>
        )}
      </div>

      {open && (
        <div className="section-teach">
          {loading && (
            <div className="section-teach-loading">
              <span className="spin" /> Preparing an in-depth lesson for this section…
            </div>
          )}
          {err && <div className="paper-err">{err}</div>}
          {data && (
            <>
              <div className="section-teach-badge">
                <span><GraduationCap size={13} /> In-depth lesson</span>
                {onSave && (
                  <button className="save-note-btn" title="Save this lesson to your notes"
                    onClick={() => onSave(section.section, data.explanation)}>
                    <NotebookPen size={12} /> Save to notes
                  </button>
                )}
              </div>
              <Markdown>{data.explanation}</Markdown>

              {data.figures?.length > 0 && (
                <div className="section-figs">
                  <div className="section-figs-title">Figures in this section</div>
                  <div className="section-figs-grid">
                    {data.figures.map((f) => (
                      <button key={f.fig_id} className="section-fig" title={f.caption || `Page ${f.page}`}
                        onClick={() => onLocatePage?.(f.page)}>
                        <div className="section-fig-thumb">
                          {f.kind === 'table' || !f.fig_id.startsWith('fig')
                            ? <div className="figure-table-ph"><Table2 size={22} /></div>
                            : <img src={paperFigureUrl(sessionId, f.fig_id)} loading="lazy" alt={f.caption || 'figure'} />}
                        </div>
                        <div className="section-fig-cap">{f.caption || `Page ${f.page}`}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
