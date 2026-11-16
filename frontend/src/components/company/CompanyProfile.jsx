import { ExternalLink, FileText } from 'lucide-react';
import { date } from '../../utils/formatters';
import { countryName } from '../../utils/presentation';
import { Badge, Panel } from '../ui/Primitives';

export default function CompanyProfile({
  profile,
  company,
  hasSources,
  onRefresh,
  busy,
  showNotice = true,
}) {
  if (!profile) return null;
  return (
    <Panel
      title={
        profile.documents?.some((d) => d.kind !== 'registry')
          ? 'Reports & disclosures'
          : 'About this company'
      }
      actions={<Badge tone={hasSources ? 'green' : 'blue'}>{profile.status}</Badge>}
    >
      <p className="research-summary">{profile.overview}</p>
      {profile.identity_facts?.length > 0 && (
        <dl className="company-facts">
          {profile.identity_facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>
                {fact.label === 'Location'
                  ? fact.value.split(', ').map(countryName).join(', ')
                  : fact.value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {profile.highlights?.length > 0 && (
        <ul className="research-highlights">
          {profile.highlights.map((item, index) => (
            <li key={index}>
              <p>{item.text}</p>
              <a href={item.url} target="_blank" rel="noreferrer">
                View source
                <ExternalLink size={12} />
              </a>
            </li>
          ))}
        </ul>
      )}
      {profile.documents?.length > 0 && (
        <div className="official-report-links">
          {profile.documents.map((doc) => (
            <a key={doc.url} href={doc.url} target="_blank" rel="noreferrer">
              <FileText size={17} />
              <span>
                {doc.title}
                <small>{doc.publisher}</small>
              </span>
              <ExternalLink size={14} />
            </a>
          ))}
        </div>
      )}
      {!hasSources && (
        <div className="research-empty-note">
          <h3>ESG research is still growing for this company</h3>
          <p>
            We’ve checked available company information. Public ESG disclosures may be limited,
            especially for smaller or unlisted businesses. Add a company report to build a fuller
            picture.
          </p>
          <div className="button-row">
            <a
              className="button secondary"
              href={`#/reports?company=${encodeURIComponent(company.id)}`}
            >
              Add a report
            </a>
            {onRefresh && (
              <button disabled={busy} className="text-button" onClick={onRefresh}>
                Check for updates
              </button>
            )}
          </div>
        </div>
      )}
      <p className="tiny muted research-profile-note">
        {showNotice && profile.notice}
        {profile.reviewed_at ? ` Sources checked ${date(profile.reviewed_at)}.` : ''}
      </p>
    </Panel>
  );
}
