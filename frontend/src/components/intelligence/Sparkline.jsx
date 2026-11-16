import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { chartPoints } from '../../utils/research';
import { date } from '../../utils/formatters';

export default function Sparkline({ rows = [] }) {
  const points = chartPoints(rows),
    available = points.filter((point) => point.value != null);
  if (available.length < 2)
    return (
      <span className="muted small">
        {available.length ? '1 scored analysis' : 'No scored history'}
      </span>
    );
  return (
    <div
      className="sparkline"
      role="img"
      aria-label={`Report-language indicator from ${date(available[0].created_at, true)} to ${date(available.at(-1).created_at, true)}. Open company history for values.`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart
          data={points}
          accessibilityLayer
          margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
        >
          <XAxis type="number" dataKey="timestamp" domain={['dataMin', 'dataMax']} hide />
          <YAxis domain={[0, 100]} hide />
          <Tooltip
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="chart-tooltip">
                  <span>{date(payload[0].payload.created_at, true)}</span>
                  <strong>Report language {payload[0].value}</strong>
                </div>
              ) : null
            }
          />
          <Line
            type="linear"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
