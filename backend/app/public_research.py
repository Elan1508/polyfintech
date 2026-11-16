"""Shared public snapshots never contain uploaded reports or workspace records."""
import json
from datetime import datetime, timedelta, timezone

from . import config, db, facts, research, sources

OWNER = 'public:curated'


def latest(company_id, mode='live'):
    return db.latest(OWNER, company_id, mode) if mode == 'live' else None


def available(owner, company_id, mode='live'):
    return db.latest(owner, company_id, mode) or latest(company_id, mode)


def catalog_companies():
    return [c for key in research.CATALOG['companies'] if (c := db.company('directory:' + key))]


def seed():
    path = config.BACKEND / 'app/data/public_research_seed.json'
    if not path.is_file():
        return
    for item in json.loads(path.read_text(encoding='utf-8')).get('analyses', []):
        if not latest(item['company']['id']) and not any(s.get('report_id') for s in item['sources'] + item.get('knowledge_sources', [])):
            db.store_analysis(OWNER, item)


def schedule():
    from .worker import enqueue
    # 02:00 Singapore time, with a startup catch-up when yesterday's batch was missed.
    local = datetime.now(timezone(timedelta(hours=8)))
    cutoff = local.replace(hour=2, minute=0, second=0, microsecond=0)
    if local < cutoff:
        cutoff -= timedelta(days=1)
    for company in catalog_companies():
        if not research.entry_for(company):
            continue
        item = latest(company['id'])
        if not item or datetime.fromisoformat(item['created_at']) < cutoff or item.get('research_version') != research.VERSION or item.get('facts', {}).get('version') != facts.VERSION:
            enqueue(OWNER, company['id'])


def peers(company):
    from .awareness import group
    return [c for c in catalog_companies() if c['id'] != company['id'] and (c.get('ticker'), c.get('exchange')) != (company.get('ticker'), company.get('exchange')) and group(c) == group(company)
            and group(company) not in (None, 'Not classified', 'Other sectors') and research.entry_for(c)][:3]
