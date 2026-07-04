/**
 * PaperTeacher — "teach me this paper" as a full, section-by-section lesson.
 *
 * Frames the paper (big picture + prerequisites), then teaches EVERY section
 * in depth by reusing the SectionBreakdown engine (each section expands into an
 * extensive explanation with its equations rendered in KaTeX and the figures /
 * charts that live on that section's pages). Works for any paper — technical or
 * not — because every paper has sections.
 */
import React from 'react';
import { GraduationCap } from 'lucide-react';
import SectionBreakdown from './SectionBreakdown';

export default function PaperTeacher({ lesson, sections = [], sessionId, onLocate, onLocatePage, onClose }) {
  return (
    <div className="teacher-panel">

      {/* Header */}
      <div className="teacher-header">
        <div className="teacher-header-left">
          <div className="teacher-icon"><GraduationCap size={20} /></div>
          <div>
            <div className="teacher-title">{lesson?.lesson_title || 'Teach me this paper'}</div>
            {lesson?.paper_in_one_sentence && (
              <div className="teacher-one-liner">{lesson.paper_in_one_sentence}</div>
            )}
          </div>
        </div>
        <button className="btn btn-g teacher-close" onClick={onClose}>✕ Close</button>
      </div>

      {/* Big picture + prerequisites */}
      {lesson?.big_picture && (
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

      {/* Section-by-section teaching (each expands to a full lesson) */}
      {sections.length > 0 ? (
        <>
          <div className="teacher-sections-label">
            <GraduationCap size={13} /> Walk through the paper — open any section for an in-depth lesson
          </div>
          <SectionBreakdown
            sections={sections}
            sessionId={sessionId}
            onLocate={onLocate}
            onLocatePage={onLocatePage}
          />
        </>
      ) : (
        <div className="teacher-empty">Section breakdown isn't available for this paper yet.</div>
      )}

      {/* How it all fits */}
      {lesson?.how_it_all_fits && (
        <div className="teacher-synthesis">
          <div className="teacher-synthesis-label">How It All Fits Together</div>
          <div className="teacher-synthesis-text">{lesson.how_it_all_fits}</div>
        </div>
      )}
    </div>
  );
}
