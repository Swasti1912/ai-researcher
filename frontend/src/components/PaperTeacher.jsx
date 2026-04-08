/**
 * PaperTeacher — guided lesson walkthrough for a paper.
 *
 * Shows chapters one at a time (like slides) with:
 *   - Explanation in plain English
 *   - A vivid analogy
 *   - The single key takeaway
 *
 * The user can step through linearly or jump to any chapter.
 */
import React, { useState } from 'react';

export default function PaperTeacher({ lesson, onClose }) {
  const [activeChapter, setActiveChapter] = useState(0); // index into chapters array
  const chapters = lesson.chapters || [];
  const total = chapters.length;
  const ch = chapters[activeChapter] || null;

  const prev = () => setActiveChapter(i => Math.max(0, i - 1));
  const next = () => setActiveChapter(i => Math.min(total - 1, i + 1));

  return (
    <div className="teacher-panel">

      {/* Header */}
      <div className="teacher-header">
        <div className="teacher-header-left">
          <div className="teacher-icon">🎓</div>
          <div>
            <div className="teacher-title">{lesson.lesson_title || 'Paper Walkthrough'}</div>
            {lesson.paper_in_one_sentence && (
              <div className="teacher-one-liner">{lesson.paper_in_one_sentence}</div>
            )}
          </div>
        </div>
        <button className="btn btn-g teacher-close" onClick={onClose}>✕ Close</button>
      </div>

      {/* Big picture */}
      {lesson.big_picture && (
        <div className="teacher-big-picture">
          <div className="teacher-bp-label">The Big Picture</div>
          <div className="teacher-bp-text">{lesson.big_picture}</div>
          {lesson.prerequisite_knowledge && (
            <div className="teacher-prereq">
              <span className="teacher-prereq-label">You'll need to know:</span>
              {lesson.prerequisite_knowledge}
            </div>
          )}
        </div>
      )}

      {/* Chapter nav strip */}
      {total > 0 && (
        <div className="teacher-nav-strip">
          {chapters.map((c, i) => (
            <button
              key={i}
              className={`teacher-nav-dot ${i === activeChapter ? 'tnd-active' : i < activeChapter ? 'tnd-done' : ''}`}
              onClick={() => setActiveChapter(i)}
              title={c.title}
            >
              <span className="tnd-num">{c.number || i + 1}</span>
              <span className="tnd-label">{c.title}</span>
            </button>
          ))}
        </div>
      )}

      {/* Active chapter */}
      {ch && (
        <div className="teacher-chapter">
          <div className="teacher-ch-header">
            <div className="teacher-ch-badge">Chapter {ch.number}</div>
            <div className="teacher-ch-title">{ch.title}</div>
          </div>

          <div className="teacher-ch-explanation">{ch.explanation}</div>

          {ch.analogy && (
            <div className="teacher-analogy">
              <div className="teacher-analogy-icon">💡</div>
              <div className="teacher-analogy-text">{ch.analogy}</div>
            </div>
          )}

          {ch.key_takeaway && (
            <div className="teacher-takeaway">
              <span className="teacher-takeaway-label">Key Takeaway</span>
              <span className="teacher-takeaway-text">{ch.key_takeaway}</span>
            </div>
          )}
        </div>
      )}

      {/* Prev / Next */}
      {total > 0 && (
        <div className="teacher-controls">
          <button className="btn btn-g" onClick={prev} disabled={activeChapter === 0}>
            ← Previous
          </button>
          <span className="teacher-progress">{activeChapter + 1} / {total}</span>
          <button className="btn btn-p" onClick={next} disabled={activeChapter === total - 1}>
            Next →
          </button>
        </div>
      )}

      {/* How it all fits — shown after last chapter */}
      {activeChapter === total - 1 && lesson.how_it_all_fits && (
        <div className="teacher-synthesis">
          <div className="teacher-synthesis-label">How It All Fits Together</div>
          <div className="teacher-synthesis-text">{lesson.how_it_all_fits}</div>
        </div>
      )}
    </div>
  );
}
