"""Private, dated comparison context derived from a researcher's actual analyses."""
import json
from datetime import datetime, timedelta
from statistics import median

from . import analysis, db


def latest_companies(owner, company_ids, mode='live'):
    result = {}
    ids = list(dict.fromkeys(company_ids))
    for start in range(0, len(ids), 400):
        batch = ids[start:start + 400]
        with db.connect() as con:
            rows = con.execute(f"""WITH ranked AS (
                SELECT payload, saved, company_id, ROW_NUMBER() OVER (
                    PARTITION BY company_id ORDER BY created_at DESC, rowid DESC) AS position
                FROM analyses WHERE owner=? AND kind='company' AND mode=?
                AND company_id IN ({','.join('?' for _ in batch)}))
                SELECT * FROM ranked WHERE position=1""", (owner, mode, *batch)).fetchall()
        for row in rows:
            result[row['company_id']] = {**json.loads(row['payload']), 'saved': bool(row['saved'])}
    return result


def trend_rows(owner, company_id, mode='live', limit=12, as_of=None):
    with db.connect() as con:
        rows = con.execute("""SELECT payload FROM analyses WHERE owner=? AND company_id=?
            AND mode=? AND kind='company' AND created_at<=?
            ORDER BY created_at DESC,rowid DESC LIMIT ?""",
            (owner, company_id, mode, as_of or db.now(), limit)).fetchall()
    return [{'id': item['id'], 'created_at': item['created_at'], 'scores': item['scores'],
             'scoring_version': item['scoring_version'], 'source_count': item['coverage']['source_count']} for item in
            (json.loads(row['payload']) for row in reversed(rows))]


def comparison_context(owner, item):
    context = {'trend': [], 'previous': None, 'score_changes': {}, 'method_changed': False,
               'peers': {'sector': item['company'].get('sector'), 'metrics': {},
                         'description': 'Workspace companies only; not a market benchmark. At least three comparable companies, including this one, are required.'}}
    if item['kind'] != 'company':
        return context
    context['trend'] = trend_rows(owner, item['company']['id'], item['mode'], 50, item['created_at'])
    with db.connect() as con:
        prior = con.execute("""SELECT payload FROM analyses WHERE owner=? AND company_id=?
            AND mode=? AND kind='company' AND created_at<=? AND id!=?
            ORDER BY created_at DESC,rowid DESC LIMIT 1""",
            (owner, item['company']['id'], item['mode'], item['created_at'], item['id'])).fetchone()
    if prior:
        previous = json.loads(prior['payload'])
        context['previous'] = {'id': previous['id'], 'created_at': previous['created_at']}
        changes = analysis.changes(previous, item)
        context['score_changes'] = changes['score_changes']
        context['method_changed'] = changes['method_changed']
    sector = item['company'].get('sector', '')
    if sector in ('', 'Not classified') or item['coverage']['status'] == 'Limited evidence':
        return context
    # Use each issuer once, with only snapshots that existed at the selected date.
    earliest = (datetime.fromisoformat(item['created_at']) - timedelta(days=90)).isoformat()
    with db.connect() as con:
        rows = con.execute("""WITH ranked AS (
            SELECT payload, ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY created_at DESC,rowid DESC) AS position
            FROM analyses WHERE owner=? AND mode=? AND kind='company' AND company_id!=?
            AND created_at BETWEEN ? AND ?)
            SELECT payload FROM ranked WHERE position=1""",
            (owner, item['mode'], item['company']['id'], earliest, item['created_at'])).fetchall()
    candidates = [json.loads(row['payload']) for row in rows]
    peers = [p for p in candidates if p['company'].get('sector', '').casefold() == sector.casefold()
             and p['scoring_version'] == item['scoring_version'] and p['coverage']['status'] != 'Limited evidence']
    for key, metric in item['scores'].items():
        values = [p['scores'][key]['score'] for p in peers if p['scores'][key]['score'] is not None]
        available = metric['score'] is not None and len(values) >= 2
        cohort = values + [metric['score']] if available else []
        context['peers']['metrics'][key] = {'available': available, 'peer_count': len(values),
            'sample_size': len(cohort), 'median': median(cohort) if available else None,
            'percentile': round(100 * (sum(v < metric['score'] for v in cohort) +
                           0.5 * sum(v == metric['score'] for v in cohort)) / len(cohort)) if available else None}
    return context
