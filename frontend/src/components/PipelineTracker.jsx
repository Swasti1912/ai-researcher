import React from 'react';

export default function PipelineTracker({ steps, activeIdx, done, loading }) {
  return (
    <div className="pipeline">
      {steps.map((step, i) => {
        const isDone = done.includes(step.key);
        const isActive = i === activeIdx && loading;
        let cls = 'pipe-step';
        if (isDone) cls += ' done';
        else if (isActive) cls += ' active';

        return (
          <div key={step.key} className={cls}>
            <span>{step.label}</span>
            <span className="status-text">
              {isDone && '✓'}
              {isActive && <span className="spinner" style={{ width: 12, height: 12 }} />}
            </span>
          </div>
        );
      })}
    </div>
  );
}
