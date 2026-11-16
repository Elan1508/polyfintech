import { useState } from 'react';
import { ArrowRight, Download, ExternalLink, Search, Star } from 'lucide-react';
import { date } from '../../utils/formatters';
import { Panel, Notice } from '../ui/Primitives';
import { briefUrl } from '../../api';
import { sourceHref } from '../../utils/presentation';

const sourceFor = (item, id) =>
  [...item.sources, ...(item.knowledge_sources || [])].find((s) => s.id === id);
const pageLink = sourceHref;

export function CompanySnapshot({ item, onSource }) {
  const snapshot = item.snapshot;
  if (!snapshot) return null;
  return (
    <Panel
      title="Company snapshot"
      actions={
        <a className="text-button" href={briefUrl(item.id)}>
          <Download size={15} /> Download brief
        </a>
      }
    >
      <p className="research-summary">
        {snapshot.summary || 'Company background is not available for this identity yet.'}
      </p>
      {snapshot.summary_source_id && (
        <button
          className="text-button small"
          onClick={() => onSource(sourceFor(item, snapshot.summary_source_id))}
        >
          Read overview source <ExternalLink size={13} />
        </button>
      )}
      <dl className="snapshot-facts">
        {snapshot.facts.map((f) => (
          <div key={f.label}>
            <dt>{f.label}</dt>
            <dd>
              <a href={f.url} target="_blank" rel="noreferrer">
                {f.value}
              </a>
              {f.as_of && <small>As of {date(f.as_of)}</small>}
            </dd>
          </div>
        ))}
      </dl>
      {snapshot.market.length > 0 && (
        <>
          <h3 className="section-title">Financial snapshot</h3>
          <div className="financial-grid">
            {snapshot.market.map((f) => (
              <a key={f.label} href={f.url} target="_blank" rel="noreferrer">
                <span>{f.label}</span>
                <strong>
                  {new Intl.NumberFormat('en', {
                    maximumFractionDigits: 2,
                    notation: Math.abs(f.value) >= 1e6 ? 'compact' : 'standard',
                  }).format(f.value)}{' '}
                  <small>{f.unit}</small>
                </strong>
                <small>
                  {f.as_of ? date(f.as_of) : 'Date not provided'} · {f.provider}
                </small>
              </a>
            ))}
          </div>
        </>
      )}
      <p className="muted small">
        {snapshot.notice} Checked {date(snapshot.collected_at)}.
      </p>
      {snapshot.warnings?.map((w) => (
        <p className="muted small" key={w}>
          {w}
        </p>
      ))}
    </Panel>
  );
}

export function CompanyBrief({ item, onSource }) {
  if (!item.brief?.items?.length) return null;
  return (
    <Panel title={item.brief.mode === 'ai' ? 'Company brief · AI summary' : 'Company brief'}>
      <div className="brief-lines">
        {item.brief.items
          .filter((line) => line.section !== 'Business' || !item.snapshot?.summary)
          .map((line, i) => (
            <article key={i}>
              <h3>{line.section}</h3>
              <p>{line.text}</p>
              <button
                className="text-button small"
                onClick={() => onSource(sourceFor(item, line.source_id))}
              >
                {line.publisher}
                {line.page ? ` · p.${line.page}` : ' · Source'} <ExternalLink size={13} />
              </button>
            </article>
          ))}
      </div>
      <p className="muted small">{item.brief.notice}</p>
      <p className="small">{item.brief.watch}</p>
    </Panel>
  );
}

export function ESGData({ item, onSource }) {
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const facts = item.facts?.items || [];
  const shown = facts.filter(
    (f) =>
      (filter === 'all' || f.status === filter) &&
      `${f.label} ${f.quote}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Panel
      title="ESG data"
      description="Figures and commitments taken directly from company documents."
    >
      <div className="evidence-filters">
        <label className="input-icon">
          <Search size={16} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find emissions, board, targets…"
            aria-label="Search report facts"
          />
        </label>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Fact type">
          <option value="all">All report facts</option>
          <option value="reported">Reported results</option>
          <option value="target">Targets and policies</option>
        </select>
      </div>
      <p className="muted small">
        {item.facts?.notice || 'Refresh this analysis to extract facts from the full report.'}{' '}
        {item.facts?.method === 'ai-assisted'
          ? 'AI selected the passages; quotations and values were checked against the document.'
          : 'Extracted with local pattern matching.'}
      </p>
      {!shown.length && (
        <Notice>
          {facts.length
            ? 'No facts match this filter.'
            : 'No clearly stated figures were extracted. Open the original report to review tables, or add a readable company report.'}
        </Notice>
      )}
      <div className="fact-list">
        {shown.map((f) => (
          <article className="fact-card" key={f.id}>
            <div className="fact-heading">
              <div>
                <span className={`fact-status ${f.status}`}>
                  {f.review_required
                    ? 'Table · review context'
                    : f.status === 'target'
                      ? 'Target or policy'
                      : 'Reported disclosure'}
                </span>
                <h3>{f.label}</h3>
              </div>
              <strong>{f.display}</strong>
            </div>
            <p className="small muted">
              {[
                f.period ? `Period ${f.period}` : 'Period not explicit in quote',
                f.scope ? `Scope ${f.scope}` : null,
                f.basis,
                f.boundary,
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <blockquote>{f.quote}</blockquote>
            {f.review_required && (
              <p className="small muted">
                AI extracted this figure. Review the quoted table headings and reporting scope
                before using it in a comparison.
              </p>
            )}
            <div className="button-row">
              <button
                className="text-button small"
                onClick={() => onSource(sourceFor(item, f.source_id))}
              >
                View evidence · {f.page ? `p.${f.page}` : f.section || 'Web section'}
              </button>
              <a className="text-button small" href={pageLink(f)} target="_blank" rel="noreferrer">
                Original report <ExternalLink size={13} />
              </a>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}

export function ScoreReasons({ item, onSource }) {
  if (!item.explanations) return null;
  return (
    <Panel title="Understand the scores">
      <div className="score-reasons">
        {[
          ['momentum', 'ESG report language'],
          ['risk', 'Risk flag pressure'],
          ['digital', 'Digital responsibility'],
        ].map(([key, label]) => (
          <details key={key}>
            <summary>
              {label} · Why {item.scores[key].score ?? 'unscored'}?
            </summary>
            <p className="muted small">{item.explanations[key].notice}</p>
            {item.explanations[key].drivers.length ? (
              item.explanations[key].drivers.map((d, i) => (
                <article className="score-driver" key={i}>
                  <strong>
                    {d.direction === 'raises' ? '+' : '−'}
                    {Math.abs(d.contribution)} points · {d.direction} this indicator
                  </strong>
                  <blockquote>{d.quote}</blockquote>
                  <p className="small muted">{d.reason}</p>
                  <button
                    className="text-button small"
                    onClick={() => onSource(sourceFor(item, d.source_id))}
                  >
                    Review source{d.page ? ` · p.${d.page}` : ''}
                  </button>
                </article>
              ))
            ) : (
              <p>
                No contributing directional evidence was found. An unscored value does not establish
                low risk.
              </p>
            )}
          </details>
        ))}
      </div>
    </Panel>
  );
}

export function NewsTimeline({ item, onSource }) {
  const [status, setStatus] = useState('all');
  const news = item.sources
    .filter((s) => s.kind === 'news')
    .sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''));
  const controversies = news.filter((s) => s.controversy);
  return (
    <>
      <Panel
        title="Controversies timeline"
        description="Reported allegations and adverse events, separated from routine announcements."
      >
        <label className="controversy-filter">
          Reported stage{' '}
          <select
            aria-label="Controversy status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="all">All stages</option>
            {['Alleged', 'Under investigation', 'Fined', 'Settled', 'Dismissed / overturned'].map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <p className="muted small">
          Automated classification of headlines and RSS excerpts. These tags do not establish
          wrongdoing.
        </p>
        {!controversies.length && (
          <Notice>
            No controversies were identified in the collected coverage. This is not a comprehensive
            check.
          </Notice>
        )}
        <ol className="news-timeline">
          {controversies
            .filter((s) => status === 'all' || s.case_status === status)
            .map((s) => (
              <NewsItem key={s.id} source={s} onSource={onSource} />
            ))}
        </ol>
        {controversies.length > 0 &&
          status !== 'all' &&
          !controversies.some((s) => s.case_status === status) && (
            <p className="muted small">No collected headlines report this stage.</p>
          )}
      </Panel>
      <Panel title="News by topic">
        <ol className="news-timeline">
          {news
            .filter((s) => !s.controversy)
            .map((s) => (
              <NewsItem key={s.id} source={s} onSource={onSource} />
            ))}
        </ol>
        {!news.length && <Notice>No relevant news was collected for this snapshot.</Notice>}
      </Panel>
    </>
  );
}
function NewsItem({ source, onSource }) {
  return (
    <li>
      <time>{date(source.published_at)}</time>
      <div>
        <div className="news-tags">
          {source.areas?.map((a) => (
            <span key={a}>
              {{ E: 'Environment', S: 'Social', G: 'Governance', digital: 'Digital' }[a]}
            </span>
          ))}
          <span>{source.sentiment || 'Unclassified'}</span>
          {source.case_status && (
            <span className="case-status">{source.case_status} · reported</span>
          )}
          {source.self_reported && <span>Company announcement</span>}
        </div>
        <button className="text-button" onClick={() => onSource(source)}>
          {source.title}
        </button>
        <p className="small muted">
          {source.publisher} · {source.text_coverage || 'Headline coverage'}
        </p>
        <p className="small">{source.excerpt}</p>
        {source.case_status && (
          <p className="small muted">
            {source.status_basis} A settlement does not establish an admission of wrongdoing. Open
            the source for the parties, outcome and any appeal.
          </p>
        )}
      </div>
    </li>
  );
}

export function NextSteps({ item, tracked, onTrack, onAsk, busy }) {
  const peers = item.next_steps?.peers || [];
  return (
    <Panel title="Continue your research">
      <div className="next-step-grid">
        {peers.length > 0 && (
          <a
            className="next-step"
            href={`#/compare?companies=${[item.company.id, ...peers.map((c) => c.id)].map(encodeURIComponent).join(',')}`}
          >
            <strong>
              Compare sector peers <ArrowRight size={16} />
            </strong>
            <span>{peers.map((p) => p.name).join(', ')}</span>
          </a>
        )}
        <button
          className="next-step"
          onClick={() =>
            onAsk(
              item.next_steps?.question ||
                `What emissions targets does ${item.company.name} report?`,
            )
          }
        >
          <strong>
            Explore the emissions targets <ArrowRight size={16} />
          </strong>
          <span>Ask the research assistant and review its source passages.</span>
        </button>
        {item.kind === 'company' && (
          <button className="next-step" disabled={tracked || busy} onClick={onTrack}>
            <strong>
              <Star size={16} />
              {tracked ? 'Company is tracked' : 'Track this company'}
            </strong>
            <span>Review new report facts and reported controversies in your watchlist.</span>
          </button>
        )}
      </div>
    </Panel>
  );
}
