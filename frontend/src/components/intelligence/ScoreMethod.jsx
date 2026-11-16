import { ChevronDown, Info } from 'lucide-react';
import { Badge, Panel } from '../ui/Primitives';

export default function ScoreMethod({ analysis }) {
  const method = analysis.methodology;
  const names = {
    news: 'News coverage',
    report: 'Uploaded reports',
    disclosure: 'Company reports',
    demo: 'Demo data',
  };
  return (
    <Panel
      title="How language indicators work"
      description="Understand what the indicators can tell you and where more research is needed."
    >
      <details className="method-details">
        <summary>
          <span>
            <Info size={17} />
            Explore how scores are calculated
          </span>
          <ChevronDown size={17} />
        </summary>
        <div className="method-content">
          <h3>Based on the available sources</h3>
          <p>
            We look for environmental, social, governance and digital topics in selected report
            passages and recent news. Positive and negative language contributes to the indicators;
            background information alone does not receive a score.
          </p>
          <p>
            Recent publications carry more weight. Repeated terms within a report are capped, and
            multiple passages from one report count as one source. Company targets and commitments
            are not proof of completed results.
          </p>
          <h3>Calculation details</h3>
          <p>{method.formula}</p>
          <div className="method-weights">
            {Object.entries(method.weights).map(([key, value]) => (
              <Badge key={key}>
                {names[key] || key}: {value}
              </Badge>
            ))}
          </div>
          <p>
            <strong>Publication dates:</strong> {method.freshness}
          </p>
          <p>
            <strong>ESG risk signals:</strong> {method.risk}
          </p>
          <h3>What to keep in mind</h3>
          <ul>
            {method.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            A score of 50 is the calculation’s starting point. It is not a measured company rating.
            Areas without enough information remain unscored.
          </p>
          <p>
            The “Positive language to investigate” label requires at least three sources, two scored
            areas, a report-language indicator of 65 or more, digital signals of 60 or more, and
            risk signals below 30 or unscored. It does not establish environmental improvement or
            investment value.
          </p>
          <p className="tiny muted">Scoring method: {method.version}</p>
        </div>
      </details>
    </Panel>
  );
}
