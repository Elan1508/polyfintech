import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


@contextmanager
def connect():
    config.RUNTIME.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with connect() as con:
        con.execute('PRAGMA journal_mode = WAL')
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
          name TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, user_id TEXT REFERENCES users(id),
          csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS owner_links (
          old_owner TEXT PRIMARY KEY, new_owner TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companies (
          id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cache (
          key TEXT PRIMARY KEY, payload TEXT NOT NULL, expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS analyses (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, company_id TEXT NOT NULL,
          kind TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL,
          saved INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS analysis_owner_company ON analyses(owner, company_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, filename TEXT NOT NULL,
          media_type TEXT NOT NULL, path TEXT NOT NULL, pages TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS watchlist (
          owner TEXT NOT NULL, company_id TEXT NOT NULL REFERENCES companies(id),
          folder TEXT NOT NULL DEFAULT 'My watchlist', created_at TEXT NOT NULL,
          last_refreshed TEXT, last_seen TEXT,
          PRIMARY KEY(owner, company_id));
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, company_id TEXT NOT NULL,
          mode TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
          error TEXT, analysis_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS job_status ON jobs(status, created_at);
        CREATE TABLE IF NOT EXISTS rate_limits (
          key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL);
        ''')
        con.execute("UPDATE jobs SET status='queued', stage='Waiting to resume' WHERE status='running'")
        from . import awareness
        awareness.init(con)


def put_company(company):
    with connect() as con:
        con.execute('INSERT INTO companies VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at',
                    (company['id'], json.dumps(company), now()))
    return company


def company(company_id):
    with connect() as con:
        row = con.execute('SELECT payload FROM companies WHERE id=?', (company_id,)).fetchone()
    return json.loads(row['payload']) if row else None


def companies():
    with connect() as con:
        rows = con.execute('SELECT payload FROM companies ORDER BY updated_at DESC').fetchall()
    return [json.loads(row['payload']) for row in rows]


def store_analysis(owner, payload):
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        owner = resolve_owner(owner, con)
        con.execute('INSERT INTO analyses(id,owner,company_id,kind,mode,created_at,payload) VALUES (?,?,?,?,?,?,?)',
                    (payload['id'], owner, payload['company']['id'], payload['kind'], payload['mode'], payload['created_at'], json.dumps(payload)))
    return payload


def get_analysis(owner, analysis_id):
    with connect() as con:
        row = con.execute('SELECT payload,saved FROM analyses WHERE id=? AND owner=?', (analysis_id, owner)).fetchone()
    return {**json.loads(row['payload']), 'saved': bool(row['saved'])} if row else None


def latest(owner, company_id, mode='live'):
    with connect() as con:
        row = con.execute("SELECT id FROM analyses WHERE owner=? AND company_id=? AND kind='company' AND mode=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                          (owner, company_id, mode)).fetchone()
    return get_analysis(owner, row['id']) if row else None


def migrate_guest(old_owner, new_owner, con):
    if not old_owner.startswith('guest:') or old_owner == new_owner:
        return
    con.execute('INSERT INTO owner_links VALUES (?,?) ON CONFLICT(old_owner) DO UPDATE SET new_owner=excluded.new_owner', (old_owner, new_owner))
    for table in ('analyses', 'reports', 'jobs'):
        con.execute(f'UPDATE {table} SET owner=? WHERE owner=?', (new_owner, old_owner))
    # Keep existing account copies when an identical guest import already exists.
    con.execute('DELETE FROM carbon_imports WHERE owner=? AND digest IN (SELECT digest FROM carbon_imports WHERE owner=?)', (old_owner, new_owner))
    con.execute('UPDATE carbon_imports SET owner=? WHERE owner=?', (new_owner, old_owner))
    con.execute('INSERT OR IGNORE INTO carbon_mappings SELECT ?,company_id,entity FROM carbon_mappings WHERE owner=?', (new_owner, old_owner))
    con.execute('DELETE FROM carbon_mappings WHERE owner=?', (old_owner,))
    con.execute('INSERT OR IGNORE INTO watchlist SELECT ?,company_id,folder,created_at,last_refreshed,last_seen FROM watchlist WHERE owner=?', (new_owner, old_owner))
    con.execute('DELETE FROM watchlist WHERE owner=?', (old_owner,))


def resolve_owner(owner, con):
    row = con.execute('SELECT new_owner FROM owner_links WHERE old_owner=?', (owner,)).fetchone()
    return row['new_owner'] if row else owner


def current_owner(owner):
    with connect() as con:
        return resolve_owner(owner, con)
