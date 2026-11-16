import asyncio
import json
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response as BinaryResponse
from pydantic import BaseModel, Field

from . import analysis, assistant, auth, awareness, briefs, config, db, facts, news, public_research, reports, research, sources, worker, workspace


@asynccontextmanager
async def lifespan(app):
    db.init()
    sources.seed_directory()
    public_research.seed()
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run(stop))
    yield
    stop.set()
    await task


app = FastAPI(title='ESG Pulse 360', version='2.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_credentials=True,
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'X-CSRF-Token'])


@app.middleware('http')
async def request_boundary(request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin and origin not in config.ALLOWED_ORIGINS:
        return JSONResponse({'detail': 'This request origin is not allowed.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default='', max_length=80)


class AnalysisRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    mode: Literal['live', 'demo'] = 'live'
    refresh: bool = False


class WatchRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    folder: str = Field(default='My watchlist', min_length=1, max_length=60)


class FolderRequest(BaseModel):
    folder: str = Field(min_length=1, max_length=60)


class SaveRequest(BaseModel):
    saved: bool


class CompareRequest(BaseModel):
    company_ids: list[str] = Field(min_length=2, max_length=5)
    mode: Literal['live', 'demo'] = 'live'


class Question(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=3, max_length=1200)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/api/session')
def get_session(request: Request, response: Response):
    try:
        current = auth.session(request)
    except HTTPException:
        current = auth.create_session(response, request)
    return {'user': current['user'], 'csrf': current['csrf'], 'ai': assistant.status(),
            'refresh_hours': config.REFRESH_SECONDS // 3600, 'scoring_version': config.SCORING_VERSION,
            'research_version': research.VERSION, 'news_version': sources.NEWS_VERSION}


@app.post('/api/auth/register')
def register(data: Credentials, request: Request, response: Response, current=Depends(auth.session)):
    auth.limit('register:' + (request.client.host if request.client else 'local'), 8, 3600)
    email = data.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Enter a valid email address.')
    user = {'id': uuid.uuid4().hex, 'email': email, 'name': data.name.strip() or email.split('@')[0]}
    digest = auth.hash_password(data.password)
    try:
        with db.connect() as con:
            con.execute('INSERT INTO users VALUES (?,?,?,?,?)', (user['id'], email, user['name'], digest, db.now()))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'An account with that email already exists. Try signing in.')
    session = auth.create_session(response, request, user, old=current)
    return {'user': user, 'csrf': session['csrf']}


@app.post('/api/auth/login')
def login(data: Credentials, request: Request, response: Response, current=Depends(auth.session)):
    address = request.client.host if request.client else 'local'
    auth.limit('login:' + address, 20, 900)
    auth.limit('login-email:' + data.email.strip().lower(), 10, 900)
    with db.connect() as con:
        row = con.execute('SELECT * FROM users WHERE email=?', (data.email.strip().lower(),)).fetchone()
    digest = row['password_hash'] if row else 'pbkdf2_sha256$600000$00000000000000000000000000000000$' + '00' * 32
    valid = auth.check_password(data.password, digest)
    if not row or not valid:
        raise HTTPException(401, 'Email or password is incorrect.')
    user = {k: row[k] for k in ('id', 'email', 'name')}
    session = auth.create_session(response, request, user, old=current)
    return {'user': user, 'csrf': session['csrf']}


@app.post('/api/auth/logout')
def logout(request: Request, response: Response, current=Depends(auth.session)):
    session = auth.create_session(response, request, old=current)
    return {'user': None, 'csrf': session['csrf']}


@app.get('/api/companies')
def search_companies(q: str = '', listed_only: bool = False, current=Depends(auth.session)):
    if len(q) > 100:
        raise HTTPException(422, 'Search using fewer than 100 characters.')
    auth.limit('search:' + current['owner'], 60, 60)
    result = sources.search(q.strip(), listed_only=listed_only)
    latest = workspace.latest_companies(current['owner'], [c['id'] for c in result['companies']])
    for company in result['companies']:
        if company['id'] not in latest:
            item = public_research.latest(company['id'])
            if item:
                latest[company['id']] = item
    result['companies'] = [{**awareness.company_meta(c), 'analysis': compact(latest[c['id']]) if c['id'] in latest else None}
                           for c in result['companies']]
    return result


@app.get('/api/companies/{company_id}')
def get_company(company_id: str, current=Depends(auth.session)):
    company = db.company(company_id)
    if not company:
        raise HTTPException(404, 'Company not found. Find it using company search.')
    return awareness.company_meta(company)


@app.get('/api/companies/{company_id}/research')
def get_company_research(company_id: str, current=Depends(auth.session)):
    company = db.company(company_id)
    if not company:
        raise HTTPException(404, 'Company not found.')
    auth.limit('profile:' + current['owner'], 60, 60)
    return research.profile(company)


@app.post('/api/analyses')
def create_analysis(data: AnalysisRequest, current=Depends(auth.session)):
    company = db.company(data.company_id)
    if not company:
        raise HTTPException(404, 'Choose a company from search results first.')
    if data.mode == 'demo' and not company.get('demo_key'):
        raise HTTPException(422, 'Demo evidence is available for starter examples only. Use live analysis.')
    previous = db.latest(current['owner'], data.company_id, data.mode)
    if not previous and not data.refresh and data.mode == 'live':
        with db.connect() as con:
            private_report = con.execute("SELECT 1 FROM analyses WHERE owner=? AND company_id=? AND kind='report' LIMIT 1", (current['owner'], data.company_id)).fetchone()
        shared = public_research.latest(data.company_id)
        if shared and not private_report and shared.get('research_version') == research.VERSION:
            return {'analysis_id': shared['id'], 'cached': True, 'public': True}
    if previous and not data.refresh:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(previous['created_at'])).total_seconds()
        with db.connect() as con:
            newer_report = con.execute("SELECT 1 FROM analyses WHERE owner=? AND company_id=? AND kind='report' AND created_at>? LIMIT 1", (current['owner'], data.company_id, previous['created_at'])).fetchone()
        current_sources = data.mode == 'demo' or (previous.get('research_version') == research.VERSION
                                                  and previous.get('collection', {}).get('version') == sources.NEWS_VERSION)
        if age < 3600 and current_sources and not (data.mode == 'live' and newer_report):
            return {'analysis_id': previous['id'], 'cached': True}
    auth.limit('analyse:' + current['owner'], 30, 3600)
    return {'job': worker.enqueue(current['owner'], data.company_id, data.mode)}


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str, current=Depends(auth.session)):
    job = worker.job(current['owner'], job_id)
    if not job:
        raise HTTPException(404, 'Job not found.')
    return job


@app.get('/api/analyses')
def list_analyses(saved: bool = False, current=Depends(auth.session)):
    with db.connect() as con:
        rows = con.execute('SELECT id FROM analyses WHERE owner=? AND (?=0 OR saved=1) ORDER BY created_at DESC,rowid DESC LIMIT 100',
                           (current['owner'], int(saved))).fetchall()
    return [compact(db.get_analysis(current['owner'], row['id'])) for row in rows]


@app.get('/api/library')
def library(view: Literal['all', 'saved'] = 'saved', kind: Literal['all', 'company', 'report'] = 'all',
            q: str = Query('', max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            current=Depends(auth.session)):
    pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    where = "owner=? AND (?='all' OR saved=1) AND (?='all' OR kind=?) AND json_extract(payload,'$.company.name') LIKE ? ESCAPE '\\'"
    params = (current['owner'], view, kind, kind, pattern)
    with db.connect() as con:
        total = con.execute('SELECT COUNT(*) FROM analyses WHERE ' + where, params).fetchone()[0]
        rows = con.execute('SELECT id FROM analyses WHERE ' + where + ' ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
    return {'items': [compact(db.get_analysis(current['owner'], row['id'])) for row in rows],
            'total': total, 'has_more': offset + len(rows) < total}


@app.get('/api/stats')
def stats(current=Depends(auth.session)):
    with db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS investigations, COALESCE(SUM(saved),0) AS saved, COALESCE(SUM(mode='live'),0) AS live FROM analyses WHERE owner=?", (current['owner'],)).fetchone()
    return dict(row)


def compact(item, include_facts=False):
    if item.get('facts', {}).get('version') != facts.VERSION:
        item = {**item, 'facts': facts.recheck(item.get('facts', {}))}
    return {k: item[k] for k in ('id', 'company', 'kind', 'mode', 'created_at', 'scoring_version', 'saved', 'scores', 'dimensions', 'coverage', 'classification')} | {
        'source_count': item['coverage']['source_count'], 'risk_flag_count': analysis.risk_flag_count(item),
        'company': awareness.company_meta(item['company']),
        'facts': item.get('facts', {}) if include_facts else {'count': len(item.get('facts', {}).get('items', []))},
        'brief': {**item['brief'], 'items': item['brief']['items'][:1]} if item.get('brief') else None,
        'public': item.get('public', False),
        'headline': next(({k: s.get(k) for k in ('id', 'title', 'publisher', 'published_at', 'url')} for s in item['sources'] if s.get('kind') == 'news'), None)}


@app.get('/api/discover')
def discover(current=Depends(auth.session)):
    items = [public_research.latest(c['id']) for c in public_research.catalog_companies()]
    priority = {'U96': 0, 'PTT': 1, 'F34': 2, 'C6L': 3, 'D05': 4, 'XOM': 5}
    ready = sorted([a for a in items if a], key=lambda a: (priority.get(a['company']['ticker'], 9), a['company']['name']))
    return {'items': [compact(a) for a in ready], 'total': len(items), 'ready': len(ready),
            'schedule': 'Public research refreshes at 02:00 Singapore time while the server is running, with startup catch-up.',
            'scope': research.CATALOG.get('scope', 'Singapore listed companies and selected regional examples')}


@app.get('/api/analyses/{analysis_id}')
def get_analysis(analysis_id: str, current=Depends(auth.session)):
    item = db.get_analysis(current['owner'], analysis_id) or db.get_analysis(public_research.OWNER, analysis_id)
    if not item:
        raise HTTPException(404, 'Investigation not found in your workspace.')
    if item['kind'] == 'report' and item.get('facts', {}).get('version') != facts.VERSION:
        # Existing uploads already retain full pages. Enrich them locally without
        # requiring another upload or sending private material to an AI provider.
        report_id = item.get('report_id') or item.get('report', {}).get('id')
        with db.connect() as con:
            report = con.execute('SELECT filename,pages FROM reports WHERE id=? AND owner=?', (report_id, current['owner'])).fetchone()
        if report:
            document = {'id': report_id, 'title': report['filename'], 'publisher': 'User-uploaded report',
                        'url': f'/api/reports/{report_id}/file', 'report_id': report_id, 'pages': json.loads(report['pages'])}
            item['facts'] = facts.extract([document], use_ai=False)
            item['knowledge_sources'] = facts.evidence(item['facts'])
            with db.connect() as con:
                con.execute('UPDATE analyses SET payload=? WHERE id=? AND owner=?', (json.dumps(item), analysis_id, current['owner']))
    if item.get('facts', {}).get('version') != facts.VERSION:
        item = {**item, 'facts': facts.recheck(item.get('facts', {}))}
        item['knowledge_sources'] = [s for s in item.get('knowledge_sources', []) if not s['id'].startswith('fact_')] + facts.evidence(item['facts'])
        item['brief'] = briefs.generate(item, allow_ai=False)
    context = workspace.comparison_context(public_research.OWNER if item.get('public') else current['owner'], item)
    if item.get('public'):
        context['peers']['description'] = 'Shared public catalog snapshots only; not a market benchmark. At least three comparable companies are required.'
    return {**item, 'company': awareness.company_meta(item['company']),
            'sources': [news.tag(s) for s in item['sources']],
            'explanations': briefs.explanations(item), 'risk_flag_count': analysis.risk_flag_count(item), 'context': context}


@app.patch('/api/analyses/{analysis_id}')
def save_analysis(analysis_id: str, data: SaveRequest, current=Depends(auth.session)):
    item = get_analysis(analysis_id, current)
    if item.get('public'):
        item = {**item, 'id': uuid.uuid4().hex, 'public': False, 'saved': data.saved}
        item.pop('context', None)
        db.store_analysis(current['owner'], item)
        analysis_id = item['id']
    with db.connect() as con:
        con.execute('UPDATE analyses SET saved=? WHERE id=? AND owner=?', (int(data.saved), analysis_id, current['owner']))
    return {'saved': data.saved, 'analysis_id': analysis_id}


@app.get('/api/companies/{company_id}/history')
def history(company_id: str, mode: Literal['live', 'demo'] = 'live', current=Depends(auth.session)):
    with db.connect() as con:
        rows = con.execute("SELECT id FROM analyses WHERE owner=? AND company_id=? AND mode=? AND kind='company' ORDER BY created_at DESC,rowid DESC LIMIT 50", (current['owner'], company_id, mode)).fetchall()
    return [compact(db.get_analysis(current['owner'], row['id'])) for row in reversed(rows)]


@app.get('/api/watchlist')
def get_watchlist(current=Depends(auth.session)):
    with db.connect() as con:
        rows = con.execute('SELECT * FROM watchlist WHERE owner=? ORDER BY created_at DESC', (current['owner'],)).fetchall()
    result = []
    for row in rows:
        latest = public_research.available(current['owner'], row['company_id'])
        previous = None
        if row['last_seen']:
            with db.connect() as con:
                old = con.execute("SELECT id,owner FROM analyses WHERE owner IN (?,?) AND company_id=? AND mode='live' AND kind='company' AND created_at<=? ORDER BY created_at DESC,rowid DESC LIMIT 1",
                                  (current['owner'], public_research.OWNER, row['company_id'], row['last_seen'])).fetchone()
            previous = db.get_analysis(old['owner'], old['id']) if old else None
        delta = analysis.changes(previous, latest) if latest else None
        meaningful = bool(delta and (previous is None or delta['new_source_count'] or delta['method_changed'] or
                                     any(value != 0 for value in delta['score_changes'].values()) or
                                     previous['coverage']['status'] != latest['coverage']['status']))
        result.append({**dict(row), 'company': db.company(row['company_id']), 'analysis': compact(latest) if latest else None,
                       'trend': workspace.trend_rows(current['owner'], row['company_id']) or workspace.trend_rows(public_research.OWNER, row['company_id']),
                       'changes': delta, 'update': news.updates(previous, latest, row['last_seen']) if latest else None,
                       'unread': bool(meaningful and latest and (not row['last_seen'] or latest['created_at'] > row['last_seen']))})
    return result


@app.post('/api/watchlist')
def add_watch(data: WatchRequest, current=Depends(auth.session)):
    if not db.company(data.company_id):
        raise HTTPException(404, 'Company not found.')
    with db.connect() as con:
        con.execute('INSERT INTO watchlist(owner,company_id,folder,created_at) VALUES (?,?,?,?) ON CONFLICT(owner,company_id) DO UPDATE SET folder=excluded.folder',
                    (current['owner'], data.company_id, data.folder.strip() or 'My watchlist', db.now()))
    return {'added': True}


@app.patch('/api/watchlist/{company_id}')
def update_watch(company_id: str, data: FolderRequest, current=Depends(auth.session)):
    with db.connect() as con:
        result = con.execute('UPDATE watchlist SET folder=? WHERE owner=? AND company_id=?', (data.folder.strip() or 'My watchlist', current['owner'], company_id))
        if not result.rowcount:
            raise HTTPException(404, 'Tracked company not found.')
    return {'updated': True}


@app.delete('/api/watchlist/{company_id}')
def remove_watch(company_id: str, current=Depends(auth.session)):
    with db.connect() as con:
        con.execute('DELETE FROM watchlist WHERE owner=? AND company_id=?', (current['owner'], company_id))
    return {'removed': True}


@app.post('/api/watchlist/{company_id}/seen')
def mark_seen(company_id: str, current=Depends(auth.session)):
    with db.connect() as con:
        con.execute('UPDATE watchlist SET last_seen=? WHERE owner=? AND company_id=?', (db.now(), current['owner'], company_id))
    return {'seen': True}


@app.post('/api/watchlist/refresh')
def refresh_watchlist(current=Depends(auth.session)):
    auth.limit('refresh:' + current['owner'], 6, 3600)
    with db.connect() as con:
        rows = con.execute('SELECT company_id FROM watchlist WHERE owner=?', (current['owner'],)).fetchall()
    return {'jobs': [worker.enqueue(current['owner'], row['company_id']) for row in rows]}


@app.post('/api/compare')
def compare(data: CompareRequest, current=Depends(auth.session)):
    ids = list(dict.fromkeys(data.company_ids))
    if len(ids) < 2:
        raise HTTPException(422, 'Choose at least two different companies.')
    rows = [{'company': db.company(company_id), 'analysis': public_research.available(current['owner'], company_id, data.mode)} for company_id in ids]
    if any(not row['company'] for row in rows):
        raise HTTPException(404, 'A selected company no longer exists.')
    for row in rows:
        row['analysis'] = compact(row['analysis'], include_facts=True) if row['analysis'] else None
        row['company'] = awareness.company_meta(row['company'])
        row['awareness'] = awareness.view(current['owner'], row['company'], row['analysis'] or {'mode': data.mode})
    groups = {row['company']['sector_group'] for row in rows}
    same_sector = len(groups) == 1 and 'Not classified' not in groups
    metric_rows = facts.key_comparison(rows)
    if not same_sector:
        for metric in metric_rows:
            metric['comparable'] = False
            for cell in metric.get('cells', []):
                if cell:
                    cell.pop('rank', None)
    return {'rows': rows, 'metrics': metric_rows, 'emissions_metrics': awareness.comparison(rows, same_sector), 'same_sector': same_sector, 'mode': data.mode, 'scoring_version': config.SCORING_VERSION,
            'notice': 'Uses your latest analysis, or shared public research when you have none. Metric rows match reporting year, unit and available boundaries. Highest/lowest describes reported values, not overall ESG quality.'}


@app.get('/api/emissions')
def emissions_workspace(current=Depends(auth.session)):
    return awareness.workspace(current['owner'])


@app.post('/api/emissions/import')
async def import_emissions(file: UploadFile = File(...), version: str = Form('', max_length=100), current=Depends(auth.session)):
    auth.limit('carbon-import:' + current['owner'], 10, 3600)
    content = await file.read(awareness.MAX_BYTES + 1)
    filename = Path((file.filename or 'carbon-majors.csv').replace('\\', '/')).name[:180]
    if not filename.lower().endswith('.csv'):
        raise HTTPException(422, 'Choose an official Carbon Majors CSV file.')
    try:
        return await asyncio.to_thread(awareness.import_csv, current['owner'], content, filename, version)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class EmissionsMapping(BaseModel):
    company_id: str = Field(min_length=1, max_length=100)
    entity: str = Field(min_length=1, max_length=180)


@app.post('/api/emissions/mapping')
def map_emissions(data: EmissionsMapping, current=Depends(auth.session)):
    try:
        awareness.set_mapping(current['owner'], data.company_id, data.entity)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return awareness.workspace(current['owner'])


@app.get('/api/companies/{company_id}/awareness')
def company_awareness(company_id: str, baseline: int | None = Query(None, ge=1750, le=2100), analysis_id: str = '', current=Depends(auth.session)):
    company = db.company(company_id)
    if not company:
        raise HTTPException(404, 'Company not found.')
    item = get_analysis(analysis_id, current) if analysis_id else public_research.available(current['owner'], company_id)
    if item and item['company']['id'] != company_id:
        raise HTTPException(422, 'The analysis belongs to a different company.')
    return awareness.view(current['owner'], company, item, baseline)


@app.post('/api/reports')
async def upload_report(file: UploadFile = File(...), company_id: str = Form(''), title: str = Form(''), current=Depends(auth.session)):
    auth.limit('upload:' + current['owner'], 15, 3600)
    content = await file.read(config.MAX_UPLOAD + 1)
    filename = Path((file.filename or 'report.txt').replace('\\', '/')).name[:180]
    company = db.company(company_id) if company_id else None
    if company_id and not company:
        raise HTTPException(404, 'Select a valid company for this report.')
    if not company:
        company = {'id': 'report:' + uuid.uuid4().hex, 'name': title.strip()[:120] or Path(filename).stem,
                   'ticker': '', 'exchange': 'Uploaded document', 'country': 'User supplied', 'sector': 'Not classified',
                   'aliases': [], 'identity_source': 'User-supplied document', 'identity_url': ''}
    report_id, evidence, pages, warnings = await asyncio.to_thread(reports.store, current['owner'], filename, content, company)
    payload = analysis.build(company, evidence, mode='report', warnings=warnings, kind='report', report_id=report_id)
    payload['report'] = {'id': report_id, 'filename': filename, 'page_count': len(pages),
                         'character_count': sum(len(p['text']) for p in pages)}
    payload['facts'] = facts.extract([{'id': report_id, 'title': filename, 'publisher': 'User-uploaded report', 'url': f'/api/reports/{report_id}/file', 'report_id': report_id, 'pages': pages}], use_ai=False)
    payload['knowledge_sources'] = facts.evidence(payload['facts'])
    payload['explanations'] = briefs.explanations(payload)
    db.store_analysis(current['owner'], payload)
    return {'analysis_id': payload['id'], 'report': payload['report']}


@app.get('/api/reports/{report_id}')
def get_report(report_id: str, current=Depends(auth.session)):
    with db.connect() as con:
        row = con.execute('SELECT * FROM reports WHERE id=? AND owner=?', (report_id, current['owner'])).fetchone()
    if not row:
        raise HTTPException(404, 'Document not found in your workspace.')
    return {'id': row['id'], 'filename': row['filename'], 'media_type': row['media_type'], 'pages': json.loads(row['pages'])}


@app.get('/api/reports/{report_id}/file')
def report_file(report_id: str, current=Depends(auth.session)):
    with db.connect() as con:
        row = con.execute('SELECT * FROM reports WHERE id=? AND owner=?', (report_id, current['owner'])).fetchone()
    if not row or not Path(row['path']).is_file():
        raise HTTPException(404, 'Document not found in your workspace.')
    return FileResponse(row['path'], media_type=row['media_type'], filename=row['filename'], content_disposition_type='inline')


@app.post('/api/assistant')
def ask(data: Question, current=Depends(auth.session)):
    auth.limit('assistant:' + current['owner'], 25, 3600)
    item = get_analysis(data.analysis_id, current)
    return assistant.answer(item, data.question)


@app.get('/api/analyses/{analysis_id}/brief.pdf')
def download_brief(analysis_id: str, current=Depends(auth.session)):
    from .company_pdf import render
    item = get_analysis(analysis_id, current)
    content = render({**item, 'awareness': awareness.view(current['owner'], item['company'], item)})
    filename = re.sub(r'[^a-zA-Z0-9_-]', '-', item['company']['name'])[:70] + '-brief.pdf'
    return BinaryResponse(content, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
