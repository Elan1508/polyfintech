import CompanySearch from '../components/company/CompanySearch';
import { PageHeading, Panel } from '../components/ui/Primitives';
import { usePulse } from '../context';

export default function Explorer() {
  const { navigate } = usePulse();
  return (
    <div className="page-stack">
      <PageHeading title="Company explorer">
        Explore ASEAN companies and global benchmarks by sector. Read the evidence behind the
        language.
      </PageHeading>
      <Panel>
        <CompanySearch
          onSelect={(company) => navigate(`/investigate/${encodeURIComponent(company.id)}`)}
        />
      </Panel>
      <p className="small muted">
        The awareness collection spans energy, mining, materials, food, transport, banks and
        technology. The full directory and worldwide legal-entity search remain available. Language
        scores describe collected wording, not measured ESG performance; missing data is shown
        explicitly.
      </p>
    </div>
  );
}
