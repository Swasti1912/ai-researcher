import React from 'react';

export default function ErrorCard({ message }) {
  return (
    <div className="card" style={{ borderColor: 'var(--red)' }}>
      <div className="card-head">
        <div className="dot dot-red">✕</div>
        <h4>Pipeline Error</h4>
      </div>
      <div className="card-body">{message}</div>
    </div>
  );
}
