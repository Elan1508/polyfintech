import { useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { date } from '../../utils/formatters';
import { metricNames } from '../../utils/presentation';
import { chartPoints } from '../../utils/research';
import { Empty, Panel } from '../ui/Primitives';

export default function HistoryChart({ rows = [], mode }) {
  const [metric, setMetric] = useState('momentum');
  const version = rows.at(-1)?.scoring_version;
  const mixed = new Set(rows.map((row) => row.scoring_version)).size > 1;
  const points = chartPoints(rows, metric, version);
  const scored = points.filter((point) => point.value != null);
  const shortDate = (timestamp) =>
    new Intl.DateTimeFormat('en-SG', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(timestamp);
  return (
    <Panel
      title="Analysis history"
      description="Actual dated analyses. Hover or tap a point to inspect values; exact dates and scores are listed below."
      actions={
        <select
          aria-label="History metric"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        >
          {Object.entries(metricNames).map(([key, name]) => (
            <option value={key} key={key}>
              {name}
            </option>
          ))}
        </select>
      }
    >
      {rows.length === 0 ? (
        <Empty title="No history yet">Refresh a company analysis to start recording changes.</Empty>
      ) : (
        <>
          <p className="small muted">
            {mode === 'demo' ? 'Demo data' : 'Collected research'} · Method {version}
            {mixed
              ? '. The line includes only this method; other versions remain in the table.'
              : ''}
          </p>
          {scored.length >= 2 ? (
            <div
              className="dated-chart"
              aria-label={`${metricNames[metric]} over time. Exact values are also listed in the table.`}
            >
              <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                <LineChart
                  data={points}
                  accessibilityLayer
                  margin={{ top: 20, right: 20, bottom: 20, left: 0 }}
                >
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis
                    type="number"
                    dataKey="timestamp"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={shortDate}
                    tick={{ fill: 'var(--text-2)', fontSize: 12 }}
                    minTickGap={60}
                    tickLine={false}
                    axisLine={{ stroke: 'var(--border)' }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    ticks={[0, 25, 50, 75, 100]}
                    tick={{ fill: 'var(--text-2)', fontSize: 12 }}
                    width={35}
                    tickLine={false}
                    axisLine={false}
                  />
                  <ReferenceLine y={50} stroke="var(--text-3)" strokeDasharray="4 4" />
                  <Tooltip
                    content={({ active, payload }) =>
                      active && payload?.length ? (
                        <div className="chart-tooltip">
                          <span>{date(payload[0].payload.created_at, true)}</span>
                          <strong>
                            {metricNames[metric]}: {payload[0].value}/100
                          </strong>
                        </div>
                      ) : null
                    }
                  />
                  <Line
                    type="linear"
                    dataKey="value"
                    name={metricNames[metric]}
                    stroke={metric === 'risk' ? 'var(--warn)' : 'var(--accent)'}
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: 'var(--surface-1)' }}
                    activeDot={{ r: 6 }}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="More dated scores are needed">
              A trend line appears after two scored analyses using the same method. Unscored areas
              remain gaps.
            </Empty>
          )}
          <div
            className="table-scroll"
            role="region"
            aria-label="Dated analysis values"
            tabIndex={0}
          >
            <table>
              <caption className="sr-only">
                Analysis history with exact dates, scores and source counts
              </caption>
              <thead>
                <tr>
                  <th scope="col">Analysed</th>
                  <th scope="col">{metricNames[metric]}</th>
                  <th scope="col">Sources</th>
                  <th scope="col">Method</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <a href={`#/analysis/${row.id}`}>
                        <time dateTime={row.created_at}>{date(row.created_at, true)}</time>
                      </a>
                    </td>
                    <td>{row.scores[metric].score ?? 'Unscored'}</td>
                    <td>{row.source_count}</td>
                    <td>{row.scoring_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}
