import io
import json

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import analysis, db, research, sources
from conftest import headers, run_analysis


collect_official = research.collect


def test_profiles_match_verified_listing_not_similar_name():
    german = {'id': 'lei:529900T1W8U0BS46AL65', 'name': 'Grab Verwaltungs GmbH', 'ticker': '', 'exchange': 'Legal entity'}
    assert research.entry_for(german) is None
    assert research.entry_for({**german, 'name': 'Grab Holdings'}) is None
    listed = {'id': 'sec:0001855612', 'ticker': 'GRAB', 'exchange': 'Nasdaq'}
    assert research.entry_for(listed)['name'] == 'Grab Holdings'
    assert research.entry_for({'cik': '1045810'})['name'] == 'NVIDIA'


def test_registry_facts_do_not_become_esg_performance(client, monkeypatch):
    company = {'id': 'lei:529900T1W8U0BS46AL65', 'name': 'Grab Verwaltungs GmbH', 'lei': '529900T1W8U0BS46AL65'}
    record = {'data': {'attributes': {'entity': {'legalName': {'name': company['name']},
              'legalAddress': {'city': 'Eschelbronn', 'country': 'DE'}, 'registeredAs': 'HRB 750272'}}}}
    monkeypatch.setattr(sources, 'get', lambda url: json.dumps(record).encode())
    result = collect_official(company)
    assert result['sources'] == []
    assert result['profile']['identity_facts'][1]['value'] == 'Eschelbronn, DE'
    assert 'Grab Holdings' not in result['profile']['overview']
    assert result['profile']['documents'][0]['kind'] == 'registry'
    empty = analysis.build(company, result['sources'])
    assert all(value['score'] is None for value in empty['scores'].values())


def test_listed_search_excludes_private_entities_and_preserves_cik(client, monkeypatch):
    private = {'id': 'lei:OTHER', 'name': 'Grab Verwaltungs GmbH', 'ticker': '', 'exchange': 'Legal entity', 'country': 'DE'}
    db.put_company(private)
    monkeypatch.setattr(sources, 'sec_search', lambda q: [{'id': 'sec:0001855612', 'name': 'Grab Holdings Limited',
                         'ticker': ticker, 'exchange': 'Nasdaq', 'cik': '0001855612'} for ticker in ['GRAB', 'GRABW']])
    calls = []
    monkeypatch.setattr(sources, 'gleif_search', lambda q: calls.append(q) or [private])
    headers(client)
    listed = client.get('/api/companies?q=Grab&listed_only=true').json()['companies']
    assert [c['id'] for c in listed] == ['directory:grab']
    assert listed[0]['research_available'] is True
    assert db.company('directory:grab')['cik'] == '0001855612'
    assert calls == []
    all_entities = client.get('/api/companies?q=Grab').json()['companies']
    assert all_entities[0]['id'] == 'directory:grab'
    assert any(c['id'] == private['id'] and not c['research_available'] for c in all_entities)


def test_official_pdf_quotes_keep_pages_and_single_document_count(monkeypatch):
    text = 'Our renewable energy programme supports carbon reduction and worker safety. The board reviews governance controls and data protection each year.'
    writer = PdfWriter()
    for _ in range(3):
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    monkeypatch.setattr(research, 'public_get', lambda url: output.getvalue())
    document = {'url': 'https://issuer.example/report.pdf', 'title': 'Sustainability report', 'publisher': 'Issuer', 'published_at': None}
    passages = research.extract_document(document)
    assert len(passages) == 1  # Identical pages never multiply evidence.
    assert passages[0]['excerpt'] == text
    assert passages[0]['page'] == 1 and passages[0]['published_at'] is None
    assert passages[0]['self_reported'] is True
    expanded = [dict(passages[0], id=f'passage_{i}', page=i + 1) for i in range(12)]
    company = {'id': 'issuer', 'name': 'Issuer'}
    one = analysis.build(company, passages)
    many = analysis.build(company, expanded)
    assert many['scores'] == one['scores']
    assert many['coverage']['source_count'] == 1
    assert many['coverage']['excerpt_count'] == 12
    assert analysis.changes(None, many)['new_source_count'] == 1
    assert analysis.changes(one, many)['new_source_count'] == 0
    assert many['coverage']['status'] == 'Limited evidence'


def test_unreadable_report_uses_official_fallback_and_warns(client, monkeypatch):
    company = db.company('directory:ocbc')
    calls = []
    def extract(doc, pages=None):
        calls.append(doc['url'])
        if len(calls) == 1:
            return []  # Some sites return an empty challenge page with HTTP 200.
        return [{'id': 'original', 'excerpt': 'Original text'}]
    monkeypatch.setattr(research, 'extract_document', extract)
    monkeypatch.setattr(research, 'public_get', lambda url: b'<html>Mock report</html>')
    result = collect_official(company)
    assert len(calls) == 2
    assert result['sources'][0]['id'] == 'original'
    assert len(result['warnings']) == 1
    assert result['profile']['documents'][0]['url'] in calls
    assert collect_official(company)['cached'] is True
    assert len(calls) == 2


def test_dynamic_company_uses_verified_annual_filing(client, monkeypatch):
    company = {'id': 'sec:0000320193', 'name': 'Apple', 'cik': '0000320193', 'ticker': 'AAPL', 'exchange': 'Nasdaq'}
    metadata = {'filings': {'recent': {'form': ['8-K', '10-K'], 'accessionNumber': ['00001-26-001', '0000320193-26-000123'],
                'primaryDocument': ['current.htm', 'annual.htm'], 'filingDate': ['2026-11-01', '2026-10-30']}}}
    monkeypatch.setattr(sources, 'get', lambda url: json.dumps(metadata).encode())
    def extract(doc, pages=None):
        assert doc['url'] == 'https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/annual.htm'
        assert doc['published_at'] == '2026-10-30'
        return [{'id': 'sec-filing', 'excerpt': 'Actual annual filing text'}]
    monkeypatch.setattr(research, 'extract_document', extract)
    monkeypatch.setattr(research, 'public_get', lambda url: b'<html>Mock report</html>')
    result = collect_official(company)
    assert result['profile']['status'] == 'Annual filing available'
    assert result['sources'][0]['id'] == 'sec-filing'
    assert result['profile']['documents'][0]['title'] == 'Apple · 10-K annual filing'


def test_report_redirect_cannot_fetch_an_unapproved_host(monkeypatch):
    called = []
    def respond(request):
        called.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://127.0.0.1/private'})
    real_client = httpx.Client
    monkeypatch.setattr(research.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    with pytest.raises(ValueError, match='Unsupported report location'):
        research.public_get(research.CATALOG['companies']['grab']['documents'][0]['url'])
    assert len(called) == 1


def test_official_sources_flow_through_api_and_invalidate_old_cache(client, monkeypatch):
    monkeypatch.setattr(sources, 'collect_news', lambda company: {'sources': [], 'warnings': []})
    original = run_analysis(client, mode='live')
    with db.connect() as con:
        payload = {**original, 'research_version': 'old-version'}
        con.execute('UPDATE analyses SET payload=? WHERE id=?', (json.dumps(payload), original['id']))
    company = db.company('directory:dbs')
    source = {**sources.demo_sources(company)[0], 'kind': 'disclosure', 'evidence_group': 'official-report'}
    monkeypatch.setattr(research, 'collect', lambda company: {'sources': [source], 'profile': research.preview(company), 'warnings': []})
    updated = run_analysis(client, mode='live')
    assert updated['id'] != original['id']
    assert updated['research_version'] == research.VERSION
    assert updated['research']['documents']
    assert updated['sources'][0]['kind'] == 'disclosure'
    assert updated['coverage']['source_count'] == 1


def test_common_words_do_not_match_unrelated_company_news():
    grab = {'name': 'Grab Holdings', 'aliases': ['Grab']}
    assert not sources.related(grab, 'The Oxfordshire fields at the centre of Labour’s land grab')
    assert not sources.related(grab, 'The AI power grab nobody voted for: London Climate Action Week')
    assert not sources.related(grab, 'Grab your opportunity to support renewable energy')
    assert sources.related(grab, 'Grab, consultancy RSM to launch AI and cybersecurity initiatives')
    assert sources.related(grab, 'GRAB Stock Juggles Barclays Cut And Uber Board Exit')
    sea = {'name': 'Sea Limited', 'aliases': ['Shopee', 'Garena']}
    assert not sources.related(sea, 'Sea levels rise as emissions increase')
    assert sources.related(sea, 'Sea supports small businesses through Shopee')
    assert sources.related(sea, 'Sea Limited updates sustainability report')
    assert sources.clean('{:TH}Thai translation{:}{:EN}Grab ESG report{:}') == 'Grab ESG report'


def test_contents_pages_are_not_scored_and_passages_keep_whole_words(monkeypatch):
    contents = 'Public Table of Content ' + 'Renewable energy, financial inclusion and responsible AI. ' * 10
    body = 'The company reports renewable energy projects and worker safety controls. ' * 35
    monkeypatch.setattr(research, 'public_get', lambda url: b'pdf')
    monkeypatch.setattr(research, 'report_pages', lambda content: [(2, contents), (3, body)])
    passages = research.extract_document({'url': 'https://issuer.example/report.pdf', 'title': 'Annual report', 'publisher': 'Issuer'})
    assert passages and all(source['page'] == 3 for source in passages)
    for source in passages:
        assert source['excerpt'] in body
        assert source['excerpt'].split()[0] in body.split()
        assert source['excerpt'].split()[-1] in body.split()
