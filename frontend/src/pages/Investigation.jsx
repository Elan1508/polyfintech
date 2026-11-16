import {
  CompanySnapshot,
  CompanyBrief,
  ESGData,
  ScoreReasons,
  NewsTimeline,
  NextSteps,
} from '../components/intelligence/CompanyResearch';
import { date } from '../utils/formatters';
import { friendlyLabel, metricNames } from '../utils/presentation';
import CompanyProfile from '../components/company/CompanyProfile';
import ClimateAwareness from '../components/intelligence/ClimateAwareness';
import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Check,
  FileText,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Star,
  TrendingUp,
} from 'lucide-react';
import { analyse, api } from '../api';
import { usePulse } from '../context';
import {
  CompanyIdentity,
  ErrorNotice,
  Loading,
  ModeBadge,
  Notice,
  PageHeading,
  Panel,
} from '../components/ui/Primitives';
import EvidencePanel from '../components/intelligence/EvidencePanel';
import SourceDrawer from '../components/intelligence/SourceDrawer';
import ScoreMethod from '../components/intelligence/ScoreMethod';
import ResearchAssistant from '../components/intelligence/ResearchAssistant';
import { ScoreMetric } from '../components/intelligence/ScoreVisual';
const HistoryChart = lazy(() => import('../components/intelligence/HistoryChart'));
const ScenarioSandbox = lazy(() => import('../components/intelligence/ScenarioSandbox'));

export default function Investigation({ companyId, analysisId, mode = 'live' }) {
  const { session, watchlist, refreshWorkspace, notify, navigate } = usePulse();
  const [item, setItem] = useState(null);
  const [busy, setBusy] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [stage, setStage] = useState('Preparing your analysis');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [source, setSource] = useState(null);
  const [tab, setTab] = useState('overview');
  const tabsId = useId();
  const tabRefs = useRef({});
  const [profile, setProfile] = useState(null);
  const [suggestedQuestion, setSuggestedQuestion] = useState(null);
  const closeSource = useCallback(() => setSource(null), []);
  const showSource = useCallback((value) => setSource(value), []);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError('');
    setItem(null);
    (async () => {
      try {
        const result = analysisId
          ? await api(`/analyses/${encodeURIComponent(analysisId)}`, { signal: controller.signal })
          : await analyse(companyId, mode, (job) => setStage(job.stage), {
              signal: controller.signal,
              refresh: attempt > 0,
            });
        if (controller.signal.aborted) return;
        setItem(result);
        setBusy(false);
        await refreshWorkspace();
      } catch (err) {
        if (err.name !== 'AbortError') {
          setError(err.message);
          setBusy(false);
        }
      }
    })();
    return () => controller.abort();
  }, [analysisId, companyId, mode, attempt, refreshWorkspace]);
  useEffect(() => {
    setProfile(item?.research || null);
    if (!item || item.kind !== 'company' || item.mode === 'demo' || item.research) return;
    const controller = new AbortController();
    api(`/companies/${encodeURIComponent(item.company.id)}/research`, { signal: controller.signal })
      .then(setProfile)
      .catch((err) => {
        if (err.name !== 'AbortError')
          notify('Company details could not be loaded. Please try again.', 'error');
      });
    return () => controller.abort();
  }, [item?.id, notify]);
  const mutate = async (fn) => {
    setActionBusy(true);
    try {
      await fn();
      await refreshWorkspace();
    } catch (err) {
      notify(err.message, 'error');
    } finally {
      setActionBusy(false);
    }
  };
  const refresh = async () => {
    setActionBusy(true);
    setError('');
    try {
      const result = await analyse(item.company.id, item.mode, (job) => setStage(job.stage), {
        refresh: true,
      });
      navigate(`/analysis/${result.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setActionBusy(false);
    }
  };
  if (busy)
    return (
      <div className="page-stack">
        <a className="text-button" href="#/explore">
          <ArrowLeft size={16} />
          Back to companies
        </a>
        <PageHeading title="Company analysis">
          Checking official reports and recent news.
        </PageHeading>
        <Loading variant="page">{stage}</Loading>
      </div>
    );
  if (!item)
    return (
      <div className="page-stack">
        <PageHeading title="Analysis unavailable" />
        <ErrorNotice error={error} onRetry={() => setAttempt((n) => n + 1)} />
        <a className="button secondary" href="#/explore">
          Find a company
        </a>
      </div>
    );
  const tracked = watchlist.some((row) => row.company.id === item.company.id);
  const context = item.context || {};
  const tabs = [
    ['overview', 'Overview'],
    ['data', 'ESG data'],
    ['climate', 'Climate & impact'],
    ['news', 'News & controversies'],
    ['sources', 'Sources'],
    ...(item.kind === 'company'
      ? [
          ['history', 'History'],
          ['scenario', 'Scenario'],
        ]
      : []),
  ];
  const notes = [...new Set([profile?.notice, ...item.warnings].filter(Boolean))];
  const peerMetrics = context.peers?.metrics || {};
  const changeTab = (event, index) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
    if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabs.length - 1;
    if (next == null) return;
    event.preventDefault();
    setTab(tabs[next][0]);
    tabRefs.current[tabs[next][0]]?.focus();
  };
  return (
    <div className="page-stack">
      <div className="investigation-toolbar">
        <a className="text-button" href="#/explore">
          <ArrowLeft size={16} />
          Companies
        </a>
        <ModeBadge mode={item.mode} />
      </div>
      <div className="investigation-heading">
        <div>
          <CompanyIdentity company={item.company} heading />
          <p className="muted small">
            {item.company.sector} · Analysed {date(item.created_at, true)}
          </p>
          {item.company.identity_url && (
            <a
              className="text-button small"
              href={item.company.identity_url}
              target="_blank"
              rel="noreferrer"
            >
              View company details ↗
            </a>
          )}
        </div>
        <div className="button-row">
          <button
            disabled={actionBusy}
            className={`button ${item.saved ? 'selected' : 'secondary'}`}
            onClick={() =>
              mutate(async () => {
                const saved = await api(`/analyses/${item.id}`, {
                  method: 'PATCH',
                  body: JSON.stringify({ saved: !item.saved }),
                });
                setItem((a) => ({ ...a, id: saved.analysis_id, public: false, saved: !a.saved }));
                if (saved.analysis_id !== item.id) navigate(`/analysis/${saved.analysis_id}`);
                notify(item.saved ? 'Removed from saved research.' : 'Analysis saved.');
              })
            }
          >
            {item.saved ? <Check size={17} /> : <Bookmark size={17} />}
            {item.saved ? 'Saved' : 'Save analysis'}
          </button>
          {item.kind === 'company' && (
            <>
              <button
                disabled={actionBusy}
                className={`button ${tracked ? 'selected' : 'secondary'}`}
                onClick={() =>
                  mutate(async () => {
                    await api(
                      tracked ? `/watchlist/${encodeURIComponent(item.company.id)}` : '/watchlist',
                      {
                        method: tracked ? 'DELETE' : 'POST',
                        ...(tracked
                          ? {}
                          : { body: JSON.stringify({ company_id: item.company.id }) }),
                      },
                    );
                    notify(
                      tracked ? 'Company removed from watchlist.' : 'Company added to watchlist.',
                    );
                  })
                }
              >
                <Star size={17} />
                {tracked ? 'Tracking' : 'Track company'}
              </button>
              <button disabled={actionBusy} className="button primary" onClick={refresh}>
                <RefreshCw size={17} className={actionBusy ? 'spin' : ''} />
                {actionBusy ? 'Refreshing' : 'Refresh'}
              </button>
            </>
          )}
        </div>
      </div>
      <ErrorNotice error={error} />
      {item.kind === 'company' &&
        item.mode === 'live' &&
        (item.research_version !== session.research_version ||
          item.collection?.version !== session.news_version) && (
          <Notice>
            Updated research is available. Refresh this analysis for the latest company reports and
            news matches.
          </Notice>
        )}
      {item.mode === 'demo' && (
        <Notice tone="amber">
          Demo data illustrates the research tools.{' '}
          <button
            className="text-button"
            onClick={() => navigate(`/investigate/${encodeURIComponent(item.company.id)}`)}
          >
            Open collected research
            <ArrowRight size={15} />
          </button>
        </Notice>
      )}
      <CompanySnapshot item={item} onSource={showSource} />
      <CompanyBrief item={item} onSource={showSource} />
      {item.public && (
        <p className="muted small">
          Shared public research · {date(item.created_at, true)}. Save a copy to your workspace to
          keep this snapshot.
        </p>
      )}
      {item.coverage.source_count > 0 ? (
        <div className="metric-grid">
          {[
            ['momentum', TrendingUp],
            ['risk', ShieldAlert],
            ['digital', Sparkles],
          ].map(([key, Icon]) => (
            <ScoreMetric
              key={key}
              metric={key}
              label={metricNames[key]}
              score={item.scores[key].score}
              detail={item.scores[key].label}
              icon={Icon}
              delta={context.score_changes?.[key]}
              flagCount={item.risk_flag_count}
              hasSources={item.coverage.source_count > 0}
              peer={peerMetrics[key]}
            />
          ))}
          <div className="metric coverage-metric">
            <div className="metric-top">
              <span>Research coverage</span>
              <FileText size={19} />
            </div>
            <div className="metric-value">
              {item.coverage.source_count}
              <span>{item.coverage.source_count === 1 ? ' source' : ' sources'}</span>
            </div>
            <p>{item.coverage.dimensions_covered}/4 areas scored</p>
            <p className="metric-context">
              {item.coverage.recent_count} {item.coverage.recent_count === 1 ? 'source' : 'sources'}{' '}
              published in the past 90 days
            </p>
            <button className="text-button" onClick={() => setTab('sources')}>
              Review sources
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      ) : (
        <Notice>
          Company profile available. Scores appear when there is enough relevant reporting to assess
          this business.
        </Notice>
      )}
      <NextSteps
        item={item}
        tracked={tracked}
        busy={actionBusy}
        onTrack={() =>
          mutate(() =>
            api('/watchlist', {
              method: 'POST',
              body: JSON.stringify({ company_id: item.company.id }),
            }),
          )
        }
        onAsk={(q) => {
          setSuggestedQuestion({ text: q, key: Date.now() });
          document
            .getElementById('research-assistant')
            ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }}
      />
      <div className="investigation-layout">
        <div className="analysis-main">
          <div className="analysis-tabs" role="tablist" aria-label="Company analysis sections">
            {tabs.map(([key, label], index) => (
              <button
                key={key}
                ref={(element) => {
                  tabRefs.current[key] = element;
                }}
                id={`${tabsId}-${key}-tab`}
                role="tab"
                aria-label={
                  key === 'sources'
                    ? `Sources, ${item.coverage.source_count} ${item.coverage.source_count === 1 ? 'source' : 'sources'}`
                    : label
                }
                type="button"
                aria-selected={tab === key}
                aria-controls={`${tabsId}-${key}-panel`}
                tabIndex={tab === key ? 0 : -1}
                onClick={() => setTab(key)}
                onKeyDown={(event) => changeTab(event, index)}
              >
                {label}
                {key === 'sources' && <span>{item.coverage.source_count}</span>}
              </button>
            ))}
          </div>
          <section
            role="tabpanel"
            id={`${tabsId}-${tab}-panel`}
            aria-labelledby={`${tabsId}-${tab}-tab`}
            tabIndex={0}
            className="page-stack analysis-tab-panel"
          >
            {tab === 'data' && <ESGData item={item} onSource={showSource} />}
            {tab === 'climate' && <ClimateAwareness item={item} onSource={showSource} />}
            {tab === 'news' && <NewsTimeline item={item} onSource={showSource} />}
            {tab === 'overview' && (
              <>
                <Panel
                  title="Look beyond the language score"
                  description="A positive report-language score can coexist with rising emissions."
                >
                  <p>
                    Review independent producer estimates, production trends and evidence for this
                    sector before drawing conclusions.
                  </p>
                  <button className="text-button" onClick={() => setTab('climate')}>
                    Explore climate & impact →
                  </button>
                </Panel>
                <CompanyProfile
                  profile={profile}
                  company={item.company}
                  hasSources={item.coverage.source_count > 0}
                  onRefresh={item.kind === 'company' ? refresh : null}
                  busy={actionBusy}
                  showNotice={false}
                />
                <ScoreReasons item={item} onSource={showSource} />
                <Panel title="ESG overview">
                  <p className="research-summary">{item.summary}</p>
                  <div className="dimension-grid">
                    {Object.entries(item.dimensions).map(([key, d]) => (
                      <div key={key}>
                        <div>
                          <span>{key === 'digital' ? 'Digital' : key}</span>
                          <strong>{d.score ?? '—'}</strong>
                        </div>
                        <p>{friendlyLabel(d.label)}</p>
                        <small>
                          {d.evidence_count} supporting passages · {friendlyLabel(d.status)}
                        </small>
                      </div>
                    ))}
                  </div>
                  {context.previous && (
                    <p className="small muted">
                      {context.method_changed ? (
                        'The scoring method changed; score differences are not compared.'
                      ) : (
                        <>
                          Score changes compare with{' '}
                          <a href={`#/analysis/${context.previous.id}`}>
                            {date(context.previous.created_at, true)}
                          </a>
                          .
                        </>
                      )}
                    </p>
                  )}
                  {item.changes && (
                    <p className="small muted">{friendlyLabel(item.changes.message)}</p>
                  )}
                  {item.report && (
                    <a className="text-button" href={`#/reports?report=${item.report.id}`}>
                      Read uploaded document
                      <ArrowRight size={15} />
                    </a>
                  )}
                </Panel>
                {item.kind === 'company' && (
                  <Panel
                    title="Sector context"
                    description={`As of ${date(item.created_at)}. Recent ${item.public ? 'public catalog' : 'workspace'} analyses using the same scoring method.`}
                  >
                    {Object.values(peerMetrics).some((value) => value.available) ? (
                      <div className="table-scroll">
                        <table>
                          <caption className="sr-only">Workspace sector comparison</caption>
                          <thead>
                            <tr>
                              <th>Indicator</th>
                              <th>Sector median</th>
                              <th>Position</th>
                              <th>Companies</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(peerMetrics)
                              .filter(([, value]) => value.available)
                              .map(([key, value]) => (
                                <tr key={key}>
                                  <th scope="row">{metricNames[key]}</th>
                                  <td>{value.median}</td>
                                  <td>Percentile {value.percentile}</td>
                                  <td>{value.sample_size}</td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="muted">
                        {!context.peers?.sector || context.peers.sector === 'Not classified'
                          ? 'A recorded sector is needed for peer comparisons.'
                          : item.public
                            ? `There are not enough comparable ${context.peers.sector} snapshots at this analysis date. Open the peer comparison to review available evidence.`
                            : `Analyse at least three ${context.peers.sector} companies with enough coverage, then refresh this analysis. Peer analyses must be from the preceding 90 days.`}
                      </p>
                    )}
                    <p className="small muted peer-footnote">
                      {item.public
                        ? 'This is a public catalog sample'
                        : 'This is a workspace sample'}
                      , not a market benchmark. A higher risk percentile means more matched risk
                      pressure.
                    </p>
                  </Panel>
                )}
                <details className="research-notes">
                  <summary>
                    Research notes and limitations{notes.length > 0 ? ` (${notes.length})` : ''}
                  </summary>
                  {notes.map((note) => (
                    <p className="small muted" key={note}>
                      {note}
                    </p>
                  ))}
                </details>
                <ScoreMethod analysis={item} />
              </>
            )}
            {tab === 'sources' && <EvidencePanel analysis={item} onSource={showSource} />}
            {tab === 'history' && (
              <Suspense fallback={<Loading>Loading dated history…</Loading>}>
                <HistoryChart rows={context.trend || []} mode={item.mode} />
              </Suspense>
            )}
            {tab === 'scenario' && (
              <Suspense fallback={<Loading>Preparing the scenario controls…</Loading>}>
                <ScenarioSandbox baseline={item.scores.momentum.score} />
              </Suspense>
            )}
          </section>
          {tabs
            .filter(([key]) => key !== tab)
            .map(([key]) => (
              <section
                key={key}
                role="tabpanel"
                id={`${tabsId}-${key}-panel`}
                aria-labelledby={`${tabsId}-${key}-tab`}
                hidden
              />
            ))}
        </div>
        <aside className="assistant-column" aria-label="Research assistant">
          <ResearchAssistant
            suggestedQuestion={suggestedQuestion}
            key={item.id}
            analysis={item}
            onSource={showSource}
          />
        </aside>
      </div>
      {source && (
        <SourceDrawer
          source={source}
          signals={item.signals.filter((signal) => signal.source_id === source.id)}
          close={closeSource}
        />
      )}
    </div>
  );
}
