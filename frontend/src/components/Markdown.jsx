import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders Markdown text with the app's prose styling.
 * Used for all long-form answer content (research answers, sub-question
 * explanations, paper Q&A). Falls back gracefully on empty input.
 */
export default function Markdown({ children, className = '' }) {
  if (!children) return null;
  return (
    <div className={`prose ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // open links in a new tab safely
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {String(children)}
      </ReactMarkdown>
    </div>
  );
}
