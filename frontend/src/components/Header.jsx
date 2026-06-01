import React from 'react';

export default function Header({ theme, onThemeToggle }) {
  const isDark = theme === 'dark';
  return (
    <header className="hdr">
      <div className="hdr-left">
        <div className="hdr-logo">R</div>
        <h1>AI Researcher</h1>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span className="tag">LangGraph</span>
        <span className="tag">v1.0</span>
        <button
          onClick={onThemeToggle}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          style={{
            background: 'transparent',
            border: '1px solid var(--bdr)',
            borderRadius: 'var(--rs)',
            color: 'var(--t2)',
            cursor: 'pointer',
            fontSize: '1rem',
            width: 32,
            height: 32,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'border-color .15s, color .15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--orange)'; e.currentTarget.style.color = 'var(--orange)'; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--bdr)'; e.currentTarget.style.color = 'var(--t2)'; }}
        >
          {isDark ? '☀️' : '🌙'}
        </button>
      </div>
    </header>
  );
}
