import { useEffect, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Bookmark,
  ChevronRight,
  Files,
  Globe2,
  LayoutDashboard,
  Leaf,
  LogOut,
  Menu,
  Search,
  Star,
  UserRound,
  X,
} from 'lucide-react';
import { usePulse } from '../../context';

const links = [
  ['Dashboard', '/dashboard', LayoutDashboard],
  ['Company explorer', '/explore', Search],
  ['Watchlist', '/watchlist', Star],
  ['Compare', '/compare', Files],
  ['Emissions data', '/emissions', Leaf],
  ['Report lab', '/reports', Globe2],
  ['Saved research', '/saved', Bookmark],
];

export default function Shell({ route, children }) {
  const { session, logout, watchlist } = usePulse();
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 700px)').matches);
  const sidebar = useRef(null);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 700px)');
    const changed = () => {
      setMobile(media.matches);
      if (!media.matches) setOpen(false);
    };
    media.addEventListener('change', changed);
    return () => media.removeEventListener('change', changed);
  }, []);
  useEffect(() => {
    setOpen(false);
    document.getElementById('main-content')?.focus({ preventScroll: true });
  }, [route]);
  useEffect(() => {
    if (!open || !mobile) return;
    const previous = document.activeElement;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusable = () => [...sidebar.current.querySelectorAll('a[href],button:not([disabled])')];
    focusable()[0]?.focus();
    const escape = (e) => {
      if (e.key === 'Escape') setOpen(false);
      if (e.key === 'Tab') {
        const items = focusable();
        if (e.shiftKey && document.activeElement === items[0]) {
          e.preventDefault();
          items.at(-1)?.focus();
        } else if (!e.shiftKey && document.activeElement === items.at(-1)) {
          e.preventDefault();
          items[0]?.focus();
        }
      }
    };
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('keydown', escape);
      document.body.style.overflow = oldOverflow;
      previous?.focus();
    };
  }, [open, mobile]);
  return (
    <div className="app-shell">
      <a
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById('main-content')?.focus();
        }}
        className="skip-link"
      >
        Skip to content
      </a>
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="Dismiss navigation overlay"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        ref={sidebar}
        inert={mobile && !open ? '' : undefined}
        aria-hidden={mobile && !open ? true : undefined}
        className={`sidebar ${open ? 'is-open' : ''}`}
      >
        <a className="brand" href="#/dashboard">
          <div className="brand-mark">
            <Leaf size={23} />
          </div>
          <div>
            ESG Pulse<span>360</span>
          </div>
        </a>
        <button
          className="icon-button mobile-close"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        >
          <X size={20} />
        </button>
        <p className="nav-caption">RESEARCH</p>
        <nav id="mobile-nav" aria-label="Main navigation">
          {links.map(([label, path, Icon]) => (
            <a
              key={path}
              href={`#${path}`}
              aria-current={route === path ? 'page' : undefined}
              className={route === path ? 'active' : ''}
            >
              <Icon size={18} />
              <span>{label}</span>
              {path === '/watchlist' && watchlist.length > 0 && <small>{watchlist.length}</small>}
            </a>
          ))}
        </nav>
        <div className="sidebar-account">
          <a href="#/account">
            <div className="user-avatar">
              <UserRound size={17} />
            </div>
            <div>
              <strong>{session.user?.name || 'Guest workspace'}</strong>
              <small>
                {session.user ? 'Personal account' : 'Create an account to keep access'}
              </small>
            </div>
            <ChevronRight size={15} />
          </a>
          {session.user && (
            <button className="text-button" onClick={logout}>
              <LogOut size={14} />
              Sign out
            </button>
          )}
        </div>
      </aside>
      <div className="main-shell" inert={mobile && open ? '' : undefined}>
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button menu-button"
              aria-expanded={open}
              aria-controls="mobile-nav"
              aria-label="Open navigation"
              onClick={() => setOpen(true)}
            >
              <Menu size={22} />
            </button>
            <span className="muted">Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {links.find(([, path]) => path === route)?.[0] ||
                (route.startsWith('/analysis') || route.startsWith('/investigate')
                  ? 'Company analysis'
                  : 'Account')}
            </strong>
          </div>
          <div className="topbar-right">
            <span className={`connection ${session.ai.available ? 'connected' : ''}`}>
              <i />
              {session.ai.available ? 'AI research assistant' : 'Search company sources'}
            </span>
            <a href="#/explore" className="topbar-search" aria-label="Find a company">
              <Search size={17} />
              <span>Find a company</span>
              <ArrowUpRight size={14} />
            </a>
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="main-content">
          {children}
        </main>
        <footer className="footer">
          <span>ESG Pulse 360 · Research workspace</span>
          <span>ESG research · Method {session.scoring_version}</span>
        </footer>
      </div>
    </div>
  );
}
