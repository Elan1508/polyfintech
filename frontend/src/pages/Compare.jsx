import { sourceHref } from '../utils/presentation';
import { zeroRiskFlags } from '../utils/research';
import { friendlyLabel, metricNames } from '../utils/presentation';
import { date } from '../utils/formatters';
import { useEffect, useState } from 'react';
import { ArrowRight, Plus, X } from 'lucide-react';
import { api } from '../api';
import { usePulse } from '../context';
import CompanySearch from '../components/company/CompanySearch';
import {
  Badge,
  CompanyIdentity,
  Empty,
  ErrorNotice,
  Loading,
  Notice,
  PageHeading,
  Panel,
} from '../components/ui/Primitives';

export default function Compare() {
  const { watchlist, investigations } = usePulse();
  const [selected, setSelected] = useState([]);
  const [mode, setMode] = useState('live');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (selected.length < 2) {
      setResult(null);
      return;
    }
    const controller = new AbortController();
    setBusy(true);
    setError('');
    api('/compare', {
      method: 'POST',
      body: JSON.stringify({ company_ids: selected.map((c) => c.id), mode }),
      signal: controller.signal,
    })
      .then((data) => {
        setResult(data);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [selected, mode, retry]);
  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
    const ids = [...new Set((params.get('companies') || '').split(',').filter(Boolean))].slice(
      0,
      5,
    );
    if (!ids.length) return;
    const controller = new AbortController();
    Promise.all(
      ids.map((id) => api(`/companies/${encodeURIComponent(id)}`, { signal: controller.signal })),
    )
      .then(setSelected)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, []);
  const add = (company) => {
    setSelected((items) =>
      items.some((c) => c.id === company.id) ? items : [...items, company].slice(0, 5),
    );
    setSearchOpen(false);
  };
  const quick = [
    ...new Map(
      [
        ...watchlist.map((w) => w.company),
        ...investigations.filter((a) => a.kind === 'company').map((a) => a.company),
      ].map((c) => [c.id, c]),
    ).values(),
  ];
  const metrics = [
    [metricNames.momentum, (a) => a.scores.momentum.score ?? 'Unscored'],
    ['Language reading', (a) => a.scores.momentum.label],
    [metricNames.risk, (a) => a.scores.risk.score ?? (zeroRiskFlags(a) ? '0 flags' : 'Unscored')],
    ['Risk reading', (a) => a.scores.risk.label],
    [metricNames.digital, (a) => a.scores.digital.score ?? 'Unscored'],
    ['Environmental', (a) => a.dimensions?.E?.score ?? '—'],
    ['Social', (a) => a.dimensions?.S?.score ?? '—'],
    ['Governance', (a) => a.dimensions?.G?.score ?? '—'],
    ['Research coverage', (a) => a.coverage.status],
    ['Sources', (a) => a.source_count],
    ['Updated', (a) => date(a.created_at, true)],
    ['Scoring method', (a) => a.scoring_version],
  ];
  return (
    <div className="page-stack">
      <PageHeading title="Compare">
        Choose two to five companies to compare ESG insights, available research and recent updates.
      </PageHeading>
      <Panel
        title="Build a comparison"
        actions={
          <select
            aria-label="Comparison data mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="live">Company research</option>
            <option value="demo">Demo data</option>
          </select>
        }
      >
        <div className="comparison-selection">
          {selected.map((c) => (
            <div className="selected-company" key={c.id}>
              <CompanyIdentity company={c} small />
              <button
                className="icon-button"
                aria-label={`Remove ${c.name} from comparison`}
                onClick={() => setSelected((items) => items.filter((item) => item.id !== c.id))}
              >
                <X size={17} />
              </button>
            </div>
          ))}
          {selected.length < 5 && (
            <button className="add-comparison" onClick={() => setSearchOpen((s) => !s)}>
              <Plus size={20} />
              Add company
            </button>
          )}
        </div>
        {searchOpen && (
          <CompanySearch compact selected={selected.map((c) => c.id)} onSelect={add} />
        )}
        {quick.length > 0 && (
          <div className="quick-companies">
            <span className="muted small">From your research:</span>
            {quick.slice(0, 12).map((c) => (
              <button
                className="chip-button"
                key={c.id}
                disabled={selected.length >= 5 || selected.some((item) => item.id === c.id)}
                onClick={() => add(c)}
              >
                {c.ticker || c.name}
                <Plus size={12} />
              </button>
            ))}
          </div>
        )}
      </Panel>
      <ErrorNotice error={error} onRetry={() => setRetry((n) => n + 1)} />
      {busy ? (
        <Loading>Comparing your company research…</Loading>
      ) : result ? (
        <>
          <Notice>{result.notice}</Notice>
          <Panel>
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Scrollable company comparison"
            >
              <table className="compare-table">
                <caption className="sr-only">Company research comparison</caption>
                <thead>
                  <tr>
                    <th>ESG measure</th>
                    {result.rows.map((row) => (
                      <th key={row.company.id}>
                        {row.company.name}
                        <p className="tiny muted">
                          {row.company.ticker} · {row.company.exchange}
                        </p>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Sector peer group</th>
                    {result.rows.map((row) => (
                      <td key={row.company.id}>{row.company.sector_group}</td>
                    ))}
                  </tr>
                  {result.emissions_metrics?.map((metric) => (
                    <tr key={metric.label} className="reported-metric-row">
                      <th scope="row">
                        {metric.label}
                        <p className="tiny muted">
                          {metric.year} · {metric.unit} · Carbon Majors
                        </p>
                      </th>
                      {metric.cells.map((cell, i) => (
                        <td key={result.rows[i].company.id}>
                          <strong>
                            {Intl.NumberFormat('en', { maximumFractionDigits: 2 }).format(
                              cell.value,
                            )}
                          </strong>
                          <p className="tiny muted">Parent: {cell.entity}</p>
                          <a
                            className="text-button small"
                            href="https://carbonmajors.org/Methodology"
                            target="_blank"
                            rel="noreferrer"
                          >
                            Scope and method ↗
                          </a>
                        </td>
                      ))}
                    </tr>
                  ))}
                  {result.metrics?.map((metric, index) => (
                    <tr key={`fact-${index}`} className="reported-metric-row">
                      <th scope="row">
                        {metric.label}
                        <p className="tiny muted">
                          {[
                            'See period and scope in each column',
                            metric.status === 'target' ? 'Target' : 'Reported',
                            metric.unit,
                            metric.scope ? `Scope ${metric.scope}` : null,
                            metric.basis,
                            metric.boundary,
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      </th>
                      {metric.cells.map((fact, i) => (
                        <td key={i} className={fact?.rank ? `metric-${fact.rank}` : ''}>
                          {fact ? (
                            <>
                              <strong>{fact.display}</strong>
                              <p className="tiny muted">
                                {[
                                  fact.period || 'Year not explicit',
                                  fact.scope ? `Scope ${fact.scope}` : null,
                                  fact.basis,
                                  fact.boundary,
                                  fact.review_required ? 'Review table mapping' : null,
                                ]
                                  .filter(Boolean)
                                  .join(' · ')}
                              </p>
                              {fact.rank && (
                                <small className="metric-ranking">
                                  {fact.rank === 'highest' ? 'Highest reported' : 'Lowest reported'}
                                </small>
                              )}
                              <a
                                className="text-button small"
                                href={sourceHref(fact)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {fact.page ? `p.${fact.page}` : 'Source'}
                              </a>
                            </>
                          ) : (
                            'Not comparable / not reported'
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {metrics.map(([label, getValue]) => (
                    <tr key={label}>
                      <th scope="row">{label}</th>
                      {result.rows.map((row) => (
                        <td key={row.company.id}>
                          {row.analysis ? friendlyLabel(getValue(row.analysis)) : 'Not analysed'}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr>
                    <th scope="row">Full company analysis</th>
                    {result.rows.map((row) => (
                      <td key={row.company.id}>
                        <a
                          className="text-button"
                          href={
                            row.analysis
                              ? `#/analysis/${row.analysis.id}`
                              : `#/investigate/${encodeURIComponent(row.company.id)}?mode=${mode}`
                          }
                        >
                          {row.analysis ? 'Explore sources' : 'View analysis'}
                          <ArrowRight size={14} />
                        </a>
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
          <ComparisonReadout rows={result.rows} sameSector={result.same_sector} />
        </>
      ) : (
        <Empty title="Bring two companies into focus">
          Choose companies from search or your watchlist to start comparing.
        </Empty>
      )}
    </div>
  );
}

function ComparisonReadout({ rows, sameSector }) {
  const comparable = rows.filter(
    (row) => row.analysis && row.analysis.coverage.status !== 'Limited evidence',
  );
  const values = comparable.filter((row) => row.analysis.scores.momentum.score != null);
  const mixedMethods = new Set(comparable.map((row) => row.analysis.scoring_version)).size > 1;
  const top = [...values].sort(
    (a, b) => b.analysis.scores.momentum.score - a.analysis.scores.momentum.score,
  )[0];
  return (
    <Panel title="What the comparison shows" actions={<Badge>Based on your latest analyses</Badge>}>
      <p className="research-summary">
        {!sameSector
          ? 'These companies operate in different sectors. Their scores are not ranked against one another. Choose sector peers to make a meaningful comparison.'
          : mixedMethods
            ? 'These analyses use different scoring methods. Refresh them before comparing score differences.'
            : values.length >= 2
              ? `${top.company.name} has the highest report-language indicator among the selected sector peers with sufficient coverage. This describes collected wording, not superior ESG performance. Inspect the underlying facts and boundaries.`
              : 'Add recent analyses with enough public information to compare company trends.'}
      </p>
      <p className="muted small">
        {sameSector
          ? 'Selected companies share a recorded sector, but the scores are not peer-normalised.'
          : 'These companies may operate in different sectors. Different reporting practices and business models limit direct score comparisons.'}{' '}
        This is a descriptive research comparison.
      </p>
    </Panel>
  );
}
