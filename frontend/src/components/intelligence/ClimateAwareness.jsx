import { lazy, Suspense, useEffect, useState } from 'react';
import { api } from '../../api';
import { date } from '../../utils/formatters';
import { ErrorNotice, Loading, Notice, Panel } from '../ui/Primitives';

const EmissionsChart = lazy(() => import('./EmissionsChart'));
const amount = (value) => new Intl.NumberFormat('en', { maximumFractionDigits: 2 }).format(value);
export function TrendText({ trend }) {
  if (!trend) return <span>Two comparable years are needed to establish a trend.</span>;
  return (
    <span>
      {trend.direction === 'unchanged'
        ? 'Unchanged'
        : `${trend.direction === 'up' ? 'Up' : 'Down'} ${trend.percent == null ? amount(Math.abs(trend.change)) : `${amount(Math.abs(trend.percent))}%`}`}{' '}
      from {trend.from_year} to {trend.to_year}
      {trend.from_value === 0 ? ' (zero baseline; no percentage calculated)' : ''}.
    </span>
  );
}

export default function ClimateAwareness({ item, onSource }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [baseline, setBaseline] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    setData(null);
    api(
      `/companies/${encodeURIComponent(item.company.id)}/awareness?analysis_id=${encodeURIComponent(item.id)}${baseline ? `&baseline=${baseline}` : ''}`,
      { signal: controller.signal },
    )
      .then(setData)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, [item.id, item.company.id, baseline, retry]);
  const latest = data?.series.at(-1);
  const score = item.scores.momentum.score;
  return (
    <div className="page-stack awareness-section">
      <Panel
        title="What they say vs what the data shows"
        description="Know what your money is backing. Read company claims alongside emissions evidence."
      >
        <ErrorNotice error={error} onRetry={() => setRetry((n) => n + 1)} />
        {!data && !error && <Loading>Loading climate context…</Loading>}
        {data && (
          <>
            <div className="awareness-grid">
              <article className="awareness-measure">
                <span className="eyebrow">REPORT LANGUAGE</span>
                <strong className="awareness-number">
                  {score ?? '—'}
                  {score != null && <small>/100</small>}
                </strong>
                <p>
                  Wording in the collected reports and news. A higher value reflects more positive
                  language, including targets and policies.
                </p>
                <p className="small muted">
                  It does not measure emissions reductions, overall sustainability or investment
                  returns. News may contain headline-only evidence.
                </p>
              </article>
              <article className="awareness-measure">
                <span className="eyebrow">ATTRIBUTED EMISSIONS</span>
                {latest ? (
                  <>
                    <strong className="awareness-number">
                      {amount(latest.total_mtco2e)}
                      <small>Mt CO₂e · {latest.year}</small>
                    </strong>
                    <p>
                      <TrendText trend={data.trend} />
                    </p>
                    <p className="small muted">
                      Carbon Majors estimate · parent: {data.entity}. {data.mapping_kind}. From your
                      imported CSV; provenance is not independently verified.
                    </p>
                  </>
                ) : (
                  <>
                    <h3>No comparable emissions series yet</h3>
                    <p>
                      {item.mode === 'demo'
                        ? 'Sample analysis does not use live emissions imports.'
                        : data.applicable
                          ? 'Import an official Carbon Majors CSV to view this producer’s historical emissions and production.'
                          : 'Carbon Majors covers fossil-fuel and cement producers. Use the sector-specific report evidence below for this company.'}
                    </p>
                    {data.applicable && item.mode !== 'demo' && (
                      <a className="text-button" href="#/emissions">
                        Manage emissions data →
                      </a>
                    )}
                  </>
                )}
              </article>
            </div>
            {latest && score != null && score >= 65 && data.trend?.direction === 'up' && (
              <Notice>
                Positive report language appears alongside rising attributed emissions over this
                period. These are different measures; this observation does not establish misleading
                intent.
              </Notice>
            )}
            <p className="small muted awareness-boundary">
              {data.boundary}{' '}
              <a href={data.methodology_url} target="_blank" rel="noreferrer">
                Read the methodology ↗
              </a>
            </p>
            {latest && (
              <>
                <div className="section-heading">
                  <h3>Historical emissions</h3>
                  <label>
                    Compare from{' '}
                    <select
                      aria-label="Emissions trend baseline"
                      value={baseline}
                      onChange={(e) => setBaseline(e.target.value)}
                    >
                      <option value="">2020, or earliest available</option>
                      {data.series.slice(0, -1).map((p) => (
                        <option key={p.year} value={p.year}>
                          {p.year}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <Suspense fallback={<Loading>Loading chart…</Loading>}>
                  <EmissionsChart series={data.series} />
                </Suspense>
                <details>
                  <summary>View annual emissions table</summary>
                  <div className="table-scroll">
                    <table>
                      <caption className="sr-only">
                        Annual Carbon Majors attributed emissions
                      </caption>
                      <thead>
                        <tr>
                          <th>Year</th>
                          <th>Mt CO₂e</th>
                          <th>CO₂ components, Mt</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.series.map((p) => (
                          <tr key={p.year}>
                            <td>{p.year}</td>
                            <td>{amount(p.total_mtco2e)}</td>
                            <td>{p.co2_mt == null ? 'Not available' : amount(p.co2_mt)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                {data.production.length > 0 && (
                  <div className="production-grid">
                    {data.production.map((p) => (
                      <article key={`${p.commodity}-${p.unit}`} className="awareness-measure">
                        <h3>{p.commodity} production</h3>
                        <strong>
                          {amount(p.series.at(-1).value)} {p.unit} · {p.series.at(-1).year}
                        </strong>
                        <p>
                          <TrendText trend={p.trend} />
                        </p>
                        {/cement/i.test(p.commodity) && (
                          <p className="small muted">
                            For cement, check the CSV unit: Carbon Majors can express production as
                            process CO₂, rather than tonnes of cement.
                          </p>
                        )}
                      </article>
                    ))}
                  </div>
                )}
                {!data.production.length && (
                  <p className="small muted">
                    Production is unavailable in this CSV. Import medium or high granularity for
                    commodity-specific production trends.
                  </p>
                )}
                <p className="small muted">
                  Oil, gas, coal and cement units stay separate. Missing years are not interpolated.{' '}
                  <a href={data.source_url} target="_blank" rel="noreferrer">
                    InfluenceMap / Carbon Majors ↗
                  </a>{' '}
                  · {data.dataset.filename} · {data.dataset.version || 'Version not supplied'} ·
                  imported {date(data.dataset.created_at)} · {data.dataset.granularity} granularity.
                </p>
              </>
            )}
          </>
        )}
      </Panel>
      {data && (
        <Panel
          title={`What matters in ${data.sector_group}`}
          description="Company-reported evidence for this sector. Commitments are not verified outcomes."
        >
          <div className="sector-evidence-grid">
            {data.metrics.map((metric) => (
              <article key={metric.label}>
                <h3>{metric.label}</h3>
                {metric.facts.length ? (
                  metric.facts.map((fact) => (
                    <div className="sector-fact" key={fact.id}>
                      <strong>
                        {fact.label} · {fact.display}
                      </strong>
                      <p>
                        {fact.status === 'target' ? 'Target / commitment' : 'Reported disclosure'} ·{' '}
                        {fact.period || 'Year not explicit'}
                      </p>
                      <blockquote>{fact.quote}</blockquote>
                      <button className="text-button small" onClick={() => onSource(fact)}>
                        Review evidence{fact.page ? ` · p.${fact.page}` : ''}
                      </button>
                    </div>
                  ))
                ) : (
                  <p className="muted small">
                    No verified extract for this topic in the retained reports. Review the original
                    disclosure; this does not mean the company has no policy or impact.
                  </p>
                )}
              </article>
            ))}
          </div>
        </Panel>
      )}
      {latest && (
        <Panel
          title="Putting the scale in context"
          description="A magnitude illustration using CO₂ only, with matching calendar years."
        >
          {data.country_scale ? (
            <>
              <p className="scale-reading">
                <strong>{amount(data.country_scale.company_mtco2)} Mt CO₂</strong> attributed to{' '}
                {data.entity} in {data.country_scale.year} is approximately{' '}
                <strong>{amount(data.country_scale.ratio)}×</strong> the{' '}
                <strong>{amount(data.country_scale.country_mtco2)} Mt CO₂</strong> estimated for{' '}
                {data.country_scale.name} in the same year.
              </p>
              <Notice>{data.country_scale.notice}</Notice>
              <p className="small muted">
                Company CO₂ is the sum of product combustion, flaring, venting and own fuel-use CO₂,
                excluding methane. Country chosen by closest positive total, not political or
                geographic similarity.{' '}
                <a href={data.country_scale.source_url} target="_blank" rel="noreferrer">
                  {data.country_scale.attribution} ↗
                </a>{' '}
                · {data.country_scale.version} · retrieved {date(data.country_scale.fetched_at)} ·{' '}
                <a href={data.country_scale.license_url} target="_blank" rel="noreferrer">
                  CC BY 4.0
                </a>
                .
              </p>
            </>
          ) : (
            <p>
              No compatible country comparison is available. It requires all CO₂ component columns
              in a high-granularity CSV and a full matching year in the country snapshot (2023 or
              2024). Carbon Majors CO₂e uses a different methane warming factor from Climate TRACE,
              so those totals are not mixed.
            </p>
          )}
        </Panel>
      )}
    </div>
  );
}
