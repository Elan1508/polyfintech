import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export default function EmissionsChart({ series }) {
  const points = new Map(series.map((p) => [p.year, p]));
  const start = series[0].year,
    end = series.at(-1).year;
  const annual = Array.from(
    { length: end - start + 1 },
    (_, index) => points.get(start + index) || { year: start + index, total_mtco2e: null },
  );
  return (
    <div
      className="emissions-chart"
      role="img"
      aria-label={`Annual attributed emissions from ${start} to ${end}, in million tonnes CO2 equivalent. Exact values are in the annual table below.`}
    >
      <ResponsiveContainer width="100%" height={270}>
        <LineChart data={annual} margin={{ top: 12, right: 20, bottom: 16, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="year" minTickGap={36} tick={{ fill: '#b3c1d2' }} />
          <YAxis
            width={65}
            tick={{ fill: '#b3c1d2' }}
            tickFormatter={(v) => Intl.NumberFormat('en', { notation: 'compact' }).format(v)}
          />
          <Tooltip
            formatter={(value) => [
              `${Intl.NumberFormat('en', { maximumFractionDigits: 2 }).format(value)} Mt CO₂e`,
              'Attributed emissions',
            ]}
            contentStyle={{
              background: 'var(--surface-1)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
            }}
          />
          <Line
            name="Attributed emissions"
            type="linear"
            dataKey="total_mtco2e"
            stroke="#52dfb4"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
