import React from 'react';

export default function Pipeline({ steps, active, done, loading }) {
  return (
    <div className="pipe">
      {steps.map((s, i) => {
        const isDone = done.includes(s.key);
        const isOn = i === active && loading;
        return (
          <div key={s.key} className={`pstep${isDone ? ' ok' : isOn ? ' on' : ''}`}>
            <span>{s.label}</span>
            <span className="ml">
              {isDone && '✓'}
              {isOn && <span className="spin" style={{ width: 10, height: 10 }} />}
            </span>
          </div>
        );
      })}
    </div>
  );
}
