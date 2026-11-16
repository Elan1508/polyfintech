import { date } from '../../utils/formatters';
import { useMemo, useState } from 'react';
import { ExternalLink, FileText, Filter, Search } from 'lucide-react';
import { sourceHref, sourceType } from '../../utils/presentation';
import { Badge, Empty, Panel } from '../ui/Primitives';

export default function EvidencePanel({ analysis, onSource }) {
  const [category, setCategory] = useState('all');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(12);
  const grouped = useMemo(() => {
    const map = new Map();
    analysis.signals.forEach((signal) => {
      const list = map.get(signal.source_id) || [];
      list.push(signal);
      map.set(signal.source_id, list);
    });
    return map;
  }, [analysis.signals]);
  const variedTypes = new Set(analysis.sources.map(sourceType)).size > 1;
  const sources = analysis.sources
    .filter((source) => {
      const signals = grouped.get(source.id) || [];
      return (
        (category === 'all' || signals.some((s) => s.dimension === category)) &&
        `${source.title} ${source.excerpt} ${source.publisher}`
          .toLowerCase()
          .includes(query.toLowerCase())
      );
    })
    .sort((a, b) => Number(a.kind === 'news') - Number(b.kind === 'news'));
  return (
    <Panel
      title="Reports & sources"
      description={`${sources.length} relevant passages from ${analysis.coverage.source_count} sources. Explore the original publications for the full context.`}
      actions={
        <Badge>
          {analysis.coverage.publisher_count} publisher
          {analysis.coverage.publisher_count === 1 ? '' : 's'}
        </Badge>
      }
    >
      <div className="evidence-filters">
        <label className="input-icon">
          <Search size={16} />
          <input
            aria-label="Search reports and sources"
            placeholder="Search reports and sources…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(12);
            }}
          />
        </label>
        <label className="select-label">
          <Filter size={15} />
          <select
            aria-label="Filter sources by ESG area"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setLimit(12);
            }}
          >
            {[
              ['all', 'All ESG areas'],
              ['E', 'Environmental'],
              ['S', 'Social'],
              ['G', 'Governance'],
              ['digital', 'Digital responsibility'],
            ].map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!sources.length && (
        <Empty title="More research starts here">
          Try a different search or add a company report to expand the available information.
        </Empty>
      )}
      <div className="evidence-grid">
        {sources.slice(0, limit).map((source) => {
          const signals = grouped.get(source.id) || [];
          return (
            <article className="evidence-card" key={source.id} id={`source-${source.id}`}>
              <div className="evidence-meta">
                <span>
                  <FileText size={14} />
                  {source.publisher}
                </span>
                {variedTypes && source.kind !== 'demo' && (
                  <Badge
                    tone={source.kind === 'demo' ? 'amber' : source.kind === 'report' ? 'blue' : ''}
                  >
                    {source.kind === 'report'
                      ? source.section || `Page ${source.page}`
                      : sourceType(source)}
                  </Badge>
                )}
              </div>
              <h3>{source.title}</h3>
              <p className="source-excerpt">
                {source.excerpt.slice(0, 420)}
                {source.excerpt.length > 420 ? '…' : ''}
              </p>
              <div className="signal-tags">
                {signals.map((signal) => (
                  <Badge
                    key={signal.id}
                    tone={
                      signal.direction === 'negative'
                        ? 'red'
                        : signal.direction === 'positive'
                          ? 'green'
                          : ''
                    }
                  >
                    {signal.dimension === 'digital' ? 'Digital' : signal.dimension} ·{' '}
                    {signal.direction}
                  </Badge>
                ))}
              </div>
              <p className="muted tiny">
                Published: {date(source.published_at)}
                <br />
                Checked: {date(source.collected_at, true)}
              </p>
              <div className="evidence-actions">
                <button className="text-button" onClick={() => onSource(source)}>
                  Explore sources
                  <ExternalLink size={14} />
                </button>
                {source.url && (
                  <a
                    className="text-button"
                    href={sourceHref(source)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View original
                    <ExternalLink size={13} />
                  </a>
                )}
              </div>
            </article>
          );
        })}
      </div>
      {sources.length > limit && (
        <button className="button secondary load-more" onClick={() => setLimit((n) => n + 12)}>
          Show more passages
        </button>
      )}
    </Panel>
  );
}
