import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from . import analysis, briefs, config, db, facts, news, profiles, public_research, research, sources

logger = logging.getLogger(__name__)


def enqueue(owner, company_id, mode='live'):
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute("SELECT * FROM jobs WHERE owner=? AND company_id=? AND mode=? AND status IN ('queued','running')", (owner, company_id, mode)).fetchone()
        if row:
            return dict(row)
        job_id = uuid.uuid4().hex
        con.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (job_id, owner, company_id, mode, 'queued', 'Waiting for collection', None, None, db.now(), db.now()))
    return job(owner, job_id)


def job(owner, job_id):
    with db.connect() as con:
        row = con.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job_id, owner)).fetchone()
    return dict(row) if row else None


def stage(job_id, label):
    with db.connect() as con:
        con.execute('UPDATE jobs SET stage=?,updated_at=? WHERE id=?', (label, db.now(), job_id))


def process_one():
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY CASE WHEN owner='public:curated' THEN 1 ELSE 0 END,created_at,rowid LIMIT 1").fetchone()
        if not row:
            return False
        row = dict(row)
        con.execute("UPDATE jobs SET status='running',stage='Collecting company evidence',updated_at=? WHERE id=?", (db.now(), row['id']))
    try:
        company = db.company(row['company_id'])
        if not company:
            raise ValueError('The company could not be found. Search again.')
        if row['mode'] == 'demo':
            evidence, warnings, collected = sources.demo_sources(company), [], None
            official = None
        else:
            collected = sources.collect_news(company)
            evidence, warnings = collected['sources'], collected['warnings']
            stage(row['id'], 'Reading official reports and company information')
            official = research.collect(company)
            evidence = list({source['id']: source for source in evidence + official['sources']}.values())
            warnings = [*warnings, *official['warnings']]
            row['owner'] = db.current_owner(row['owner'])
            # User-supplied company reports remain scoped to their owner's research.
            with db.connect() as con:
                report_rows = con.execute("SELECT payload FROM analyses WHERE owner=? AND company_id=? AND kind='report' ORDER BY created_at DESC LIMIT 30", (row['owner'], company['id'])).fetchall() if row['owner'] != public_research.OWNER else []
            report_sources = [source for report in report_rows for source in json.loads(report['payload'])['sources']]
            evidence = list({source['id']: source for source in evidence + report_sources}.values())
            if report_sources:
                warnings = [*warnings, 'Includes reports supplied in your workspace. Their claims and publication dates have not been independently verified.']
        stage(row['id'], 'Extracting page-verified facts and company context')
        extracted = facts.extract(official.get('documents', [])) if official else facts.extract([], use_ai=False)
        if official:
            # Private documents stay on this machine during unattended enrichment.
            private = [{'id': s['id'], 'title': s['title'], 'url': s['url'], 'publisher': s['publisher'], 'report_id': s['report_id'],
                        'pages': [{'page': s.get('page'), 'label': s.get('section'), 'text': s['excerpt']}]} for s in evidence if s.get('report_id')]
            extracted['items'].extend(facts.extract(private, use_ai=False)['items'])
        snapshot = profiles.collect(company) if official else None
        evidence = [news.tag(s) for s in evidence]
        stage(row['id'], 'Classifying evidence and calculating scores')
        row['owner'] = db.current_owner(row['owner'])
        previous = db.latest(row['owner'], company['id'], row['mode'])
        payload = analysis.build(company, evidence, mode=row['mode'], warnings=warnings)
        payload['changes'] = analysis.changes(previous, payload)
        payload['collection'] = {k: v for k, v in (collected or {}).items() if k != 'sources'}
        payload['research'] = official['profile'] if official else None
        payload['research_version'] = research.VERSION if official else None
        payload['facts'] = extracted
        payload['snapshot'] = {k: v for k, v in (snapshot or {}).items() if k != 'sources'} or None
        payload['knowledge_sources'] = list({s['id']: s for s in facts.evidence(extracted) + (snapshot or {}).get('sources', [])}.values())
        payload['controversies'] = news.timeline(evidence)
        payload['explanations'] = briefs.explanations(payload)
        stage(row['id'], 'Preparing the cited company brief')
        payload['brief'] = briefs.generate(payload, allow_ai=bool(official))
        payload['next_steps'] = {'peers': public_research.peers(company), 'question': f"What emissions targets does {company['name']} report?"}
        payload['public'] = row['owner'] == public_research.OWNER
        stage(row['id'], 'Saving the analysis snapshot')
        db.store_analysis(row['owner'], payload)
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            owner = db.resolve_owner(row['owner'], con)
            con.execute("UPDATE jobs SET status='complete',stage='Analysis ready',analysis_id=?,updated_at=? WHERE id=?", (payload['id'], db.now(), row['id']))
            if row['mode'] == 'live':
                con.execute('UPDATE watchlist SET last_refreshed=? WHERE owner=? AND company_id=?', (db.now(), owner, company['id']))
    except Exception as exc:
        logger.exception('Company analysis job failed: %s', row['id'])
        message = str(exc) if isinstance(exc, ValueError) else 'Analysis could not finish. Please retry.'
        with db.connect() as con:
            con.execute("UPDATE jobs SET status='failed',stage='Needs attention',error=?,updated_at=? WHERE id=?", (message, db.now(), row['id']))
    return True


def schedule():
    public_research.schedule()
    with db.connect() as con:
        # Guest sessions are deliberately excluded from unattended monitoring.
        rows = con.execute("SELECT w.* FROM watchlist w JOIN users u ON w.owner=u.id").fetchall()
    for row in rows:
        stamp = row['last_refreshed'] or row['created_at']
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
        if elapsed >= config.REFRESH_SECONDS:
            enqueue(row['owner'], row['company_id'])


async def run(stop):
    last_schedule = 0
    while not stop.is_set():
        try:
            if time.monotonic() - last_schedule >= 60:
                await asyncio.to_thread(schedule)
                last_schedule = time.monotonic()
            await asyncio.to_thread(process_one)
        except Exception:
            # A transient database or source failure must not stop monitoring.
            logger.exception('Background monitoring iteration failed')
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except asyncio.TimeoutError:
            pass
