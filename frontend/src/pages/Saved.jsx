import { useEffect, useState } from 'react';
import { ArrowRight, Bookmark, Search } from 'lucide-react';
import { api } from '../api';
import {
  Badge,
  Empty,
  ErrorNotice,
  InvestigationLink,
  Loading,
  PageHeading,
  Panel,
} from '../components/ui/Primitives';

export default function Saved() {
  const [filter, setFilter] = useState('saved');
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError('');
    if (offset === 0) setRows([]);
    const timer = setTimeout(
      async () => {
        try {
          const data = await api(
            `/library?view=${filter}&kind=${kind}&q=${encodeURIComponent(query)}&offset=${offset}`,
            { signal: controller.signal },
          );
          setRows((items) =>
            offset
              ? [...new Map([...items, ...data.items].map((item) => [item.id, item])).values()]
              : data.items,
          );
          setTotal(data.total);
          setMore(data.has_more);
        } catch (err) {
          if (err.name !== 'AbortError') setError(err.message);
        } finally {
          if (!controller.signal.aborted) setBusy(false);
        }
      },
      query ? 250 : 0,
    );
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [filter, kind, query, offset, attempt]);
  const change = (setter, value) => {
    setOffset(0);
    setter(value);
  };
  return (
    <div className="page-stack">
      <PageHeading title="Saved research">
        Find saved company analyses and reports, ready whenever you want to revisit them.
      </PageHeading>
      <Panel>
        <div className="library-filters">
          <div className="segmented">
            <button
              className={filter === 'saved' ? 'active' : ''}
              onClick={() => change(setFilter, 'saved')}
            >
              <Bookmark size={15} />
              Saved
            </button>
            <button
              className={filter === 'all' ? 'active' : ''}
              onClick={() => change(setFilter, 'all')}
            >
              All research
            </button>
          </div>
          <label className="input-icon">
            <Search size={16} />
            <input
              aria-label="Search saved research"
              placeholder="Find company research…"
              maxLength={100}
              value={query}
              onChange={(e) => change(setQuery, e.target.value)}
            />
          </label>
          <select
            aria-label="Filter research type"
            value={kind}
            onChange={(e) => change(setKind, e.target.value)}
          >
            <option value="all">All types</option>
            <option value="company">Company analyses</option>
            <option value="report">Uploaded reports</option>
          </select>
          <Badge>{total} analyses</Badge>
        </div>
        <ErrorNotice error={error} onRetry={() => setAttempt((n) => n + 1)} />
        {rows.map((item) => (
          <InvestigationLink item={item} key={item.id} />
        ))}
        {busy && <Loading>Opening your research library…</Loading>}
        {!busy && !error && !rows.length && (
          <Empty title={filter === 'saved' ? 'Save research for later' : 'No matching research'}>
            Use “Save analysis” on a company or report analysis.
            <a className="button secondary" href="#/explore">
              Explore companies
              <ArrowRight size={15} />
            </a>
          </Empty>
        )}
        {more && !busy && (
          <button className="button secondary load-more" onClick={() => setOffset(rows.length)}>
            Load more research
          </button>
        )}
        {rows.length > 0 && (
          <p className="tiny muted">
            Showing {rows.length} of {total} matching analyses.
          </p>
        )}
      </Panel>
    </div>
  );
}
