import { Fragment, useEffect, useRef, useState } from 'react';
import { ArrowRight, Search } from 'lucide-react';
import { api } from '../../api';
import { Badge, CompanyIdentity, Empty, ErrorNotice, Loading } from '../ui/Primitives';
import { ScoreValue } from '../intelligence/ScoreVisual';

export default function CompanySearch({
  onSelect,
  compact = false,
  selected = [],
  resultsWhenQuery = false,
}) {
  const [query, setQuery] = useState(''),
    [scope, setScope] = useState('listed');
  const [rows, setRows] = useState([]),
    [warnings, setWarnings] = useState([]);
  const [loading, setLoading] = useState(!resultsWhenQuery),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0);
  const request = useRef(0);
  const [sector, setSector] = useState('all'),
    [collection, setCollection] = useState('all');
  const sectors = [
    ...new Set(rows.map((c) => c.sector_group || c.sector || 'Not classified')),
  ].sort();
  const visible = rows
    .filter(
      (c) =>
        (compact || sector === 'all' || (c.sector_group || c.sector) === sector) &&
        (compact ||
          collection === 'all' ||
          (collection === 'focus' ? c.awareness_focus : c.region_group === collection)),
    )
    .sort((a, b) =>
      compact
        ? 0
        : (a.sector_group || a.sector || '').localeCompare(b.sector_group || b.sector || '') ||
          a.name.localeCompare(b.name),
    );
  const showResults = !resultsWhenQuery || query.trim().length > 0;
  useEffect(() => {
    const controller = new AbortController(),
      sequence = ++request.current;
    if (!showResults) {
      setRows([]);
      setWarnings([]);
      setError('');
      setLoading(false);
      return () => controller.abort();
    }
    setLoading(true);
    const timer = setTimeout(
      async () => {
        try {
          const result = await api(
            `/companies?q=${encodeURIComponent(query.trim())}&listed_only=${scope === 'listed'}`,
            { signal: controller.signal },
          );
          if (sequence !== request.current) return;
          setRows(result.companies);
          setWarnings(result.warnings);
          setError('');
        } catch (err) {
          if (err.name !== 'AbortError' && sequence === request.current) setError(err.message);
        } finally {
          if (sequence === request.current && !controller.signal.aborted) setLoading(false);
        }
      },
      query.trim() ? 450 : 0,
    );
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, retry, scope, showResults]);
  return (
    <div className={`company-search ${compact ? 'compact' : ''}`}>
      <label className="search-field">
        <Search size={21} />
        <input
          aria-label="Search companies by name or ticker"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search company name or ticker"
        />
      </label>
      <div className="company-search-options">
        <p className="search-caption">
          {showResults
            ? 'Scores use your latest analysis, or shared public research when available.'
            : 'Find a company to open its research and source documents.'}
        </p>
        <select
          aria-label="Company search scope"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
        >
          <option value="listed">Listed companies</option>
          <option value="all">All companies & legal entities</option>
        </select>
      </div>
      {!compact && showResults && (
        <div className="explorer-filters">
          <label>
            Sector
            <select value={sector} onChange={(e) => setSector(e.target.value)}>
              <option value="all">All sectors</option>
              {sectors.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Collection
            <select value={collection} onChange={(e) => setCollection(e.target.value)}>
              <option value="all">All companies</option>
              <option value="focus">Awareness collection</option>
              <option value="ASEAN">ASEAN</option>
              <option value="Global benchmark">Global benchmarks</option>
            </select>
          </label>
          <span className="small muted" aria-live="polite">
            {visible.length} companies · Language indicators are not performance ratings.
          </span>
        </div>
      )}
      <ErrorNotice error={error} onRetry={() => setRetry((n) => n + 1)} />
      {warnings.map((w) => (
        <p key={w} className="small warning-text">
          {w}
        </p>
      ))}
      {showResults &&
        (loading ? (
          <Loading>Finding companies…</Loading>
        ) : visible.length ? (
          compact ? (
            <div className="company-results">
              {visible.map((company) => (
                <button
                  className="company-result"
                  key={company.id}
                  disabled={selected.includes(company.id)}
                  onClick={() => onSelect(company)}
                >
                  <CompanyIdentity company={company} small />
                  <div className="result-end">
                    {selected.includes(company.id) && <Badge>Selected</Badge>}
                    <ArrowRight size={17} />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div
              className="table-scroll explorer-table"
              role="region"
              aria-label="Company search results"
              tabIndex={0}
            >
              <table>
                <caption className="sr-only">
                  Companies, recorded sectors and your latest collected ESG scores. Unanalysed
                  companies have no scores.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Company</th>
                    <th scope="col">Sector</th>
                    <th scope="col">Report language</th>
                    <th scope="col">Risk signals</th>
                    <th scope="col">Digital responsibility</th>
                    <th scope="col">Sources</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((company, index) => (
                    <Fragment key={company.id}>
                      {(index === 0 ||
                        visible[index - 1].sector_group !== company.sector_group) && (
                        <tr className="sector-heading">
                          <th colSpan={6} scope="rowgroup">
                            {company.sector_group || company.sector || 'Not classified'}
                          </th>
                        </tr>
                      )}
                      <tr>
                        <td>
                          <button
                            className="company-table-button"
                            onClick={() => onSelect(company)}
                          >
                            <CompanyIdentity company={company} small />
                          </button>
                        </td>
                        <td className="small muted">
                          {company.sector_group || company.sector || '—'}
                          <span className="coverage-note">{company.region_group}</span>
                        </td>
                        {['momentum', 'risk', 'digital'].map((metric) => (
                          <td key={metric}>
                            <ScoreValue analysis={company.analysis} metric={metric} />
                          </td>
                        ))}
                        <td className="small muted">
                          {company.analysis ? (
                            <>
                              {company.analysis.source_count}
                              {company.analysis.coverage.status === 'Limited evidence' && (
                                <span className="coverage-note">Limited coverage</span>
                              )}
                            </>
                          ) : (
                            'Not analysed'
                          )}
                        </td>
                      </tr>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : (
          !error && (
            <Empty title="No matching companies">
              Try a full company name or ticker.
              {scope === 'listed' && (
                <button className="text-button" onClick={() => setScope('all')}>
                  Search all legal entities
                  <ArrowRight size={14} />
                </button>
              )}
            </Empty>
          )
        ))}
      {scope === 'all' && (
        <p className="muted small search-footer">
          Check the registered name and location. Similarly named businesses may be unrelated.
        </p>
      )}
    </div>
  );
}
