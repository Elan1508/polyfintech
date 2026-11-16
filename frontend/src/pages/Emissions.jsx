import { useEffect, useState } from 'react';
import { api } from '../api';
import { date } from '../utils/formatters';
import { ErrorNotice, Loading, Notice, PageHeading, Panel } from '../components/ui/Primitives';

export default function Emissions() {
  const [data, setData] = useState(null),
    [companies, setCompanies] = useState([]);
  const [file, setFile] = useState(null),
    [version, setVersion] = useState('');
  const [companyId, setCompanyId] = useState(''),
    [entity, setEntity] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    Promise.all([
      api('/emissions', { signal: controller.signal }),
      api('/companies?listed_only=true', { signal: controller.signal }),
    ])
      .then(([workspace, result]) => {
        setData(workspace);
        setCompanies(result.companies.filter((c) => c.carbon_producer));
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, [retry]);
  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('version', version);
      const result = await api('/emissions/import', { method: 'POST', body });
      setData(result);
      setMessage(
        result.unchanged
          ? 'This file is already in your workspace. Your active dataset is unchanged.'
          : 'Emissions data imported. Company pages now use this dataset in your workspace.',
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function map(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setMessage('');
    try {
      setData(
        await api('/emissions/mapping', {
          method: 'POST',
          body: JSON.stringify({ company_id: companyId, entity }),
        }),
      );
      setMessage('Parent mapping saved. Check its group boundary on the company page.');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-stack">
      <PageHeading title="Emissions data">
        Bring independent producer estimates into your company research.
      </PageHeading>
      <ErrorNotice error={error} onRetry={() => setRetry((n) => n + 1)} />
      {message && <Notice>{message}</Notice>}
      <Panel
        title="Import Carbon Majors data"
        description="Private to your workspace. The latest successful import supplies company trends."
      >
        <p>
          Download an official CSV from{' '}
          <a href="https://carbonmajors.org/Downloads" target="_blank" rel="noreferrer">
            Carbon Majors ↗
          </a>{' '}
          using your own account. High granularity includes CO₂ components and production; medium
          includes production; low includes annual emissions totals.
        </p>
        <p className="small muted">
          Use data within{' '}
          <a href="https://influencemap.org/terms" target="_blank" rel="noreferrer">
            InfluenceMap’s terms
          </a>
          . Imported rows are stored locally for your account and excluded from public research and
          AI prompts. File format is validated; the uploaded data’s authenticity is not
          independently checked. Source: InfluenceMap / Carbon Majors. For commercial use or
          redistribution, obtain the appropriate permission from the provider.
        </p>
        <form className="emissions-import-form" onSubmit={upload}>
          <label>
            Official CSV (up to 30 MB)
            <input
              type="file"
              accept=".csv,text/csv"
              required
              onChange={(e) => setFile(e.target.files[0] || null)}
            />
          </label>
          <label>
            Dataset release or version
            <input
              value={version}
              maxLength={100}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="e.g. January 2026 release"
            />
          </label>
          <button className="button primary" disabled={busy || !file}>
            {busy ? 'Working…' : 'Import emissions data'}
          </button>
        </form>
        <p className="small muted">
          Import one official file at a time. Totals from different granularities are never
          combined. Invalid imports leave your current dataset intact.
        </p>
      </Panel>
      {!data && !error && <Loading>Loading your emissions workspace…</Loading>}
      {data?.dataset ? (
        <Panel title="Active dataset">
          <dl className="dataset-summary">
            <div>
              <dt>File</dt>
              <dd>{data.dataset.filename}</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>
                {data.dataset.first_year}–{data.dataset.last_year} · {data.dataset.entity_count}{' '}
                parents
              </dd>
            </div>
            <div>
              <dt>Detail</dt>
              <dd>
                {data.dataset.granularity} · {data.dataset.row_count.toLocaleString()} unique rows
              </dd>
            </div>
            <div>
              <dt>Imported</dt>
              <dd>{date(data.dataset.created_at, true)}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{data.dataset.version || 'Not supplied'}</dd>
            </div>
          </dl>
          <details>
            <summary>Check a company’s parent mapping</summary>
            <p className="small muted">
              Reviewed exact names are matched automatically. If a dataset uses a different parent
              name, select it here only after checking the corporate boundary. A subsidiary is not
              interchangeable with its parent.
            </p>
            <form className="emissions-import-form" onSubmit={map}>
              <label>
                Producer company
                <select
                  required
                  value={companyId}
                  onChange={(e) => {
                    setCompanyId(e.target.value);
                    setEntity(data.mappings[e.target.value] || '');
                  }}
                >
                  <option value="">Choose company</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Carbon Majors parent
                <select required value={entity} onChange={(e) => setEntity(e.target.value)}>
                  <option value="">Choose exact parent</option>
                  {data.entities.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="button secondary" disabled={busy || !companyId || !entity}>
                Save parent mapping
              </button>
            </form>
          </details>
        </Panel>
      ) : (
        data && (
          <Notice>
            No Carbon Majors CSV imported yet. Report facts, company snapshots and sector
            comparisons remain available.
          </Notice>
        )
      )}
      <Panel title="Understanding the boundaries">
        <p>
          Carbon Majors covers parts of producers’ Scope 1 and downstream Scope 3. It does not
          represent every company’s operational footprint. Production is grouped by commodity and
          original unit.
        </p>
        <p>
          Country illustrations use a cached Climate TRACE CO₂ snapshot for matching full calendar
          years. CO₂ and CO₂e are kept separate, and overlapping company and country totals are
          never added.
        </p>
        <a
          className="text-button"
          href="https://carbonmajors.org/Methodology"
          target="_blank"
          rel="noreferrer"
        >
          Carbon Majors methodology ↗
        </a>
      </Panel>
    </div>
  );
}
