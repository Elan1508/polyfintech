import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, FileText, Search, UploadCloud, X } from 'lucide-react';
import { api, fileUrl } from '../api';
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

export default function ReportLab({ reportId, companyId }) {
  const { navigate, refreshWorkspace } = usePulse();
  const [file, setFile] = useState(null);
  const [notes, setNotes] = useState('');
  const [tab, setTab] = useState('file');
  const [company, setCompany] = useState(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(Boolean(reportId));
  const [error, setError] = useState('');
  const [report, setReport] = useState(null);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [drag, setDrag] = useState(false);
  const input = useRef(null);
  useEffect(() => {
    if (!reportId) {
      setReport(null);
      return;
    }
    const controller = new AbortController();
    setBusy(true);
    api(`/reports/${encodeURIComponent(reportId)}`, { signal: controller.signal })
      .then((data) => {
        setReport(data);
        setPage(0);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [reportId, attempt]);
  useEffect(() => {
    if (!companyId || reportId) return;
    const controller = new AbortController();
    api(`/companies/${encodeURIComponent(companyId)}`, { signal: controller.signal })
      .then(setCompany)
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, [companyId, reportId]);
  const choose = (value) => {
    if (!value) return;
    setError('');
    if (!/\.(pdf|docx|txt)$/i.test(value.name)) {
      setError('Choose a PDF, DOCX, or TXT file.');
      return;
    }
    if (value.size > 12 * 1024 * 1024) {
      setError('Choose a document smaller than 12 MB.');
      return;
    }
    setFile(value);
  };
  const run = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    const data = new FormData();
    data.append(
      'file',
      tab === 'file'
        ? file
        : new File([notes], `${title.trim() || 'Research notes'}.txt`, { type: 'text/plain' }),
    );
    if (company) data.append('company_id', company.id);
    data.append('title', title);
    try {
      const result = await api('/reports', { method: 'POST', body: data });
      await refreshWorkspace();
      navigate(`/analysis/${result.analysis_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const pages =
    report?.pages
      .map((p, index) => ({ ...p, index }))
      .filter((p) => !query || p.text.toLowerCase().includes(query.toLowerCase())) || [];
  if (reportId && !report)
    return (
      <div className="page-stack">
        <PageHeading title="Opening the source document.">
          Loading your private extracted pages.
        </PageHeading>
        {busy ? (
          <Loading>Opening the document…</Loading>
        ) : (
          <ErrorNotice
            error={error || 'Document not found.'}
            onRetry={() => setAttempt((n) => n + 1)}
          />
        )}
        <a className="text-button" href="#/reports">
          Return to report lab
          <ArrowRight size={15} />
        </a>
      </div>
    );
  return (
    <div className="page-stack">
      <PageHeading title={report ? report.filename : 'Report lab'}>
        {report
          ? 'Inspect the extracted text and open the original document at its source page.'
          : 'Upload a company document, inspect its evidence, and ask questions with page-level references.'}
      </PageHeading>
      <ErrorNotice error={error} />
      {report ? (
        <>
          <div className="button-row">
            <a className="button secondary" href="#/reports">
              Analyse another document
            </a>
            <a
              className="button primary"
              target="_blank"
              rel="noreferrer"
              href={fileUrl(report.id, report.pages[page]?.page)}
            >
              Open original document
              <ArrowRight size={16} />
            </a>
            <Badge>{report.pages.length} pages / sections</Badge>
          </div>
          <div className="report-reader">
            <Panel title="Extracted pages">
              <label className="input-icon">
                <Search size={16} />
                <input
                  placeholder="Find in document…"
                  aria-label="Find text in document"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <div className="page-list">
                {pages.map((p) => (
                  <button
                    key={p.index}
                    onClick={() => setPage(p.index)}
                    aria-current={page === p.index ? 'page' : undefined}
                    className={page === p.index ? 'active' : ''}
                  >
                    <FileText size={15} />
                    {p.label}
                    <small>{p.text.length} characters</small>
                  </button>
                ))}
              </div>
              {!pages.length && <p className="muted small">No matching passages.</p>}
            </Panel>
            <Panel
              title={report.pages[page]?.label || 'Document text'}
              description="Extracted text can differ from the original visual layout."
            >
              <pre className="report-text">
                {report.pages[page]?.text || 'This page has no extractable text.'}
              </pre>
            </Panel>
          </div>
        </>
      ) : (
        <div className="report-grid">
          <Panel>
            <div className="segmented" role="group" aria-label="Report input method">
              <button className={tab === 'file' ? 'active' : ''} onClick={() => setTab('file')}>
                Upload document
              </button>
              <button className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>
                Paste research notes
              </button>
            </div>
            <form onSubmit={run} className="report-form">
              {tab === 'file' ? (
                <>
                  <input
                    className="sr-only"
                    tabIndex={-1}
                    ref={input}
                    type="file"
                    accept=".pdf,.docx,.txt"
                    aria-label="Choose a report document"
                    onChange={(e) => choose(e.target.files?.[0])}
                  />
                  <button
                    type="button"
                    className={`dropzone ${drag ? 'dragging' : ''}`}
                    onClick={() => input.current?.click()}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDrag(true);
                    }}
                    onDragLeave={() => setDrag(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDrag(false);
                      choose(e.dataTransfer.files[0]);
                    }}
                  >
                    <UploadCloud size={33} />
                    <strong>{file ? file.name : 'Drop a report here, or browse'}</strong>
                    <span>PDF, DOCX, TXT · Up to 12 MB</span>
                    {file && (
                      <Badge tone="green">
                        <Check size={13} />
                        {(file.size / 1024).toFixed(0)} KB selected
                      </Badge>
                    )}
                  </button>
                </>
              ) : (
                <label className="field-label">
                  Report excerpts or research notes
                  <textarea
                    rows={12}
                    maxLength={500000}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Paste the source passages you want to investigate…"
                  />
                </label>
              )}
              <label className="field-label">
                Analysis title <span className="muted">(optional)</span>
                <input
                  value={title}
                  maxLength={120}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Sustainability report review"
                />
              </label>
              <div>
                <div className="field-label">
                  Link to a company <span className="muted">(optional)</span>
                </div>
                {company ? (
                  <div className="selected-company">
                    <CompanyIdentity company={company} small />
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Remove linked company"
                      onClick={() => setCompany(null)}
                    >
                      <X size={17} />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => setSearchOpen((s) => !s)}
                  >
                    <Search size={16} />
                    Choose a company
                  </button>
                )}
                {searchOpen && (
                  <CompanySearch
                    compact
                    onSelect={(value) => {
                      setCompany(value);
                      setSearchOpen(false);
                    }}
                  />
                )}
              </div>
              <button
                className="button primary full-width"
                disabled={busy || (tab === 'file' ? !file : notes.trim().length < 30)}
                type="submit"
              >
                <FileText size={17} />
                {busy ? 'Extracting and analysing…' : 'Analyse document'}
                <ArrowRight size={16} />
              </button>
              {busy && <Loading>Reading your report and preparing the ESG insights…</Loading>}
            </form>
          </Panel>
          <div className="page-stack">
            <Panel title="Turn reports into useful insights">
              <ol className="report-steps">
                <li>
                  <span>01</span>
                  <div>
                    <h3>Explore the report</h3>
                    <p>
                      PDF pages retain page numbers. DOCX and TXT references use extracted sections.
                    </p>
                  </div>
                </li>
                <li>
                  <span>02</span>
                  <div>
                    <h3>Understand the ESG insights</h3>
                    <p>
                      See what the report says about environmental, social, governance and digital
                      topics.
                    </p>
                  </div>
                </li>
                <li>
                  <span>03</span>
                  <div>
                    <h3>Find answers with source links</h3>
                    <p>
                      Find relevant passages or get AI answers when connected, with references to
                      the original document.
                    </p>
                  </div>
                </li>
              </ol>
            </Panel>
            <Notice>
              Scanned pages need text recognition before upload. Claims in uploaded reports are not
              independently verified.
            </Notice>
            <div className="quiet-note">
              <strong>Private to your workspace</strong>
              <p>
                Your reports and research are private to your workspace. Create an account to keep
                access across devices. When you ask an AI question, relevant passages are shared
                with the connected AI provider to prepare your answer.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
