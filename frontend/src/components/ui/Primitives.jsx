import { AlertCircle, ArrowRight, FileText, Search, X } from 'lucide-react';

import { date } from '../../utils/formatters';
import { countryName } from '../../utils/presentation';
import { companyInitials } from '../../utils/research';

export function PageHeading({ eyebrow, title, children, actions }) {
  return (
    <header className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {children && <p className="page-description">{children}</p>}
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </header>
  );
}

export function Panel({ title, description, actions, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {description && <p className="muted small">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Badge({ children, tone = '' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function ModeBadge({ mode }) {
  return (
    <Badge tone={mode === 'demo' ? 'amber' : mode === 'report' ? 'blue' : 'green'}>
      {mode === 'demo' ? 'Demo data' : mode === 'report' ? 'Uploaded report' : 'Company research'}
    </Badge>
  );
}
export function ErrorNotice({ error, onRetry }) {
  if (!error) return null;
  return (
    <div role="alert" className="notice error">
      <AlertCircle size={18} />
      <div>{error}</div>
      {onRetry && (
        <button className="text-button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
export function Notice({ children, tone = '' }) {
  return (
    <div className={`notice ${tone}`}>
      <AlertCircle size={17} />
      <div>{children}</div>
    </div>
  );
}
export function Loading({ children = 'Loading your workspace…', variant = 'rows' }) {
  return (
    <div role="status" className={`loading-skeleton ${variant}`}>
      <span className="small muted">{children}</span>
      <div className="skeleton-content" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <div className="skeleton-row" key={i}>
            <span className="skeleton skeleton-avatar" />
            <div>
              <span className="skeleton skeleton-title" />
              <span className="skeleton skeleton-text" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <Search size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function CompanyIdentity({ company, small = false, heading = false }) {
  const Name = heading ? 'h1' : 'strong';
  return (
    <div className={`company-identity ${small ? 'compact' : ''}`}>
      <div className="company-avatar" aria-hidden="true">
        {companyInitials(company.name)}
      </div>
      <div>
        <Name>{company.name}</Name>
        <p>
          {[company.ticker, company.exchange, countryName(company.country)]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </div>
    </div>
  );
}
export function InvestigationLink({ item }) {
  return (
    <a className="investigation-row" href={`#/analysis/${item.id}`}>
      <FileText size={19} />
      <div className="grow">
        <strong>{item.company.name}</strong>
        <p className="muted small">
          {item.kind === 'report' ? 'Report analysis' : 'Company analysis'} ·{' '}
          {date(item.created_at)}
        </p>
      </div>
      <ModeBadge mode={item.mode} />
      <ArrowRight size={17} />
    </a>
  );
}
export function CloseButton({ onClick, label = 'Close' }) {
  return (
    <button className="icon-button" aria-label={label} onClick={onClick}>
      <X size={20} />
    </button>
  );
}
