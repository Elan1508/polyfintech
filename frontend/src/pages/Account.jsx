import { useState } from 'react';
import { ArrowRight, Check, LockKeyhole, ShieldCheck, UserRound } from 'lucide-react';
import { api, setCsrf } from '../api';
import { usePulse } from '../context';
import { Badge, ErrorNotice, Notice, PageHeading, Panel } from '../components/ui/Primitives';

export default function Account() {
  const { session, setSession, refreshWorkspace, navigate, notify, logout } = usePulse();
  const [register, setRegister] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    const data = new FormData(e.currentTarget);
    try {
      const result = await api(`/auth/${register ? 'register' : 'login'}`, {
        method: 'POST',
        body: JSON.stringify(Object.fromEntries(data)),
      });
      setCsrf(result.csrf);
      setSession((s) => ({ ...s, ...result }));
      await refreshWorkspace();
      notify(
        register
          ? 'Account created. Your guest research has been moved into your account.'
          : 'Welcome back. Your research is ready.',
      );
      navigate('/dashboard');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-stack">
      <PageHeading title="Account">
        {session.user
          ? 'Your saved research, documents and watchlists are linked to your account.'
          : 'Create an account to keep your research together and follow company updates.'}
      </PageHeading>
      <div className="account-grid">
        <Panel>
          {session.user ? (
            <div className="account-profile">
              <div className="account-avatar">
                <UserRound size={35} />
              </div>
              <h2>{session.user.name}</h2>
              <p className="muted">{session.user.email}</p>
              <Badge tone="green">
                <Check size={13} />
                Signed in
              </Badge>
              <p>
                Your research is saved to this app. Sign in to the same workspace to pick up where
                you left off.
              </p>
              <button className="button secondary" onClick={logout}>
                Sign out
              </button>
            </div>
          ) : (
            <>
              <div className="segmented">
                <button
                  className={register ? 'active' : ''}
                  onClick={() => {
                    setRegister(true);
                    setError('');
                  }}
                >
                  Create account
                </button>
                <button
                  className={!register ? 'active' : ''}
                  onClick={() => {
                    setRegister(false);
                    setError('');
                  }}
                >
                  Sign in
                </button>
              </div>
              <form onSubmit={submit} className="account-form">
                {register && (
                  <label className="field-label">
                    Your name
                    <input
                      name="name"
                      autoComplete="name"
                      maxLength={80}
                      required
                      placeholder="How should we address you?"
                    />
                  </label>
                )}
                <label className="field-label">
                  Email address
                  <input
                    name="email"
                    type="email"
                    autoComplete="email"
                    maxLength={254}
                    required
                    placeholder="you@example.com"
                  />
                </label>
                <label className="field-label">
                  Password
                  <input
                    name="password"
                    type="password"
                    autoComplete={register ? 'new-password' : 'current-password'}
                    minLength={12}
                    maxLength={128}
                    required
                    placeholder="At least 12 characters"
                  />
                </label>
                <ErrorNotice error={error} />
                <button className="button primary full-width" disabled={busy}>
                  {busy ? 'Please wait…' : register ? 'Create my workspace' : 'Sign in'}
                  <ArrowRight size={17} />
                </button>
                <a className="text-button" href="#/dashboard">
                  Continue in guest workspace
                  <ArrowRight size={15} />
                </a>
              </form>
            </>
          )}
        </Panel>
        <div className="page-stack">
          <Panel title="Your research, in one place">
            <div className="coverage-item">
              <ShieldCheck size={22} />
              <div>
                <h3>Keep the research you’ve started</h3>
                <p>
                  Your current company analyses, documents and watchlists move with you when you
                  create an account or sign in.
                </p>
              </div>
            </div>
            <div className="coverage-item">
              <LockKeyhole size={22} />
              <div>
                <h3>Your own research space</h3>
                <p>
                  Your account keeps your reports, watchlists and saved research together, with
                  access limited to you.
                </p>
              </div>
            </div>
          </Panel>
          <Notice>
            Accounts are local to this running application. Email verification and password recovery
            are not available in this version.
          </Notice>
        </div>
      </div>
    </div>
  );
}
