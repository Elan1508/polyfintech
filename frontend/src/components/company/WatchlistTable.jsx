import { lazy, Suspense } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { CompanyIdentity } from '../ui/Primitives';
import { ScoreValue } from '../intelligence/ScoreVisual';
import { previousChanges } from '../../utils/research';
import { date } from '../../utils/formatters';

const Sparkline = lazy(() => import('../intelligence/Sparkline'));
export default function WatchlistTable({ rows, actions, folders = false }) {
  return (
    <div
      className="table-scroll workspace-table"
      role="region"
      aria-label="Watchlist scores and changes"
      tabIndex={0}
    >
      <table>
        <caption className="sr-only">
          Latest collected company scores. Changes are since the previous analysis using the same
          scoring method. Trend lines show actual dated momentum observations.
        </caption>
        <thead>
          <tr>
            <th scope="col">Company</th>
            <th scope="col">Report language</th>
            <th scope="col">Risk signals</th>
            <th scope="col">Digital responsibility</th>
            <th scope="col">Language history</th>
            <th scope="col">Updated</th>
            <th scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const changes = previousChanges(row.trend);
            const href = row.analysis
              ? `#/analysis/${row.analysis.id}`
              : `#/investigate/${encodeURIComponent(row.company.id)}`;
            return (
              <tr key={row.company.id}>
                <td>
                  <a href={href} className="company-table-link">
                    <CompanyIdentity company={row.company} small />
                    {row.unread && <span className="unread-dot" aria-label="Unread update" />}
                  </a>
                  {folders && <span className="small muted row-folder">{row.folder}</span>}
                  {row.update && (
                    <p className={`watch-update ${row.update.kind}`}>
                      <a href={href}>{row.update.message}</a>
                      <small>
                        {row.update.publisher}
                        {row.update.published_at ? ` · ${date(row.update.published_at)}` : ''}
                      </small>
                    </p>
                  )}
                </td>
                {['momentum', 'risk', 'digital'].map((metric) => (
                  <td key={metric}>
                    <ScoreValue
                      analysis={row.analysis}
                      metric={metric}
                      delta={changes[metric]}
                      showChange
                    />
                  </td>
                ))}
                <td>
                  <Suspense fallback={<span className="skeleton skeleton-spark" />}>
                    <Sparkline rows={row.trend} />
                  </Suspense>
                </td>
                <td className="small muted">
                  {row.analysis ? (
                    <time dateTime={row.analysis.created_at}>
                      {date(row.analysis.created_at, true)}
                    </time>
                  ) : (
                    'Not analysed'
                  )}
                </td>
                <td>
                  <div className="table-actions">
                    {actions ? (
                      actions(row)
                    ) : (
                      <a
                        className="icon-button"
                        href={href}
                        aria-label={`Open ${row.company.name}`}
                      >
                        <ArrowUpRight size={18} />
                      </a>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
