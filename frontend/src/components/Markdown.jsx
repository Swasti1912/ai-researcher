import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

/**
 * Renders Markdown (with GitHub-flavored extras + LaTeX math via KaTeX)
 * using the app's prose styling. Used for all long-form answer content.
 * Inline math: $E = mc^2$   ·   Display math: $$ ... $$
 */
export default function Markdown({ children, className = '' }) {
  if (!children) return null;
  return (
    <div className={`prose ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
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
