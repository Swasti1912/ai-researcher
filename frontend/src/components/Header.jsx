import React from 'react';
export default function Header() {
  return (
    <header className="hdr">
      <div className="hdr-left">
        <div className="hdr-logo">R</div>
        <h1>AI Researcher</h1>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <span className="tag">LangGraph</span>
        <span className="tag">v1.0</span>
      </div>
    </header>
  );
}
