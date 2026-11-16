"""Public, listing-matched company context with dated source links."""
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from . import db, research, sources


def value(claim):
    return claim.get('mainsnak', {}).get('datavalue', {}).get('value')


def active(claim):
    if claim.get('rank') == 'deprecated':
        return False
    qualifiers = claim.get('qualifiers', {})
    ends = qualifiers.get('P582', [])
    starts = qualifiers.get('P580', [])
    return not any(q.get('datavalue', {}).get('value', {}).get('time', '')[1:11] <= db.now()[:10] for q in ends) and not any(
        q.get('datavalue', {}).get('value', {}).get('time', '')[1:11] > db.now()[:10] for q in starts)


def latest(claims):
    rows = [c for c in claims if active(c)]
    def stamp(c):
        return max((q.get('datavalue', {}).get('value', {}).get('time', '') for prop in ('P585', 'P580') for q in c.get('qualifiers', {}).get(prop, [])), default='')
    return sorted(rows, key=lambda c: (c.get('rank') == 'preferred', stamp(c)), reverse=True)


def point_in_time(raw):
    value = raw.lstrip('+')[:10]
    if value.endswith('-00-00'):
        return value[:4]
    if value.endswith('-00'):
        return value[:7]
    return value


def entity(qid):
    if not re.fullmatch(r'Q\d+', qid):
        raise ValueError('Invalid Wikidata identity')
    key = 'wikidata:' + qid
    record = sources.cached(key)
    if not record:
        record = json.loads(sources.get('https://www.wikidata.org/w/api.php?' + urlencode({'action': 'wbgetentities', 'ids': qid, 'format': 'json', 'languages': 'en'})))['entities'][qid]
        sources.cache(key, record, 86400)
    return record


def wikidata(entry):
    qid = entry.get('wikidata_id')
    if not qid:
        return [], None
    record = entity(qid)
    facts, ids = [], {}
    for prop, label in [('P159', 'Headquarters'), ('P571', 'Founded'), ('P1128', 'Employees'), ('P169', 'Chief executive'), ('P856', 'Website')]:
        claims = latest(record.get('claims', {}).get(prop, []))
        if not claims:
            continue
        claim, raw = claims[0], value(claims[0])
        if not raw:
            continue
        as_of = next((point_in_time(q.get('datavalue', {}).get('value', {}).get('time', '')) for q in claim.get('qualifiers', {}).get('P585', [])), None)
        if isinstance(raw, dict) and raw.get('id'):
            ids[raw['id']] = len(facts)
            display = raw['id']
        elif isinstance(raw, dict) and 'time' in raw:
            display = raw['time'][1:5]
        elif isinstance(raw, dict) and 'amount' in raw:
            display = f"{float(raw['amount']):,.0f}"
        else:
            display = str(raw)
        facts.append({'label': label, 'value': display, 'as_of': as_of, 'url': f'https://www.wikidata.org/wiki/{qid}#{prop}', 'provider': 'Wikidata'})
    for linked, index in ids.items():
        try:
            labels = entity(linked).get('labels', {})
            facts[index]['value'] = labels.get('en', next(iter(labels.values()), {'value': linked}))['value']
        except Exception:
            facts[index]['value'] = 'See linked Wikidata record'
    title = record.get('sitelinks', {}).get('enwiki', {}).get('title')
    return facts, title


def market(company):
    result = []
    if company.get('exchange', '').upper() == 'SGX':
        import yfinance as yf
        symbol = company['ticker'] + '.SI'
        info = yf.Ticker(symbol).get_info()
        currency = info.get('currency')
        date = datetime.fromtimestamp(info['regularMarketTime'], timezone.utc).isoformat() if info.get('regularMarketTime') else None
        for key, label in [('regularMarketPrice', 'Last reported price'), ('marketCap', 'Market capitalisation'), ('trailingPE', 'Trailing P/E'), ('fiftyTwoWeekLow', '52-week low'), ('fiftyTwoWeekHigh', '52-week high')]:
            v = info.get(key)
            if isinstance(v, (int, float)) and math.isfinite(v):
                result.append({'label': label, 'value': v, 'unit': 'ratio' if key == 'trailingPE' else currency,
                               'as_of': date, 'provider': 'Yahoo Finance via yfinance', 'url': f'https://finance.yahoo.com/quote/{quote(symbol)}/'})
    elif company.get('cik') or (research.entry_for(company) or {}).get('cik'):
        cik = str(company.get('cik') or research.entry_for(company)['cik']).zfill(10)
        if not re.fullmatch(r'\d{10}', cik):
            return []
        url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
        taxonomies = json.loads(sources.get(url)).get('facts', {})
        data = {**taxonomies.get('ifrs-full', {}), **taxonomies.get('us-gaap', {})}
        for keys, label in [(['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'Revenue'], 'Annual revenue'), (['NetIncomeLoss', 'ProfitLoss'], 'Annual net income'), (['Assets'], 'Total assets'), (['StockholdersEquity', 'Equity'], 'Shareholders’ equity'), (['CashAndCashEquivalentsAtCarryingValue', 'CashAndCashEquivalents'], 'Cash and equivalents')]:
            values = [v for key in keys for v in data.get(key, {}).get('units', {}).get('USD', []) if v.get('form') in ('10-K', '20-F') and v.get('filed', '') <= db.now()[:10] and (label not in ('Annual revenue', 'Annual net income') or v.get('start') and 330 <= (datetime.fromisoformat(v['end']) - datetime.fromisoformat(v['start'])).days <= 380)]
            if values:
                v = max(values, key=lambda x: (x['end'], x.get('filed', '')))
                result.append({'label': label, 'value': v['val'], 'unit': 'USD', 'as_of': v['end'], 'provider': 'SEC company facts', 'url': url})
    return result


def collect(company):
    key = 'snapshot:1:' + company['id']
    cached = sources.cached(key)
    if cached is not None:
        return cached
    entry = research.entry_for(company)
    result = {'summary': '', 'facts': [], 'market': [], 'sources': [], 'collected_at': db.now(),
              'notice': 'Company context is sourced separately from ESG indicators. Market figures may be delayed; Wikidata facts can be incomplete or outdated.'}
    if not entry:
        if not company.get('cik'):
            result['notice'] = 'A verified listed-company identity is needed before linking public profiles or market data.'
            return result
        try:
            cik = str(company['cik']).zfill(10)
            if not re.fullmatch(r'\d{10}', cik):
                return result
            url = f'https://data.sec.gov/submissions/CIK{cik}.json'
            record = json.loads(sources.get(url))
            name, industry = record.get('name', company['name']), record.get('sicDescription')
            summary = name + (f" files with the SEC in the {industry.lower()} industry." if industry else ' is listed in the SEC filing directory.')
            result.update(summary=summary, summary_source_id='profile_' + company['id'])
            address = record.get('addresses', {}).get('business', {})
            location = ', '.join(v for v in [address.get('city'), address.get('stateOrCountryDescription')] if v)
            if location:
                result['facts'].append({'label': 'Business address', 'value': location, 'as_of': None, 'url': url, 'provider': 'SEC submissions'})
            result['sources'] = [{'id': result['summary_source_id'], 'title': 'SEC company profile', 'excerpt': summary,
                                  'url': url, 'publisher': 'SEC submissions', 'kind': 'profile', 'page': None, 'report_id': None, 'published_at': None}]
            result['market'] = market(company)
            return sources.cache(key, result, 86400)
        except Exception:
            result['warnings'] = ['The SEC company snapshot is temporarily unavailable. No figures have been estimated.']
            return sources.cache(key, result, 600)
    if entry.get('identity_note'):
        result['notice'] += ' ' + entry['identity_note']
    title = entry.get('wikipedia_title')
    try:
        result['facts'], linked_title = wikidata(entry)
        title = linked_title or title
    except Exception:
        result['warnings'] = ['Wikidata is temporarily unavailable.']
    if title:
        try:
            data = json.loads(sources.get('https://en.wikipedia.org/api/rest_v1/page/summary/' + quote(title, safe='')))
            text = data.get('extract', '')[:2200]
            if text:
                # A short opening sentence avoids cutting names at initials ("John D.").
                parts = re.split(r'(?<!\b[A-Z]\.)(?<!\bInc\.)(?<!\bLtd\.)(?<=[.!?])\s+(?=[A-Z])', text)
                result['summary'] = parts[0]
                result['summary_source_id'] = 'profile_' + company['id']
                result['sources'].append({'id': result['summary_source_id'], 'title': title + ' · Company overview', 'excerpt': text,
                    'publisher': 'Wikipedia contributors (CC BY-SA)', 'url': data.get('content_urls', {}).get('desktop', {}).get('page') or 'https://en.wikipedia.org/wiki/' + quote(title),
                    'kind': 'profile', 'page': None, 'report_id': None, 'published_at': None})
        except Exception:
            pass
    if not result['summary']:
        # Catalog business descriptions are attributed to a reviewed company publication.
        text = entry.get('business_summary') or entry['overview']
        doc = entry['documents'][0]
        result['summary'] = text
        result['summary_source_id'] = 'profile_' + company['id']
        result['sources'].append({'id': result['summary_source_id'], 'title': 'Company overview · ' + doc['publisher'], 'excerpt': text,
                                 'publisher': doc['publisher'] + ' (curated summary)', 'url': doc['url'], 'kind': 'profile', 'page': None, 'report_id': None, 'published_at': None})
    try:
        result['market'] = market(company)
    except Exception:
        result.setdefault('warnings', []).append('Financial snapshot is temporarily unavailable; no values have been estimated.')
    return sources.cache(key, result, 86400 if result['market'] else 3600)
