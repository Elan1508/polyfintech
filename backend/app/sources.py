import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse

import httpx

from . import config, db

HEADERS = {'User-Agent': 'ESGPulse360/2.0 public-company-research'}
NEWS_VERSION = 'company-news-4'
SEED_LISTINGS = {
    'dbs': ('DBS Group Holdings', 'D05', 'SGX', ['DBS', 'DBS Bank']),
    'ocbc': ('Oversea-Chinese Banking Corporation', 'O39', 'SGX', ['OCBC']),
    'uob': ('United Overseas Bank', 'U11', 'SGX', ['UOB']),
    'singtel': ('Singapore Telecommunications', 'Z74', 'SGX', ['Singtel']),
    'grab': ('Grab Holdings', 'GRAB', 'NASDAQ', ['Grab']),
    'sea': ('Sea Limited', 'SE', 'NYSE', ['Sea Ltd', 'Sea Limited', 'Shopee', 'Garena']),
    'wilmar': ('Wilmar International', 'F34', 'SGX', ['Wilmar']),
    'capitaland': ('CapitaLand Investment', '9CI', 'SGX', ['CapitaLand']),
    'aia': ('AIA Group', '1299', 'HKEX', ['AIA Group']),
    'keppel': ('Keppel', 'BN4', 'SGX', ['Keppel']),
    'sembcorp': ('Sembcorp Industries', 'U96', 'SGX', ['Sembcorp']),
    'comfortdelgro': ('ComfortDelGro', 'C52', 'SGX', ['ComfortDelGro']),
    'thai_union': ('Thai Union Group', 'TU', 'SET', ['Thai Union']),
}


def clean(text):
    value = html.unescape(re.sub('<[^>]+>', ' ', str(text or '')))
    english = re.search(r'\{:EN\}(.*?)(?=\{:(?:[A-Z]{2})?\}|$)', value, re.I | re.S)
    if english:
        value = english.group(1)
    return re.sub(r'\s+', ' ', re.sub(r'\{:(?:[A-Z]{2})?\}', '', value)).strip()


def safe_url(value):
    parsed = urlparse(value or '')
    return value if parsed.scheme in ('http', 'https') and parsed.netloc and not parsed.username else ''


def cached(key):
    with db.connect() as con:
        row = con.execute('SELECT payload FROM cache WHERE key=? AND expires_at>?', (key, time.time())).fetchone()
    return json.loads(row['payload']) if row else None


def cache(key, value, ttl):
    with db.connect() as con:
        con.execute('INSERT INTO cache VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at',
                    (key, json.dumps(value), time.time() + ttl))
    return value


def get(url, params=None):
    with httpx.Client(timeout=9, headers=HEADERS, follow_redirects=False) as client:
        with client.stream('GET', url, params=params) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 8 * 1024 * 1024:
                    raise ValueError('Source response exceeded size limit')
            return bytes(content)


def seed_directory():
    fixture = json.loads((config.BACKEND / 'app/data/companies.json').read_text(encoding='utf-8'))
    for row in fixture:
        name, ticker, exchange, aliases = SEED_LISTINGS[row['company_id']]
        company_id = f"directory:{row['company_id']}"
        if not db.company(company_id):
            db.put_company({'id': company_id, 'name': name, 'ticker': ticker, 'exchange': exchange,
                            'country': row['country'], 'sector': row['sector'], 'aliases': aliases,
                            'identity_source': 'Starter listing directory', 'identity_url': '', 'demo_key': row['company_id']})
    from . import research
    for key, entry in research.CATALOG['companies'].items():
        if key in SEED_LISTINGS:
            continue
        company_id = 'directory:' + key
        existing = db.company(company_id)
        if existing and entry.get('cik') and existing.get('cik') != entry['cik']:
            db.put_company({**existing, 'cik': entry['cik']})
        if not db.company(company_id):
            db.put_company({'id': company_id, 'name': entry['name'], 'ticker': entry['listing'][0], 'exchange': entry['listing'][1],
                            'country': entry.get('country', 'US' if entry['listing'][1] != 'SGX' else 'SG'),
                            'sector': entry.get('sector', 'Information Technology'), 'aliases': [entry['name']],
                            'cik': entry.get('cik'), 'identity_source': 'Reviewed listed-company catalog', 'identity_url': entry['documents'][0]['url']})


def sec_search(query):
    listing = cached('sec:listings')
    if listing is None:
        listing = json.loads(get('https://www.sec.gov/files/company_tickers_exchange.json'))
        cache('sec:listings', listing, 86400)
    q = query.casefold()
    result = []
    for values in listing.get('data', []):
        record = dict(zip(listing['fields'], values))
        name, ticker = record.get('name', ''), record.get('ticker', '')
        if q not in name.casefold() and q not in ticker.casefold():
            continue
        cik = str(record['cik']).zfill(10)
        result.append({'id': f'sec:{cik}', 'name': name.title(), 'ticker': ticker,
                       'exchange': record.get('exchange') or 'US filing', 'country': 'US filing',
                       'sector': 'Not classified', 'aliases': [name], 'identity_source': 'SEC EDGAR listing directory',
                       'identity_url': f'https://www.sec.gov/edgar/browse/?CIK={cik}', 'cik': cik})
    result.sort(key=lambda c: (c['ticker'].casefold() != q, not c['name'].casefold().startswith(q), c['name']))
    return result[:12]


def gleif_search(query):
    key = 'gleif:' + query.casefold()
    data = cached(key)
    if data is None:
        data = json.loads(get('https://api.gleif.org/api/v1/lei-records',
                              {'filter[fulltext]': query, 'page[size]': 12}))
        cache(key, data, 86400)
    result = []
    for item in data.get('data', []):
        entity = item['attributes']['entity']
        if entity.get('status') != 'ACTIVE':
            continue
        name = entity['legalName']['name']
        aliases = [row['name'] for row in entity.get('otherNames', [])]
        normal_query = re.sub(r'\W', '', query).casefold()
        if not any(normal_query in re.sub(r'\W', '', candidate).casefold() for candidate in [name, *aliases]):
            continue
        result.append({'id': f"lei:{item['id']}", 'name': name, 'ticker': '', 'exchange': 'Legal entity',
                       'country': entity.get('legalAddress', {}).get('country', 'Unknown'), 'sector': 'Not classified',
                       'aliases': aliases + [name], 'identity_source': 'GLEIF legal entity register',
                       'identity_url': f"https://search.gleif.org/#/record/{item['id']}", 'lei': item['id']})
    return result


def search(query, listed_only=False):
    from .research import entry_for
    known = db.companies()
    local = [c for c in known if not query or query.casefold() in
             ' '.join([c['name'], c.get('ticker', ''), *c.get('aliases', [])]).casefold()]
    warnings, remote = [], []
    if len(query) >= 2:
        with ThreadPoolExecutor(max_workers=2) as executor:
            providers = [('SEC', sec_search)] if listed_only else [('SEC', sec_search), ('GLEIF', gleif_search)]
            futures = [(name, executor.submit(fn, query)) for name, fn in providers]
            for name, future in futures:
                try:
                    remote.extend(future.result())
                except Exception:
                    warnings.append(f'{name} company search is temporarily unavailable. Showing available directory matches.')
    seen, rows = set(), []
    starter_ciks = {c['cik']: c for c in known if c.get('demo_key') and c.get('cik')}
    for company in local + remote:
        ticker = company.get('ticker', '').casefold()
        exchange = company.get('exchange', '').casefold()
        if listed_only and not ticker:
            continue
        canonical = starter_ciks.get(company.get('cik')) or next((c for c in known if c.get('demo_key') and ticker and
                          c.get('ticker', '').casefold() == ticker and c.get('exchange', '').casefold() == exchange), None)
        if canonical and canonical['id'] != company['id']:
            reference = {key: company[key] for key in ('cik',) if company.get(key)}
            company = {**canonical, **reference, 'aliases': list(dict.fromkeys(canonical.get('aliases', []) + company.get('aliases', []) + [company['name']]))}
            db.put_company(company)
            if company.get('cik'):
                starter_ciks[company['cik']] = company
        company = {**company, 'research_available': entry_for(company) is not None,
                   'entity_type': 'listed' if company.get('ticker') else 'legal_entity'}
        identity = (ticker or re.sub(r'\W', '', company['name']).casefold(), exchange)
        if company['id'] in seen or identity in seen:
            continue
        seen.update([company['id'], identity])
        db.put_company(company)
        rows.append(company)
    rows.sort(key=lambda c: (c.get('ticker', '').casefold() != query.casefold(), c['entity_type'] != 'listed',
                             not c['name'].casefold().startswith(query.casefold()), not c['research_available'], c['name'].casefold()))
    return {'companies': rows[:30 if query else 100], 'warnings': warnings, 'coverage': 'Reviewed STI and regional listings, SEC-listed companies, and GLEIF legal entities worldwide'}


def company_terms(company):
    names = [company['name'], *company.get('aliases', [])]
    shortened = [re.sub(r'\b(holdings?|corporation|corp|limited|ltd|inc|plc|co|group)\b\.?', '', name,
                         flags=re.I).strip(' ,.') for name in names]
    return list(dict.fromkeys(name for name in names + shortened if len(name) > 2))


def publisher_is_issuer(company, publisher):
    def normal(value):
        value = re.sub(r'\b(?:holdings?|corporation|corp|limited|ltd|inc|plc|co|group)\b\.?', '', value, flags=re.I)
        return re.sub(r'\W', '', value).casefold()
    key = normal(publisher)
    return len(key) >= 3 and any(key == normal(term) for term in company_terms(company))


def related(company, text):
    value = clean(text)
    contexts = {'sea': r'\b(shopee|garena|seamoney|monee|nyse|e-commerce|digital entertainment|sea limited|sea ltd)\b',
                'apple': r'\b(iphone|ipad|macbook|cupertino|technology|company|devices?|suppliers?)\b',
                'meta': r'\b(facebook|instagram|whatsapp|zuckerberg|technology|company)\b',
                'target': r'\b(retailer|retail|stores?|shopping|minneapolis|tgt|corporation)\b',
                'shell': r'\b(oil|gas|energy|fuel|petrol|plc)\b',
                'block': r'\b(square|cash app|fintech|dorsey|payments?)\b',
                'visa': r'\b(payments?|cards?|fintech|financial|nyse|company)\b',
                'venture': r'\b(corporation|V03|electronics|manufacturing|Singapore|Wong Ngit Liong|technology services)\b'}
    for term in company_terms(company):
        matches = list(re.finditer(r'(?<!\w)' + re.escape(term) + r'(?!\w)', value, re.I))
        if not matches:
            continue
        lowered = term.casefold()
        if lowered in ('grab', *contexts):
            # Common nouns are not enough to identify an issuer.
            if not any(match.group()[0].isupper() for match in matches):
                continue
            if lowered == 'grab' and re.search(r'\b(?:land|power|tax|cash)\s+grab\b|\bgrab\s+(?:your|a|the)\b', value, re.I):
                continue
            if lowered in contexts and not re.search(contexts[lowered], value, re.I):
                continue
        return True
    return False


def collect_news(company, refresh=False):
    from .analysis import RULES, contains
    key = f"news:{NEWS_VERSION}:{company['id']}"
    old = cached(key)
    if old and not refresh:
        return {**old, 'cached': True}
    terms = company_terms(company)
    names = [name for name in terms if len(name) >= 3][:3] or [company['name']]
    name_query = ' OR '.join(f'"{name}"' for name in names)
    query = f'({name_query}) (ESG OR sustainability OR climate OR governance OR cybersecurity OR labour) when:1y'
    url = 'https://news.google.com/rss/search?' + urlencode({'q': query, 'hl': 'en-SG', 'gl': 'SG', 'ceid': 'SG:en'})
    warnings, sources, seen = [], [], set()
    try:
        root = ET.fromstring(get(url))
        for item in root.findall('./channel/item'):
            title, excerpt = clean(item.findtext('title')), clean(item.findtext('description'))
            if not related(company, title + ' ' + excerpt):
                continue
            if not any(contains(title + ' ' + excerpt, term) for rules in RULES.values() for terms in rules.values() for term in terms):
                continue
            fingerprint = re.sub(r'\W', '', title.rsplit(' - ', 1)[0]).casefold()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            try:
                published = parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc).isoformat(timespec='seconds')
            except (TypeError, ValueError):
                published = None
            source = item.find('source')
            publisher = clean(source.text) if source is not None else 'Google News RSS'
            self_reported = publisher_is_issuer(company, publisher)
            sources.append({'id': 'src_' + hashlib.sha256(fingerprint.encode()).hexdigest()[:16], 'title': title,
                            'excerpt': excerpt[:1800] or title, 'publisher': publisher,
                            'url': safe_url(item.findtext('link')), 'published_at': published, 'collected_at': db.now(),
                            'kind': 'news', 'page': None, 'report_id': None, 'self_reported': self_reported})
            if len(sources) >= 18:
                break
        if not sources:
            warnings.append('No matching recent articles were returned. Upload a company report to add primary evidence.')
    except Exception:
        warnings.append('Live news collection is unavailable. Retry later or upload a company report.')
        if old:
            return {**old, 'cached': True, 'warnings': old.get('warnings', []) + warnings}
    result = {'sources': sources, 'warnings': warnings, 'cached': False, 'collected_at': db.now(),
              'collection_url': url, 'languages': ['English'], 'version': NEWS_VERSION}
    return cache(key, result, 3600 if sources else 180)


def demo_sources(company):
    data = json.loads((config.BACKEND / 'app/data/companies.json').read_text(encoding='utf-8'))
    row = next((c for c in data if c['company_id'] == company.get('demo_key')), None)
    if not row:
        raise ValueError('Demo evidence is available only for the starter examples. Use live analysis for this company.')
    return [{'id': f"demo_{row['company_id']}_{i}", 'title': a['title'], 'excerpt': a['text'],
             'publisher': 'Synthetic demo fixture', 'url': '', 'published_at': a['date'] + 'T00:00:00+00:00',
             'collected_at': db.now(), 'kind': 'demo', 'page': None, 'report_id': None, 'self_reported': False}
            for i, a in enumerate(row.get('news_articles', []))]
