import { ArrowDownRight, ArrowUpRight } from 'lucide-react';
import { friendlyLabel } from '../../utils/presentation';
import { scoreTone, zeroRiskFlags } from '../../utils/research';

export function ScoreBand({ metric = 'momentum', value, compact = false }) {
  if (value == null) return null;
  return (
    <div
      className={`score-band ${metric} ${compact ? 'compact' : ''} ${scoreTone(metric, value)}`}
      role="img"
      aria-label={`${value} of 100. ${metric === 'risk' ? 'Higher values mean more matched risk pressure.' : 'Below 40: adverse language. 40 to 64: mixed language. 65 and above: positive language. This describes wording, not measured performance.'}`}
    >
      <span
        className="score-band-fill"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
      <span
        className="score-band-marker"
        style={{ left: `${Math.max(1, Math.min(99, value))}%` }}
      />
    </div>
  );
}
export function ScoreChange({ value, metric }) {
  if (value == null) return <span className="score-change muted">No prior score</span>;
  const improving = metric === 'risk' ? value < 0 : value > 0;
  const Icon = value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`score-change ${value === 0 ? 'muted' : improving ? 'positive' : 'negative'}`}>
      {value !== 0 && <Icon size={14} aria-hidden="true" />}
      {value > 0 ? '+' : ''}
      {value} pts<span className="sr-only"> since previous comparable analysis</span>
    </span>
  );
}
export function ScoreValue({ analysis, metric, delta, showChange = false }) {
  const value = analysis?.scores[metric]?.score;
  const flags = metric === 'risk' && zeroRiskFlags(analysis);
  return (
    <div className={`table-score ${scoreTone(metric, value)}`}>
      <strong>
        {flags ? '0 flags' : (value ?? '—')}
        {value == null && !flags && <span className="sr-only">Unscored</span>}
      </strong>
      <ScoreBand metric={metric} value={value} compact />
      {showChange && <ScoreChange metric={metric} value={delta} />}
    </div>
  );
}
export function ScoreMetric({
  metric = 'momentum',
  label,
  score,
  detail,
  icon: Icon,
  delta,
  flagCount,
  hasSources,
  peer,
}) {
  const noFlags = metric === 'risk' && score == null && flagCount === 0 && hasSources;
  return (
    <div className={`metric score-metric ${scoreTone(metric, score)}`}>
      <div className="metric-top">
        <span>{label}</span>
        {Icon && <Icon size={19} />}
      </div>
      <div className="metric-value">
        {noFlags ? '0' : (score ?? '—')}
        {noFlags ? <span> flags</span> : score != null ? <span>/100</span> : null}
      </div>
      <p>
        {noFlags ? 'No matched risk signals' : friendlyLabel(detail) || 'More information needed'}
      </p>
      <ScoreBand metric={metric} value={score} />
      {score != null && (
        <p className="metric-context">
          {metric === 'risk'
            ? 'Higher = more matched risk pressure'
            : score >= 65
              ? '65–100 · Positive language'
              : score < 40
                ? '0–39 · Adverse language'
                : '40–64 · Mixed language'}
        </p>
      )}
      {noFlags && (
        <p className="metric-context">Within the collected sources; risk score remains unscored.</p>
      )}
      <ScoreChange metric={metric} value={delta} />
      {peer?.available && (
        <p className="metric-peer">
          Sector median <strong>{peer.median}</strong> · {peer.sample_size} workspace companies
        </p>
      )}
    </div>
  );
}
