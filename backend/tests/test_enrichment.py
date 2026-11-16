import copy
import io
import json
import uuid

from pypdf import PdfReader

from app import analysis, assistant, briefs, company_pdf, db, facts, news, profiles, public_research, research, sources, worker
from conftest import headers, run_analysis

schedule_public = public_research.schedule
collect_profile = profiles.collect


def document(text, page=18, report_id=None):
    return {'id': 'doc', 'title': 'Issuer Sustainability Report', 'publisher': 'Issuer', 'url': 'https://issuer.example/report.pdf',
            'report_id': report_id, 'pages': [{'page': page, 'label': f'Page {page}', 'text': text}]}


def test_local_facts_verify_physical_pages_and_preserve_decimals():
    text = ('In 2025 our operational Scope 1 and Scope 2 market-based emissions were 32.5 tCO2e. '
            'We commit to net zero by 2050. Renewable electricity was 35% in 2025. '
            'In 2025, 40% of our board members were women. Our LTIFR was 0.25 per million hours in 2025.')
    result = facts.extract([document(text)], use_ai=False)
    by_metric = {f['metric']: f for f in result['items']}
    assert set(by_metric) == {'emissions', 'net_zero', 'renewable', 'board_women', 'injury_rate'}
    assert by_metric['emissions']['value'] == 32.5
    assert by_metric['emissions']['scope'] == '1+2'
    assert by_metric['injury_rate']['value'] == .25
    assert by_metric['net_zero']['status'] == 'target'
    assert by_metric['renewable']['status'] == 'reported'
    assert all(f['page'] == 18 and facts.verified(f['quote'], text) for f in result['items'])
    signed = facts.parse('In 2025 our net Scope 1/2 emissions were −12.5 tCO2e.')
    assert signed[0]['value'] == -12.5 and signed[0]['scope'] == '1+2'


def test_ai_quotes_cannot_fabricate_pages_values_or_hide_fallback(monkeypatch):
    monkeypatch.setattr(assistant, 'status', lambda: {'available': True})
    monkeypatch.setattr(assistant, 'structured', lambda *args: {'items': [
        {'key': 'doc:0', 'quote': 'We commit to net zero by 2040.'},
        {'key': 'doc:999', 'quote': 'We commit to net zero by 2050.'}]})
    result = facts.extract([document('We commit to net zero by 2050.')])
    assert [f['value'] for f in result['items']] == [2050]
    assert result['items'][0]['page'] == 18


def test_targets_and_workforce_percentages_are_not_mislabelled():
    text = ('IMO net zero shipping talks resume in 2026. We set our net zero strategy in 2022. '
            'The Net Zero Framework includes intensity cuts of 4% by 2028. '
            'We aim to achieve net zero for our own operations by 2050. '
            'Women now comprise 30% of our Board and 24% of our Group Management Committee. '
            'Achieve 35% female representation in India by 2026. '
            'Customers offset 5,000 tonnes of CO2e through our platform.')
    result = facts.extract([document(text)], use_ai=False)['items']
    assert [f['value'] for f in result if f['metric'] == 'net_zero'] == [2050]
    board = [f for f in result if f['metric'] == 'board_women']
    assert len(board) == 1 and board[0]['value'] == 30 and board[0]['status'] == 'reported'
    assert not any(f['metric'] == 'emissions' for f in result)
    assert next(f for f in result if f['metric'] == 'carbon_offsets')['value'] == 5000


def test_ai_can_surface_quoted_table_values_but_cannot_rank_unreviewed_cells(monkeypatch):
    quote = 'Renewable electricity share | FY2025 | 42.5% | Group operations.'
    monkeypatch.setattr(assistant, 'status', lambda: {'available': True})
    monkeypatch.setattr(assistant, 'structured', lambda *args: {'items': [{'key': 'doc:0', 'quote': quote, 'metric': 'renewable',
                         'value_text': '42.5%', 'period': 'FY2025', 'status': 'reported'}]})
    result = facts.extract([document(quote)])
    assert result['method'] == 'ai-assisted'
    row = next(f for f in result['items'] if f['metric'] == 'renewable')
    assert row['review_required'] and row['display'] == '42.5%' and row['page'] == 18
    assert facts.comparison([{'analysis': {'facts': result}}] * 2) == []


def test_nightly_public_schedule_catches_up_once_and_keeps_catalog_issuers(client, monkeypatch):
    scheduling = schedule_public
    scheduling()
    scheduling()
    with db.connect() as con:
        jobs = con.execute('SELECT * FROM jobs WHERE owner=?', (public_research.OWNER,)).fetchall()
    assert len(jobs) == len(research.CATALOG['companies'])
    assert len({j['company_id'] for j in jobs}) == len(research.CATALOG['companies'])


def test_ambiguous_periods_unknown_boundaries_and_targets_are_not_ranked():
    text = 'In 2025 operational Scope 1 and 2 market-based emissions were 100 tCO2e compared with 80 tCO2e in 2024.'
    metric = facts.extract([document(text)], use_ai=False)['items'][0]
    assert metric['period'] is None
    rows = [{'analysis': {'facts': {'items': [metric]}}}, {'analysis': {'facts': {'items': [{**metric, 'value': 110}]}}}]
    assert all(not r['comparable'] for r in facts.comparison(rows))
    valid = {**metric, 'period': '2025', 'status': 'reported'}
    rows[0]['analysis']['facts']['items'] = [valid]
    rows[1]['analysis']['facts']['items'] = [{**valid, 'value': 110}]
    result = facts.comparison(rows)
    assert result[0]['comparable']
    assert [c['rank'] for c in result[0]['cells']] == ['lowest', 'highest']
    rows[1]['analysis']['facts']['items'][0]['scope'] = '3'
    assert all(not r['comparable'] for r in facts.comparison(rows))
    rows[1]['analysis']['facts']['items'][0]['scope'] = '1+2'
    rows[1]['analysis']['facts']['items'].append({**valid, 'value': 500})
    assert not facts.comparison(rows)[0]['comparable']


def test_news_tags_do_not_turn_policies_into_controversies():
    source = {'id': 'article', 'kind': 'news', 'title': 'Issuer accused of deforestation in a new report',
              'excerpt': 'Reuters reports an allegation. The company says its policy prohibits deforestation.',
              'publisher': 'Reuters', 'url': 'https://news.example/a', 'published_at': '2026-11-15T00:00:00+00:00'}
    tagged = news.tag(source)
    assert tagged['controversy'] and tagged['sentiment'] == 'controversy' and 'E' in tagged['areas']
    assert not news.tag({**source, 'title': 'Issuer announces zero-deforestation policy', 'excerpt': 'A new policy to prevent deforestation.'})['controversy']
    assert not news.tag({**source, 'self_reported': True})['controversy']
    assert news.updates(None, {'sources': [tagged]}, '2026-11-14')['publisher'] == 'Reuters'
    assert news.updates(None, {'sources': [tagged]}, '2026-11-16') is None


def test_brief_rejects_bad_ai_quotes_and_never_sends_private_report(monkeypatch):
    item = analysis.build({'id': 'issuer', 'name': 'Issuer'}, [], mode='live')
    item['facts'] = facts.extract([document('We commit to net zero by 2050.')], use_ai=False)
    item['knowledge_sources'] = facts.evidence(item['facts'])
    item['sources'] = [{'id': 'secret', 'report_id': 'private', 'excerpt': 'PRIVATE UPLOAD', 'kind': 'report'}]
    monkeypatch.setattr(assistant, 'status', lambda: {'available': True})
    def generate(*args):
        assert 'PRIVATE UPLOAD' not in json.dumps(args)
        return {'items': [{'section': 'Strengths', 'text': 'Already carbon neutral.', 'source_id': item['knowledge_sources'][0]['id'], 'quote': 'We commit to net zero by 2050.'}]}
    monkeypatch.setattr(assistant, 'structured', generate)
    result = briefs.generate(item)
    assert result['mode'] == 'source'
    assert all('Already carbon neutral' not in r['text'] for r in result['items'])


def test_public_snapshots_are_readable_and_saved_as_private_copies(client):
    headers(client)
    shared = analysis.build(db.company('directory:dbs'), sources.demo_sources(db.company('directory:dbs')), mode='live')
    shared.update(public=True, research_version=research.VERSION, facts=facts.extract([], use_ai=False))
    db.store_analysis(public_research.OWNER, shared)
    assert client.get('/api/analyses/' + shared['id']).status_code == 200
    saved = client.patch('/api/analyses/' + shared['id'], headers=headers(client), json={'saved': True}).json()
    assert saved['analysis_id'] != shared['id']
    assert db.get_analysis(public_research.OWNER, shared['id'])['saved'] is False
    private_id = saved['analysis_id']
    assert client.get('/api/analyses/' + private_id).json()['saved'] is True
    client.cookies.clear()
    headers(client)
    assert client.get('/api/analyses/' + private_id).status_code == 404
    assert client.get('/api/analyses/' + private_id + '/brief.pdf').status_code == 404
    assert client.get('/api/analyses/' + shared['id']).status_code == 200
    assert client.get('/api/discover').json()['ready'] == 1


def test_public_worker_excludes_private_uploads_and_prioritises_user_jobs(client, monkeypatch):
    headers(client)
    with db.connect() as con:
        owner = con.execute('SELECT owner FROM sessions LIMIT 1').fetchone()['owner']
    private = analysis.build(db.company('directory:dbs'), [{'id': 'secret', 'kind': 'report', 'title': 'PRIVATE', 'excerpt': 'PRIVATE emissions 10 tCO2e', 'publisher': 'Private', 'url': '/api/reports/secret/file', 'report_id': 'secret', 'published_at': None}], kind='report', mode='report')
    db.store_analysis(owner, private)
    monkeypatch.setattr(sources, 'collect_news', lambda c: {'sources': [], 'warnings': []})
    shared_job = worker.enqueue(public_research.OWNER, 'directory:dbs')
    user_job = worker.enqueue(owner, 'directory:ocbc')
    assert worker.process_one()
    assert worker.job(owner, user_job['id'])['status'] == 'complete'
    assert worker.job(public_research.OWNER, shared_job['id'])['status'] == 'queued'
    assert worker.process_one()
    shared = public_research.latest('directory:dbs')
    assert 'PRIVATE' not in json.dumps(shared)


def test_upload_has_local_facts_and_assistant_can_retrieve_them(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Upload must not call AI')
    monkeypatch.setattr(assistant, 'structured', forbidden)
    response = client.post('/api/reports', headers=headers(client), files={'file': ('report.txt', b'Our operational emissions were 12,345 tCO2e in 2025. We commit to net zero by 2050.', 'text/plain')})
    assert response.status_code == 200
    item = client.get('/api/analyses/' + response.json()['analysis_id']).json()
    assert {f['metric'] for f in item['facts']['items']} == {'emissions', 'net_zero'}
    assert all(f['page'] is None for f in item['facts']['items'])
    assert assistant.retrieve(item, 'What is the net zero target?')


def test_pdf_is_one_page_and_contains_cited_metrics(client):
    item = run_analysis(client)
    item['facts'] = facts.extract([document('In 2025 emissions were 32.5 tCO2e. We commit to net zero by 2050.')], use_ai=False)
    item['knowledge_sources'] = facts.evidence(item['facts'])
    item['brief'] = briefs.generate(item, allow_ai=False)
    pdf = PdfReader(io.BytesIO(company_pdf.render(item)))
    assert len(pdf.pages) == 1
    text = pdf.pages[0].extract_text()
    assert '32.5' in text and '2050' in text and 'p.18' in text
    assert len(pdf.pages[0].get('/Annots', [])) > 0
    response = client.get('/api/analyses/' + item['id'] + '/brief.pdf')
    assert response.status_code == 200 and response.content.startswith(b'%PDF-')


def test_wikidata_prefers_current_claims_and_catalog_has_sti_scope():
    old = {'rank': 'normal', 'qualifiers': {'P582': [{'datavalue': {'value': {'time': '+2020-01-01T00:00:00Z'}}}]}}
    current = {'rank': 'normal'}
    assert profiles.latest([old, current]) == [current]
    assert len(research.CATALOG['companies']) == 47
    assert sum(e['sti'] for e in research.CATALOG['companies'].values()) == 30
    assert all(e['documents'][0]['url'].startswith('https://') for e in research.CATALOG['companies'].values())


def test_generic_venture_headlines_do_not_match_the_listed_manufacturer():
    company = {'name': 'Venture Corporation', 'aliases': []}
    assert not sources.related(company, 'Turning venture-backed innovation into bankable climate infrastructure')
    assert sources.related(company, 'Venture Corporation publishes its sustainability report')
    assert sources.publisher_is_issuer({'name': 'DBS Group Holdings', 'aliases': ['DBS Bank']}, 'DBS Bank Ltd')
    assert not sources.publisher_is_issuer(company, 'Reuters')


def test_uncurated_sec_company_gets_a_sourced_profile_and_annual_ifrs_figures(client, monkeypatch):
    annual = {'start': '2025-01-01', 'end': '2025-12-31', 'filed': '2026-03-01', 'form': '20-F', 'val': 120}
    quarterly = {**annual, 'start': '2025-10-01', 'val': 30}
    fact_data = {'facts': {'ifrs-full': {key: {'units': {'USD': [annual, quarterly]}} for key in ['Revenue', 'ProfitLoss', 'Assets', 'Equity', 'CashAndCashEquivalents']}}}
    def get(url):
        data = fact_data if 'companyfacts' in url else {'name': 'Example Semiconductor', 'sicDescription': 'Semiconductors', 'addresses': {'business': {'city': 'SINGAPORE', 'stateOrCountryDescription': 'SINGAPORE'}}}
        return json.dumps(data).encode()
    monkeypatch.setattr(sources, 'get', get)
    profile = collect_profile({'id': 'sec:0000000999', 'name': 'Example Semiconductor', 'cik': '999', 'ticker': 'EXAMPLE', 'exchange': 'NASDAQ'})
    assert 'semiconductors' in profile['summary']
    assert len(profile['market']) == 5
    assert next(f['value'] for f in profile['market'] if f['label'] == 'Annual revenue') == 120
    assert profile['sources'][0]['publisher'] == 'SEC submissions'
    assert profile['facts'][0]['label'] == 'Business address'


def test_key_comparison_prefers_operational_scopes_and_only_ranks_matching_periods():
    def extract(text):
        return facts.extract([document(text)], use_ai=False)
    first = extract('In 2025 operational Scope 2 market-based emissions were 25,518 tCO2e. In 2025 Scope 3 emissions associated with waste were 375 tCO2e.')
    second = extract('In 2025 operational Scope 2 market-based emissions were 20,000 tCO2e.')
    rows = [{'analysis': {'facts': first}}, {'analysis': {'facts': second}}]
    cells = facts.key_comparison(rows)[0]['cells']
    assert cells[0]['value'] == 25518 and cells[0]['scope'] == '2'
    assert [c['rank'] for c in cells] == ['highest', 'lowest']
    second['items'][0]['period'] = '2024'
    assert all(c['rank'] is None for c in facts.key_comparison(rows)[0]['cells'])


def test_score_driver_quotes_the_contributing_phrase_instead_of_neutral_context():
    source = {'id': 'source', 'title': 'Issuer report', 'excerpt': 'Climate information. We invest in solar energy.',
              'kind': 'disclosure', 'publisher': 'Issuer', 'url': 'https://issuer.example/report.pdf', 'published_at': None, 'page': 4}
    item = analysis.build({'id': 'issuer', 'name': 'Issuer'}, [source])
    driver = briefs.explanations(item)['momentum']['drivers'][0]
    assert driver['quote'] == 'We invest in solar energy.'
    assert driver['page'] == 4 and driver['direction'] == 'raises'


def test_existing_uploads_gain_local_facts_without_reuploading_or_ai(client, monkeypatch):
    response = client.post('/api/reports', headers=headers(client), files={'file': ('legacy.txt', b'We commit to net zero by 2050. Operational emissions were 120 tCO2e in 2025.', 'text/plain')})
    analysis_id = response.json()['analysis_id']
    with db.connect() as con:
        row = con.execute('SELECT owner,payload FROM analyses WHERE id=?', (analysis_id,)).fetchone()
        old = json.loads(row['payload'])
        old.pop('facts')
        old.pop('knowledge_sources')
        con.execute('UPDATE analyses SET payload=? WHERE id=?', (json.dumps(old), analysis_id))
    monkeypatch.setattr(assistant, 'structured', lambda *args: (_ for _ in ()).throw(AssertionError('No AI for existing uploads')))
    item = client.get('/api/analyses/' + analysis_id).json()
    assert {f['metric'] for f in item['facts']['items']} == {'emissions', 'net_zero'}
    assert db.get_analysis(row['owner'], analysis_id)['facts']['version'] == facts.VERSION
