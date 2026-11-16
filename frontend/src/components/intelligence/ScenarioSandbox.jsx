import { useState } from 'react';
import { Panel } from '../ui/Primitives';

export default function ScenarioSandbox({ baseline }) {
  const [change, setChange] = useState(2);
  return (
    <Panel
      title="Explore a scenario"
      description="See how a change in momentum could affect an illustrative scenario. This is not a forecast."
    >
      {baseline == null ? (
        <p className="muted">A scored momentum baseline is needed to illustrate a scenario.</p>
      ) : (
        <>
          <label className="range-label" htmlFor="quarterly-change">
            Assumed indicator change per quarter
            <strong>
              {change > 0 ? '+' : ''}
              {change} points
            </strong>
          </label>
          <input
            id="quarterly-change"
            type="range"
            min="-10"
            max="10"
            value={change}
            onChange={(e) => setChange(Number(e.target.value))}
          />
          <div className="scenario-grid">
            {[0, 1, 2, 3, 4].map((quarter) => (
              <div key={quarter}>
                <span>{quarter ? `${quarter * 3} months` : 'Baseline'}</span>
                <strong>{Math.max(0, Math.min(100, baseline + change * quarter))}</strong>
              </div>
            ))}
          </div>
          <p className="tiny muted">
            Calculation: current momentum + your assumed quarterly change × quarters, bounded to
            0–100. No estimated returns, probabilities, or investment recommendation.
          </p>
        </>
      )}
    </Panel>
  );
}
