import { date } from '../../utils/formatters';
import { useEffect, useRef } from 'react';
import { ExternalLink } from 'lucide-react';
import { sourceHref, sourceType } from '../../utils/presentation';
import { Badge, CloseButton } from '../ui/Primitives';

export default function SourceDrawer({ source, signals, close }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    dialog.showModal();
    const cancel = () => close();
    dialog.addEventListener('cancel', cancel);
    return () => {
      dialog.removeEventListener('cancel', cancel);
      dialog.close();
      previous?.focus();
    };
  }, [close]);
  return (
    <dialog
      className="source-dialog"
      ref={ref}
      aria-labelledby="source-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="dialog-heading">
        <Badge tone={source.kind === 'demo' ? 'amber' : 'blue'}>{sourceType(source)}</Badge>
        <CloseButton onClick={close} />
      </div>
      <h2 id="source-title">{source.title}</h2>
      <p className="muted small">
        {source.publisher} · {date(source.published_at)}
      </p>
      {source.url && (
        <a className="button secondary" href={sourceHref(source)} target="_blank" rel="noreferrer">
          Open original {source.page ? `at page ${source.page}` : 'source'}
          <ExternalLink size={16} />
        </a>
      )}
      <div className="source-fulltext">{source.excerpt}</div>
      {source.kind === 'news' && (
        <p className="muted small">
          {source.text_coverage || 'Headline and RSS excerpt'} · Article tags are automated. Open
          the publisher’s coverage for full context.
        </p>
      )}
      <h3>How this affects the ESG scores</h3>
      {signals.length ? (
        signals.map((signal) => (
          <div className="contribution" key={signal.id}>
            <div>
              <strong>
                {signal.dimension === 'digital' ? 'Digital responsibility' : signal.dimension} ·{' '}
                {signal.direction}
              </strong>
              <span>
                {signal.contribution >= 0 ? '+' : ''}
                {signal.contribution} pts
              </span>
            </div>
            <p>{signal.explanation}</p>
            <p className="tiny muted">
              Source weight {signal.source_weight} × recency {signal.freshness_weight}. Matched
              terms: {signal.terms.join(', ')}.
            </p>
          </div>
        ))
      ) : (
        <p className="muted">
          This passage adds background information without changing the ESG scores.
        </p>
      )}
      <p className="tiny muted">
        This passage is taken from the linked source. Company disclosures are self-reported; a
        phrase match does not confirm that a claim is accurate.
      </p>
    </dialog>
  );
}
