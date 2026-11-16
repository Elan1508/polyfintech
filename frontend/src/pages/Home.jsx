import { useEffect, useState } from 'react';
import { api } from '../api';
import { ArrowRight, Bookmark, FileSearch, RefreshCw, Star } from 'lucide-react';
import { usePulse } from '../context';
import { date } from '../utils/formatters';
import { friendlyLabel } from '../utils/presentation';
import CompanySearch from '../components/company/CompanySearch';
import WatchlistTable from '../components/company/WatchlistTable';
import { Empty, InvestigationLink, PageHeading, Panel } from '../components/ui/Primitives';

export default function Home() {
  const { watchlist, investigations, stats, navigate } = usePulse();
  const [discover, setDiscover] = useState(null);
  const [discoverError, setDiscoverError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api('/discover', { signal: controller.signal })
      .then(setDiscover)
      .catch((err) => {
        if (err.name !== 'AbortError') setDiscoverError(err.message);
      });
    return () => controller.abort();
  }, []);
  const firstVisit = watchlist.length === 0 && investigations.length === 0;
  const updates = watchlist
    .filter((row) => row.unread && row.analysis)
    .sort((a, b) => b.analysis.created_at.localeCompare(a.analysis.created_at));
  return (
    <div className="page-stack">
      <PageHeading title="Dashboard">
        Know what your money is backing. Explore company claims, climate evidence and recent
        changes.
      </PageHeading>
      <Panel title="Company search" className="dashboard-search">
        <CompanySearch
          resultsWhenQuery
          onSelect={(company) => navigate(`/investigate/${encodeURIComponent(company.id)}`)}
        />
      </Panel>
      {discover && (
        <Panel title="ASEAN companies and global benchmarks" description={discover.scope}>
          <div className="discover-grid">
            {discover.items.slice(0, 6).map((a) => (
              <a className="discover-card" href={`#/analysis/${a.id}`} key={a.id}>
                <strong>
                  {a.company.name} <ArrowRight size={15} />
                </strong>
                <p>{a.brief?.items?.[0]?.text || a.classification}</p>
                <span>
                  Report language {a.scores.momentum.score ?? 'Unscored'} · {a.source_count} sources
                  · {a.facts?.count || 0} report facts
                </span>
                {a.headline && <small>{a.headline.title}</small>}
                <small>Analysed {date(a.created_at)}</small>
              </a>
            ))}
          </div>
          <p className="muted small">
            {discover.ready}/{discover.total} public snapshots ready. {discover.schedule}
          </p>
        </Panel>
      )}
      {discoverError && (
        <p className="muted">Shared company research could not be loaded: {discoverError}</p>
      )}
      {firstVisit && !discover?.items?.length && (
        <section className="welcome-panel">
          <div>
            <h2>Start your research workspace</h2>
            <p>
              Find a company above and track it, or explore a sample analysis to see how the
              indicators and sources work.
            </p>
          </div>
          <div className="button-row">
            <a href="#/investigate/directory%3Adbs?mode=demo" className="button primary">
              Open sample analysis
              <ArrowRight size={16} />
            </a>
            <a href="#/reports" className="button secondary">
              <FileSearch size={16} />
              Upload a report
            </a>
          </div>
        </section>
      )}
      {!firstVisit && (
        <div className="stats-grid">
          {[
            [Star, watchlist.length, 'Companies tracked'],
            [RefreshCw, updates.length, 'Unreviewed updates'],
            [FileSearch, stats.live, 'Company analyses'],
            [Bookmark, stats.saved, 'Saved analyses'],
          ].map(([Icon, value, label]) => (
            <div className="stat-card" key={label}>
              <div>
                <span>{label}</span>
                <Icon size={18} />
              </div>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      )}
      <Panel
        title="Watchlist"
        description="Latest scores and changes since the previous comparable analysis."
        actions={
          <a className="text-button" href="#/watchlist">
            Manage watchlist
            <ArrowRight size={16} />
          </a>
        }
      >
        {watchlist.length ? (
          <WatchlistTable rows={watchlist.slice(0, 8)} />
        ) : (
          <Empty title="No companies tracked">
            Search for a company above, open its analysis and select “Track company”.
          </Empty>
        )}
        {watchlist.length > 8 && (
          <a className="text-button load-more" href="#/watchlist">
            View all {watchlist.length} companies
            <ArrowRight size={16} />
          </a>
        )}
      </Panel>
      <div className="dashboard-grid">
        <Panel
          title="Recent changes"
          description="Unreviewed updates from the companies you follow."
        >
          {updates.length ? (
            <ol className="changes-feed">
              {updates.slice(0, 6).map((row) => (
                <li key={row.company.id}>
                  <span className="feed-dot" />
                  <div>
                    <a href={`#/analysis/${row.analysis.id}`}>
                      {row.company.name}
                      <ArrowRight size={15} />
                    </a>
                    <p>
                      {row.update?.message ||
                        (!row.last_seen
                          ? `${row.analysis.source_count} sources · ${row.analysis.coverage.dimensions_covered}/4 areas scored. Ready for your first review.`
                          : friendlyLabel(row.changes?.message) || 'New analysis available.')}
                    </p>
                    <time dateTime={row.analysis.created_at}>
                      {date(row.analysis.created_at, true)}
                    </time>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <Empty title="No unreviewed changes">
              New sources and comparable score changes will appear here after a tracked company is
              refreshed.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Recent analyses"
          actions={
            <a href="#/saved" className="text-button">
              Research library
              <ArrowRight size={16} />
            </a>
          }
        >
          {investigations.length ? (
            investigations
              .slice(0, 5)
              .map((item) => <InvestigationLink key={item.id} item={item} />)
          ) : (
            <Empty title="No analyses yet">
              Your company and report analyses will appear here.
            </Empty>
          )}
        </Panel>
      </div>
    </div>
  );
}
