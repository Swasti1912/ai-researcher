/**
 * ConceptCards — clickable glossary cards extracted from the paper.
 *
 * Each card shows the concept name + definition.
 * Clicking sends a pre-built deep-dive question to the chat via onAsk().
 */
import React, { useState } from 'react';
import { MapPin, NotebookPen } from 'lucide-react';

export default function ConceptCards({ concepts = [], onAsk, onLocate, onSave, disabled }) {
  const [expanded, setExpanded] = useState(null);

  if (!concepts.length) return null;

  const handleAsk = (concept) => {
    if (disabled) return;
    onAsk(
      `Explain "${concept.name}" in depth as described in this paper: how it works step by step, ` +
      `its role in the research, the intuition behind the design choice, and how it connects to other key concepts.`
    );
  };

  return (
    <div className="concept-section">
      <div className="sec-title">Key Concepts — click any to deep-dive</div>
      <div className="concept-grid">
        {concepts.map((c, i) => {
          const name = c.name || '';
          const def  = c.definition || '';
          const imp  = c.importance || '';
          const isOpen = expanded === i;
          return (
            <div
              key={i}
              className={`concept-card ${isOpen ? 'cc-open' : ''}`}
              onClick={() => setExpanded(isOpen ? null : i)}
            >
              <div className="concept-card-top">
                <div className="concept-name">{name}</div>
                <div className="concept-card-actions">
                  {onLocate && (
                    <button className="concept-locate" title="Find in PDF"
                      onClick={(e) => { e.stopPropagation(); onLocate(name); }}>
                      <MapPin size={13} />
                    </button>
                  )}
                  <div className="concept-expand">{isOpen ? '▴' : '▾'}</div>
                </div>
              </div>
              <div className="concept-def">{def}</div>
              {isOpen && (
                <div className="concept-detail">
                  {imp && (
                    <div className="concept-importance">
                      <span className="concept-imp-label">Why it matters</span>
                      {imp}
                    </div>
                  )}
                  <div className="concept-detail-actions">
                    <button
                      className="btn btn-p concept-ask-btn"
                      onClick={(e) => { e.stopPropagation(); handleAsk(c); }}
                      disabled={disabled}
                    >
                      ✦ Deep-dive in chat
                    </button>
                    {onSave && (
                      <button className="save-note-btn"
                        onClick={(e) => { e.stopPropagation(); onSave(c); }}
                        title="Save this concept to your notes">
                        <NotebookPen size={12} /> Save to notes
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
