import hashlib
import io
import json
import re
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx
from pypdf import PdfReader

from . import config, db, sources

VERSION = 'official-pages-2026-11-15.1'
CATALOG = json.loads((config.BACKEND / 'app/data/research_catalog.json').read_text(encoding='utf-8'))
ALLOWED_HOSTS = {urlparse(doc['url']).hostname for entry in CATALOG['companies'].values() for doc in entry['documents']} | {'www.sec.gov', 'data.sec.gov'}


def entry_for(company):
    if company.get('demo_key') in CATALOG['companies']:
        return CATALOG['companies'][company['demo_key']]
    for entry in CATALOG['companies'].values():
        ticker, exchange = entry['listing']
        if company.get('ticker', '').upper() == ticker and company.get('exchange', '').upper() == exchange:
            return entry
        if company.get('cik') and str(company['cik']).zfill(10) == entry.get('cik'):
            return entry
    return None


def preview(company):
    entry = entry_for(company)
    if not entry:
        return None
    return {'overview': entry['overview'], 'highlights': entry['highlights'], 'documents': entry['documents'],
            'reviewed_at': CATALOG['reviewed_at'], 'identity_facts': [],
            'status': 'Company publications available' if all(d.get('format') == 'html' for d in entry['documents']) else 'Official reports available',
            'notice': 'Research notes summarise company publications. Company-reported claims have not been independently verified.'}


def profile(company):
    curated = preview(company)
    if curated:
        return curated
    if company.get('lei'):
        key = 'identity:' + company['lei']
        record = sources.cached(key)
        try:
            if not record:
                record = json.loads(sources.get('https://api.gleif.org/api/v1/lei-records/' + quote(company['lei'], safe='')))
                sources.cache(key, record, 86400)
            entity = record['data']['attributes']['entity']
            address = entity.get('legalAddress', {})
            registration = entity.get('registeredAs') or ''
            facts = [{'label': 'Registered name', 'value': entity['legalName']['name']},
                     {'label': 'Location', 'value': ', '.join(v for v in [address.get('city'), address.get('country')] if v)},
                     {'label': 'Legal entity identifier', 'value': company['lei']},
                     {'label': 'Registration number', 'value': registration}]
            return {'overview': f"{entity['legalName']['name']} is recorded in the GLEIF legal-entity register"
                                + (f" with its registered location in {address['city']}." if address.get('city') else '.'),
                    'identity_facts': [f for f in facts if f['value']], 'highlights': [],
                    'documents': [{'title': 'Verified legal-entity record', 'url': f"https://api.gleif.org/api/v1/lei-records/{company['lei']}", 'publisher': 'GLEIF', 'kind': 'registry'}],
                    'reviewed_at': db.now()[:10], 'status': 'Company profile available',
                    'notice': 'The registry confirms company identity, not ESG performance. A similar name does not establish a relationship with another business.'}
        except Exception:
            pass
    return {'overview': f"Explore the available reports and news for {company['name']}.", 'identity_facts': [],
            'highlights': [], 'documents': [], 'reviewed_at': None, 'status': 'Research in progress',
            'notice': 'Public information varies by company. You can add an official report to expand this analysis.'}


def public_get(url):
    # Only explicitly selected issuer sites and SEC filing hosts may be fetched.
    with httpx.Client(timeout=18, headers=sources.HEADERS, follow_redirects=False) as client:
        for _ in range(5):
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.port not in (None, 443):
                raise ValueError('Unsupported report location')
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                data = bytearray()
                for part in response.iter_bytes():
                    data.extend(part)
                    if len(data) > 90 * 1024 * 1024:
                        raise ValueError('Report exceeds download limit')
                return bytes(data)
    raise ValueError('Report redirected too many times')


class DocumentText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden += 1
        if not self.hidden and tag in ('p', 'div', 'section', 'h1', 'h2', 'h3', 'tr', 'li', 'br'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'nav', 'footer'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data + ' ')


def report_pages(content):
    if content.startswith(b'%PDF-'):
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted and not reader.decrypt(''):
            raise ValueError('Report is password protected')
        if len(reader.pages) > 500:
            raise ValueError('Report cannot be extracted')
        pages, total = [], 0
        for index, page in enumerate(reader.pages):
            stream = page.get_contents()
            if stream and len(stream.get_data()) > 8 * 1024 * 1024:
                continue
            text = page.extract_text() or ''
            total += len(text)
            if total > 1_500_000:
                break
            pages.append((index + 1, text))
        return pages
    parser = DocumentText()
    parser.feed(content.decode('utf-8', errors='replace')[:4_000_000])
    text = ''.join(parser.parts)
    return [(None, text[index:index + 3500]) for index in range(0, min(len(text), 1_500_000), 3500)]


def extract_document(doc, pages=None):
    from .analysis import RULES, contains
    pages = pages if pages is not None else report_pages(public_get(doc['url']))
    candidates = []
    for page, text in pages:
        # Contents pages list topics without the context needed to assess them.
        if re.search(r'\btable\s+of\s+contents?\b|\bcontents\s+at\s+a\s+glance\b|^\s*contents\b', text[:800], re.I) or len(re.findall(r'\.{3,}\s*\d+', text)) >= 5:
            continue
        blocks = re.split(r'\n\s*\n', text)
        for block in blocks:
            block = re.sub(r'\s+', ' ', block).strip()
            if len(block) < 100:
                continue
            for passage in text_windows(block):
                if len(passage) < 100:
                    continue
                dimensions = {key: sum(contains(passage, term) for terms in rules.values() for term in terms) for key, rules in RULES.items()}
                if not any(dimensions.values()):
                    continue
                candidates.append((sum(min(4, v) for v in dimensions.values()), dimensions, page, passage))
    candidates.sort(key=lambda row: row[0], reverse=True)
    selected, seen = [], set()
    for dimension in RULES:
        for row in candidates:
            if row[1][dimension] and row[3] not in seen:
                selected.append(row); seen.add(row[3]); break
    for row in candidates:
        if row[3] not in seen:
            selected.append(row); seen.add(row[3])
        if len(selected) >= 12:
            break
    return [{'id': 'official_' + hashlib.sha256((doc['url'] + passage).encode()).hexdigest()[:18],
             'title': doc['title'] + (f' · Page {page}' if page else ''), 'excerpt': passage,
             'publisher': doc['publisher'], 'url': doc['url'], 'published_at': (doc['published_at'] + 'T00:00:00+00:00') if doc.get('published_at') else None,
             'collected_at': db.now(), 'kind': 'disclosure', 'page': page, 'report_id': None,
             'evidence_group': doc['url'], 'self_reported': True}
            for _, _, page, passage in selected]


def text_windows(text):
    start = 0
    while start < len(text):
        end = min(len(text), start + 1200)
        if end < len(text):
            end = text.rfind(' ', start + 600, end) or end
            if end <= start:
                end = start + 1200
        yield text[start:end].strip()
        if end >= len(text):
            break
        boundary = text.find(' ', max(start + 1, end - 200))
        start = boundary + 1 if boundary >= 0 else end


def sec_document(company):
    cik = company.get('cik')
    if not cik:
        return None
    cik = str(cik).zfill(10)
    if not re.fullmatch(r'\d{10}', cik):
        return None
    metadata = json.loads(sources.get(f'https://data.sec.gov/submissions/CIK{cik}.json'))
    recent = metadata.get('filings', {}).get('recent', {})
    for index, form in enumerate(recent.get('form', [])):
        if form not in ('10-K', '20-F', '40-F'):
            continue
        accession = recent['accessionNumber'][index].replace('-', '')
        document = recent['primaryDocument'][index]
        if not re.fullmatch(r'\d+', accession) or '/' in document or '\\' in document:
            continue
        return {'title': f"{company['name']} · {form} annual filing", 'publisher': company['name'],
                'url': f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{quote(document, safe=".-_")}',
                'published_at': recent['filingDate'][index]}
    return None


def collect(company):
    key = f'disclosures:{VERSION}:{company["id"]}'
    old = sources.cached(key)
    if old is not None:
        return {**old, 'cached': True}
    info = profile(company)
    documents = [doc for doc in info['documents'] if doc.get('kind') != 'registry']
    warnings, evidence, retained = [], [], []
    if not documents and company.get('cik'):
        try:
            filing = sec_document(company)
            if filing:
                documents.append(filing)
                info['documents'] = documents
                info['status'] = 'Annual filing available'
        except Exception:
            warnings.append('Annual filings could not be checked right now. You can still open available sources or add a report.')
    for doc in documents[:2]:
        try:
            pages = report_pages(public_get(doc['url']))
            passages = extract_document(doc, pages)
            if not passages:
                raise ValueError('No readable ESG passages')
            evidence.extend(passages)
            retained.append({**doc, 'id': hashlib.sha256(doc['url'].encode()).hexdigest()[:20],
                             'pages': [{'page': p, 'label': f'Page {p}' if p else f'Section {i + 1}', 'text': text}
                                       for i, (p, text) in enumerate(pages)]})
            break
        except Exception:
            warnings.append(f"We found {doc['title']}, but could not read it automatically. Open it from the company profile to read the original.")
    if not retained:
        # Reviewed short quotations can remain useful when issuer downloads block
        # automated access. They are explicitly excerpts, never complete report pages.
        for excerpt in (entry_for(company) or {}).get('reviewed_excerpts', []):
            doc = next((d for d in documents if d['url'] == excerpt['url']), None)
            if not doc:
                continue
            quote = excerpt['quote']
            source_id = 'reviewed_' + hashlib.sha256((doc['url'] + quote).encode()).hexdigest()[:18]
            retained.append({**doc, 'id': hashlib.sha256(doc['url'].encode()).hexdigest()[:20], 'excerpt_only': True,
                             'pages': [{'page': excerpt.get('page'), 'label': 'Reviewed excerpt only', 'text': quote}]})
            evidence.append({**doc, 'id': source_id, 'excerpt': quote, 'kind': 'disclosure', 'page': excerpt.get('page'),
                             'report_id': None, 'published_at': None, 'collected_at': db.now(),
                             'evidence_group': doc['url'], 'self_reported': True, 'excerpt_only': True})
        if retained:
            warnings.append('Includes a short, manually reviewed issuer quotation. Full report extraction was unavailable; this is not complete report coverage.')
    result = {'sources': evidence, 'documents': retained, 'profile': info, 'warnings': warnings, 'cached': False, 'version': VERSION}
    return sources.cache(key, result, 86400 if evidence else 600)
