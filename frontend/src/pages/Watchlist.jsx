import { countryName } from '../utils/presentation';
import { useEffect, useState } from 'react';
import { ArrowRight, CheckCheck, Folder, RefreshCw, Search, Star, Trash2 } from 'lucide-react';
import { api } from '../api';
import WatchlistTable from '../components/company/WatchlistTable';
import { usePulse } from '../context';
import { Badge, Empty, ErrorNotice, Notice, PageHeading, Panel } from '../components/ui/Primitives';

export default function Watchlist() {
  const { watchlist, session, refreshWorkspace, notify } = usePulse();
  const [query, setQuery] = useState('');
  const [folder, setFolder] = useState('all');
  const [country, setCountry] = useState('all');
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [jobs, setJobs] = useState([]);
  const [editing, setEditing] = useState(null);
  const [folderName, setFolderName] = useState('');
  useEffect(() => {
    if (!jobs.length) return;
    let stopped = false;
    let timer;
    const poll = async () => {
      try {
        const states = await Promise.all(jobs.map((job) => api(`/jobs/${job.id}`)));
        if (stopped) return;
        const finished = states.filter((job) => ['complete', 'failed'].includes(job.status));
        setProgress(`${finished.length}/${jobs.length} company updates finished`);
        if (finished.length === jobs.length) {
          setBusy(false);
          setJobs([]);
          await refreshWorkspace();
          const failed = states.filter((job) => job.status === 'failed');
          if (failed.length)
            setError(
              `${failed.length} updates need attention. You can retry individual companies.`,
            );
          else notify('Your watchlist is up to date.');
        } else {
          timer = setTimeout(poll, 1500);
        }
      } catch (err) {
        if (!stopped) {
          setError(err.message);
          setBusy(false);
          setJobs([]);
        }
      }
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobs, refreshWorkspace, notify]);
  const mutate = async (fn) => {
    try {
      await fn();
      await refreshWorkspace();
    } catch (err) {
      setError(err.message);
    }
  };
  const refresh = async () => {
    setBusy(true);
    setError('');
    setProgress('Preparing your company updates…');
    try {
      const result = await api('/watchlist/refresh', { method: 'POST' });
      setJobs(result.jobs);
      if (!result.jobs.length) setBusy(false);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };
  const folders = [...new Set(watchlist.map((row) => row.folder))];
  const countries = [...new Set(watchlist.map((row) => row.company.country))];
  const filtered = watchlist.filter(
    (row) =>
      `${row.company.name} ${row.company.ticker} ${row.company.sector}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (folder === 'all' || row.folder === folder) &&
      (country === 'all' || row.company.country === country) &&
      (!onlyUnread || row.unread),
  );
  const unread = watchlist.filter((row) => row.unread);
  return (
    <div className="page-stack">
      <PageHeading
        title="Watchlist"
        actions={
          <>
            <a className="button secondary" href="#/explore">
              <Star size={16} />
              Add companies
            </a>
            <button
              className="button primary"
              disabled={busy || !watchlist.length}
              onClick={refresh}
            >
              <RefreshCw size={16} className={busy ? 'spin' : ''} />
              {busy ? 'Refreshing…' : 'Refresh watchlist'}
            </button>
          </>
        }
      >
        Keep your companies organised and catch up on the latest ESG developments.
      </PageHeading>
      <div className="monitoring-banner">
        <span className="live-dot" />
        <p>
          {session.user
            ? `We check your tracked companies every ${session.refresh_hours} hours while this app is running.`
            : 'Refresh your watchlist whenever you like. Create an account to enable automatic checks when this app is running.'}
        </p>
        <Badge>{watchlist.length} companies</Badge>
      </div>
      <ErrorNotice error={error} />
      {busy && <Notice>{progress} You can keep exploring while we check for updates.</Notice>}
      <div className="watchlist-filters">
        <label className="input-icon">
          <Search size={17} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter tracked companies"
            placeholder="Filter your companies…"
          />
        </label>
        <select
          aria-label="Filter by watchlist folder"
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
        >
          <option value="all">All folders</option>
          {folders.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <select
          aria-label="Filter by company country"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        >
          <option value="all">All countries</option>
          {countries.map((c) => (
            <option key={c} value={c}>
              {countryName(c)}
            </option>
          ))}
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={onlyUnread}
            onChange={(e) => setOnlyUnread(e.target.checked)}
          />
          Unread updates ({unread.length})
        </label>
      </div>
      {editing && (
        <Panel title="Move company to a folder">
          <form
            className="folder-form"
            onSubmit={(event) => {
              event.preventDefault();
              mutate(async () => {
                await api(`/watchlist/${encodeURIComponent(editing)}`, {
                  method: 'PATCH',
                  body: JSON.stringify({ folder: folderName.trim() || 'My watchlist' }),
                });
                setEditing(null);
              });
            }}
          >
            <label htmlFor="edit-folder">Folder name</label>
            <input
              id="edit-folder"
              value={folderName}
              maxLength={60}
              onChange={(event) => setFolderName(event.target.value)}
              autoFocus
              list="watch-folders"
            />
            <button className="button primary" type="submit">
              Move
            </button>
            <button className="text-button" type="button" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </form>
        </Panel>
      )}
      {!filtered.length ? (
        <Panel>
          <Empty
            title={watchlist.length ? 'No companies match these filters' : 'No companies tracked'}
          >
            Find a company and select “Track company” on its analysis page.
            <a className="button primary" href="#/explore">
              Find companies
              <ArrowRight size={16} />
            </a>
          </Empty>
        </Panel>
      ) : (
        <Panel>
          <WatchlistTable
            rows={filtered}
            folders
            actions={(row) => (
              <>
                <button
                  className="icon-button"
                  title="Move to a folder"
                  aria-label={`Move ${row.company.name} to a folder`}
                  onClick={() => {
                    setEditing(row.company.id);
                    setFolderName(row.folder);
                  }}
                >
                  <Folder size={17} />
                </button>
                {row.unread && (
                  <button
                    className="icon-button"
                    title="Mark reviewed"
                    aria-label={`Mark ${row.company.name} reviewed`}
                    onClick={() =>
                      mutate(() =>
                        api(`/watchlist/${encodeURIComponent(row.company.id)}/seen`, {
                          method: 'POST',
                        }),
                      )
                    }
                  >
                    <CheckCheck size={17} />
                  </button>
                )}
                <button
                  className="icon-button danger-button"
                  title="Remove from watchlist"
                  aria-label={`Remove ${row.company.name} from watchlist`}
                  onClick={() =>
                    mutate(() =>
                      api(`/watchlist/${encodeURIComponent(row.company.id)}`, { method: 'DELETE' }),
                    )
                  }
                >
                  <Trash2 size={17} />
                </button>
              </>
            )}
          />
        </Panel>
      )}
      <datalist id="watch-folders">
        {folders.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      <Panel title="Understanding your updates">
        <p className="muted">
          Updates highlight new sources since your last review. Scores may also change as
          information ages or the scoring method improves. We show score differences only when the
          methods are comparable.
        </p>
      </Panel>
    </div>
  );
}
