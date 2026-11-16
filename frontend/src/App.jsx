import { Component, Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, X } from 'lucide-react';
import { api, setCsrf } from './api';
import { PulseContext } from './context';
import Shell from './components/layout/Shell';
import { ErrorNotice, Loading } from './components/ui/Primitives';

const Home = lazy(() => import('./pages/Home'));
const Explorer = lazy(() => import('./pages/Explorer'));
const Investigation = lazy(() => import('./pages/Investigation'));
const Compare = lazy(() => import('./pages/Compare'));
const Watchlist = lazy(() => import('./pages/Watchlist'));
const ReportLab = lazy(() => import('./pages/ReportLab'));
const Saved = lazy(() => import('./pages/Saved'));
const Account = lazy(() => import('./pages/Account'));
const Emissions = lazy(() => import('./pages/Emissions'));

class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="startup">
        <h1>This page needs a fresh start.</h1>
        <p>Your saved research is still in the database.</p>
        <button className="button primary" onClick={() => window.location.reload()}>
          Reload workspace
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}

function WorkspaceApp() {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/dashboard');
  const [session, setSession] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [investigations, setInvestigations] = useState([]);
  const [stats, setStats] = useState({ saved: 0, live: 0, investigations: 0 });
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);
  const toastTimer = useRef();
  const refreshRequest = useRef(0);
  const notify = useCallback((message, tone = 'success') => {
    clearTimeout(toastTimer.current);
    setToast({ message, tone });
    toastTimer.current = setTimeout(() => setToast(null), 6500);
  }, []);
  const navigate = useCallback((path) => {
    window.location.hash = path;
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);
  const refreshWorkspace = useCallback(async () => {
    const request = ++refreshRequest.current;
    const [watch, analyses, totals] = await Promise.all([
      api('/watchlist'),
      api('/analyses'),
      api('/stats'),
    ]);
    if (request === refreshRequest.current) {
      setWatchlist(watch);
      setInvestigations(analyses);
      setStats(totals);
    }
  }, []);
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.slice(1) || '/dashboard');
    window.addEventListener('hashchange', onHash);
    if (!window.location.hash || window.location.hash === '#/') window.location.hash = '/dashboard';
    return () => {
      window.removeEventListener('hashchange', onHash);
      clearTimeout(toastTimer.current);
    };
  }, []);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await api('/session');
        if (!active) return;
        setCsrf(result.csrf);
        setSession(result);
        await refreshWorkspace();
      } catch (err) {
        if (active) setError(err.message);
      }
    })();
    return () => {
      active = false;
    };
  }, [refreshWorkspace]);
  useEffect(() => {
    if (session) refreshWorkspace().catch((err) => notify(err.message, 'error'));
    document.title = 'ESG Pulse 360 · Research workspace';
  }, [route, refreshWorkspace, Boolean(session), notify]);
  const logout = useCallback(async () => {
    try {
      const result = await api('/auth/logout', { method: 'POST' });
      setCsrf(result.csrf);
      setSession((s) => ({ ...s, ...result }));
      await refreshWorkspace();
      navigate('/dashboard');
      notify('Signed out. You are now in a new guest workspace.');
    } catch (err) {
      notify(err.message, 'error');
    }
  }, [refreshWorkspace, navigate, notify]);
  if (!session)
    return (
      <div className="startup">
        <div className="brand startup-brand">
          ESG Pulse<span>360</span>
        </div>
        {error ? (
          <ErrorNotice error={error} onRetry={() => window.location.reload()} />
        ) : (
          <Loading>Opening your research workspace…</Loading>
        )}
      </div>
    );
  const url = new URL(route, 'http://pulse.local');
  const path = url.pathname;
  let page;
  if (path === '/dashboard' || path === '/') page = <Home />;
  else if (path === '/explore') page = <Explorer />;
  else if (path.startsWith('/investigate/'))
    page = (
      <Investigation
        key={route}
        companyId={decodeURIComponent(path.slice('/investigate/'.length))}
        mode={url.searchParams.get('mode') === 'demo' ? 'demo' : 'live'}
      />
    );
  else if (path.startsWith('/analysis/'))
    page = (
      <Investigation key={route} analysisId={decodeURIComponent(path.slice('/analysis/'.length))} />
    );
  else if (path === '/compare') page = <Compare key={route} />;
  else if (path === '/watchlist') page = <Watchlist />;
  else if (path === '/reports')
    page = (
      <ReportLab
        reportId={url.searchParams.get('report')}
        companyId={url.searchParams.get('company')}
      />
    );
  else if (path === '/saved') page = <Saved />;
  else if (path === '/account') page = <Account />;
  else if (path === '/emissions') page = <Emissions />;
  else
    page = (
      <div className="empty">
        <h1>Page not found</h1>
        <a className="button primary" href="#/dashboard">
          Return to your dashboard
        </a>
      </div>
    );
  const context = {
    session,
    setSession,
    watchlist,
    investigations,
    stats,
    refreshWorkspace,
    notify,
    navigate,
    logout,
  };
  return (
    <PulseContext.Provider value={context}>
      <Shell route={path}>
        <ErrorNotice error={error} />
        <Suspense fallback={<Loading variant="page">Opening the page…</Loading>}>{page}</Suspense>
      </Shell>
      {toast && (
        <div role={toast.tone === 'error' ? 'alert' : 'status'} className={`toast ${toast.tone}`}>
          {toast.tone === 'error' ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
          <span>{toast.message}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={17} />
          </button>
        </div>
      )}
    </PulseContext.Provider>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <WorkspaceApp />
    </ErrorBoundary>
  );
}
