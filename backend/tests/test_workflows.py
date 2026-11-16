import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import analysis, assistant, auth, config, db, reports, sources, worker
from app.main import app
from conftest import headers, run_analysis


def register(client, email='researcher@example.com'):
    return client.post('/api/auth/register', headers=headers(client), json={'email': email, 'name': 'Researcher', 'password': 'a long test password 2026'})


def test_verified_session_and_csrf(client):
    assert client.post('/api/analyses', json={'company_id': 'directory:dbs'}).status_code == 401
    response = client.get('/api/session')
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
    assert client.post('/api/watchlist', json={'company_id': 'directory:dbs'}).status_code == 403
    assert client.post('/api/watchlist', headers={**headers(client), 'Origin': 'https://evil.example'}, json={'company_id': 'directory:dbs'}).status_code == 403


def test_password_hashing_and_login(client):
    response = register(client)
    assert response.status_code == 200
    with db.connect() as con:
        stored = con.execute('SELECT password_hash FROM users').fetchone()[0]
    assert 'a long test password' not in stored
    assert auth.check_password('a long test password 2026', stored)
    assert not auth.check_password('different', stored)
    assert client.post('/api/auth/logout', headers=headers(client)).status_code == 200
    assert client.get('/api/session').json()['user'] is None
    assert client.post('/api/auth/login', headers=headers(client), json={'email': 'researcher@example.com', 'password': 'wrong password here'}).status_code == 401
    assert client.post('/api/auth/login', headers=headers(client), json={'email': 'researcher@example.com', 'password': 'a long test password 2026'}).status_code == 200


def test_guest_research_migrates_and_persists(client):
    item = run_analysis(client)
    assert client.patch('/api/analyses/' + item['id'], headers=headers(client), json={'saved': True}).status_code == 200
    assert client.post('/api/watchlist', headers=headers(client), json={'company_id': item['company']['id']}).status_code == 200
    assert register(client).status_code == 200
    assert client.get('/api/analyses/' + item['id']).json()['saved'] is True
    assert len(client.get('/api/watchlist').json()) == 1
    assert client.post('/api/auth/logout', headers=headers(client)).status_code == 200
    assert client.get('/api/analyses/' + item['id']).status_code == 404
    assert not client.get('/api/watchlist').json()
    login = client.post('/api/auth/login', headers=headers(client), json={'email': 'researcher@example.com', 'password': 'a long test password 2026'})
    assert login.status_code == 200
    assert client.get('/api/analyses/' + item['id']).json()['saved'] is True


def test_scores_match_investigation_compare_and_watchlist(client, monkeypatch):
    monkeypatch.setattr(sources, 'collect_news', lambda company: {'sources': sources.demo_sources(company), 'warnings': [], 'cached': False})
    first = run_analysis(client, mode='live')
    second = run_analysis(client, company='directory:grab', mode='live')
    assert client.post('/api/watchlist', headers=headers(client), json={'company_id': first['company']['id']}).status_code == 200
    watch = client.get('/api/watchlist').json()[0]
    compared = client.post('/api/compare', headers=headers(client), json={'company_ids': [first['company']['id'], second['company']['id']]}).json()
    assert watch['analysis']['scores'] == first['scores']
    assert compared['rows'][0]['analysis']['scores'] == first['scores']
    assert compared['rows'][0]['analysis']['id'] == first['id']
    assert compared['rows'][0]['analysis']['dimensions'] == first['dimensions']
    assert client.post('/api/watchlist/' + first['company']['id'] + '/seen', headers=headers(client)).status_code == 200
    assert not client.get('/api/watchlist').json()[0]['unread']
    refreshed = run_analysis(client, mode='live', refresh=True)
    assert refreshed['id'] != first['id']
    history = client.get('/api/companies/' + first['company']['id'] + '/history').json()
    assert len(history) == 2
    assert all(item['mode'] == 'live' for item in history)


def test_dynamic_search_imports_new_companies(client, monkeypatch):
    foreign = {'id': 'lei:NEW', 'name': 'New Research Industries', 'ticker': '', 'exchange': 'Legal entity', 'country': 'SG', 'sector': 'Not classified', 'aliases': [], 'identity_source': 'GLEIF', 'identity_url': ''}
    monkeypatch.setattr(sources, 'gleif_search', lambda query: [foreign])
    monkeypatch.setattr(sources, 'sec_search', lambda query: [])
    headers(client)
    result = client.get('/api/companies?q=New%20Research').json()
    assert any(c['id'] == foreign['id'] for c in result['companies'])
    assert db.company(foreign['id'])['name'] == foreign['name']
    monkeypatch.setattr(sources, 'collect_news', lambda company: {'sources': [], 'warnings': ['No sources'], 'cached': False})
    item = run_analysis(client, company=foreign['id'], mode='live')
    assert item['company']['id'] == foreign['id']
    assert item['scores']['momentum']['score'] is None
    assert item['scores']['risk']['label'] == 'Unassessed'
    assert client.post('/api/analyses', headers=headers(client), json={'company_id': foreign['id'], 'mode': 'demo'}).status_code == 422


def test_search_deduplicates_exchange_case_and_aliases(client, monkeypatch):
    duplicate = {'id': 'sec:new-grab', 'name': 'Grab Holdings Ltd', 'ticker': 'GRAB', 'exchange': 'Nasdaq', 'country': 'US filing', 'sector': 'Not classified', 'aliases': ['GRAB HOLDINGS LTD'], 'identity_source': 'SEC', 'identity_url': ''}
    monkeypatch.setattr(sources, 'sec_search', lambda query: [duplicate])
    monkeypatch.setattr(sources, 'gleif_search', lambda query: [])
    headers(client)
    result = client.get('/api/companies?q=Grab').json()
    assert len([c for c in result['companies'] if c.get('ticker') == 'GRAB']) == 1
    assert result['companies'][0]['id'] == 'directory:grab'


def test_source_failures_and_unknown_names_never_fabricate(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('network down')
    monkeypatch.setattr(sources, 'get', unavailable)
    evidence = sources.collect_news(db.company('directory:dbs'))
    assert not evidence['sources'] and evidence['warnings']
    headers(client)
    assert client.post('/api/analyses', headers=headers(client), json={'company_id': 'unverified invented name'}).status_code == 404
    result = client.get('/api/companies?q=unmatched').json()
    assert len(result['warnings']) == 2
    assert result['companies'] == []


def pdf_bytes():
    writer = PdfWriter()
    for text in ['Renewable energy and carbon reduction support our climate programme.', 'AI governance and data protection policies include responsible AI controls.']:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(f'BT /F1 12 Tf 50 700 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_pages_citations_and_account_isolation(client, monkeypatch):
    response = client.post('/api/reports', headers=headers(client), files={'file': ('sustainability.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 200, response.text
    item = client.get('/api/analyses/' + response.json()['analysis_id']).json()
    assert item['mode'] == 'report'
    assert [s['page'] for s in item['sources']] == [1, 2]
    report_id = item['report_id']
    assert client.get(f'/api/reports/{report_id}').json()['pages'][1]['page'] == 2
    assert client.get(f'/api/reports/{report_id}/file').content.startswith(b'%PDF')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    answer = client.post('/api/assistant', headers=headers(client), json={'analysis_id': item['id'], 'question': 'What supports AI governance?'}).json()
    assert answer['mode'] == 'evidence'
    assert any(c['page'] == 2 for c in answer['citations'])
    assert all(c['quote'] in next(s['excerpt'] for s in item['sources'] if s['id'] == c['source_id']) for c in answer['citations'])
    with TestClient(app) as other:
        other_headers = headers(other)
        assert other.get('/api/analyses/' + item['id']).status_code == 404
        assert other.get(f'/api/reports/{report_id}').status_code == 404
        assert other.get(f'/api/reports/{report_id}/file').status_code == 404
        assert other.patch('/api/analyses/' + item['id'], headers=other_headers, json={'saved': True}).status_code == 404
        assert other.post('/api/assistant', headers=other_headers, json={'analysis_id': item['id'], 'question': 'Summarise this report'}).status_code == 404


def test_upload_validations(client):
    assert client.post('/api/reports', headers=headers(client), files={'file': ('evil.exe', b'hello', 'application/octet-stream')}).status_code == 415
    assert client.post('/api/reports', headers=headers(client), files={'file': ('empty.pdf', b'%PDF-invalid', 'application/pdf')}).status_code == 422
    assert client.post('/api/reports', headers=headers(client), files={'file': ('notes.txt', b'abc', 'text/plain')}).status_code == 422
    assert client.post('/api/reports', headers=headers(client), files={'file': ('huge.txt', b'x' * (config.MAX_UPLOAD + 1), 'text/plain')}).status_code == 413


def test_scoring_recency_negation_and_missing_data():
    company = {'id': 'test', 'name': 'Test'}
    base = {'id': 's', 'title': 'Research update', 'excerpt': 'No data breach occurred. Renewable energy investment increased.', 'publisher': 'Primary', 'kind': 'news', 'url': '', 'page': None, 'report_id': None, 'collected_at': db.now(), 'published_at': db.now()}
    current = analysis.build(company, [base])
    old = analysis.build(company, [{**base, 'published_at': (datetime.now(timezone.utc) - timedelta(days=600)).isoformat()}])
    assert current['scores']['risk']['score'] is None
    assert current['scores']['momentum']['score'] > old['scores']['momentum']['score']
    assert current['dimensions']['S']['score'] is None
    assert analysis.changes(current, {**old, 'scoring_version': 'new'})['score_changes'] == {}


def test_watchlist_folders_and_refresh_jobs(client):
    assert register(client).status_code == 200
    for name in ['directory:dbs', 'directory:grab']:
        assert client.post('/api/watchlist', headers=headers(client), json={'company_id': name, 'folder': 'Banks'}).status_code == 200
    assert client.patch('/api/watchlist/directory:grab', headers=headers(client), json={'folder': 'Technology'}).status_code == 200
    assert {w['folder'] for w in client.get('/api/watchlist').json()} == {'Banks', 'Technology'}
    jobs = client.post('/api/watchlist/refresh', headers=headers(client)).json()['jobs']
    assert len(jobs) == 2
    repeated = client.post('/api/watchlist/refresh', headers=headers(client)).json()['jobs']
    assert {j['id'] for j in jobs} == {j['id'] for j in repeated}


def test_ai_rejects_invented_citations(monkeypatch):
    source = {'id': 's1', 'title': 'Climate report', 'excerpt': 'Renewable energy investments increased during the year.', 'publisher': 'Report', 'kind': 'report', 'page': 1, 'report_id': 'r', 'url': '/api/reports/r/file', 'published_at': None, 'collected_at': db.now()}
    item = analysis.build({'id': 'c', 'name': 'Company'}, [source])
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text=json.dumps({'answer': 'Invented', 'citations': [{'source_id': 'fake', 'quote': 'Invented quote'}]}))))
    monkeypatch.setattr(assistant, 'OpenAI', lambda **kwargs: fake)
    response = assistant.answer(item, 'What renewable investments are described?')
    assert response['mode'] == 'evidence'
    assert 'unverifiable' in response['notice']
    fake.responses.create = lambda **kwargs: SimpleNamespace(output_text=json.dumps({'answer': 'Investments increased.', 'citations': [{'source_id': 's1', 'quote': source['excerpt']}]}))
    response = assistant.answer(item, 'What renewable investments are described?')
    assert response['mode'] == 'ai' and response['citations'][0]['page'] == 1


def test_unanswerable_questions_do_not_get_generic_claims(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    item = analysis.build({'id': 'c', 'name': 'Company'}, [])
    assert assistant.answer(item, 'What is the CEO shoe size?')['citations'] == []


def test_report_terms_do_not_multiply_with_repeated_pages():
    source = {'id': 'p1', 'title': 'Page 1', 'excerpt': 'Renewable energy and solar programmes. A data breach occurred.', 'publisher': 'Report', 'kind': 'report', 'page': 1, 'report_id': 'same', 'url': '', 'published_at': None, 'collected_at': db.now()}
    single = analysis.build({'id': 'c', 'name': 'Company'}, [source])
    repeated = analysis.build({'id': 'c', 'name': 'Company'}, [source, {**source, 'id': 'p2', 'page': 2}])
    assert single['scores'] == repeated['scores']
    assert single['dimensions']['E']['score'] == repeated['dimensions']['E']['score']


def test_linked_reports_enter_only_owners_live_analysis(client, monkeypatch):
    monkeypatch.setattr(sources, 'collect_news', lambda company: {'sources': [], 'warnings': [], 'cached': False})
    old = run_analysis(client, mode='live')
    uploaded = client.post('/api/reports', headers=headers(client), data={'company_id': 'directory:dbs'}, files={'file': ('notes.txt', b'Renewable energy and solar projects support carbon reduction. Responsible AI governance and data protection controls are in place.', 'text/plain')})
    assert uploaded.status_code == 200
    fresh = run_analysis(client, mode='live')
    assert fresh['id'] != old['id']
    assert fresh['sources'] and all(s['report_id'] for s in fresh['sources'])
    with TestClient(app) as other:
        independent = run_analysis(other, mode='live')
        assert independent['sources'] == []


def test_docx_sections_and_tables_are_extracted():
    from docx import Document
    doc = Document()
    doc.add_paragraph('Responsible AI governance supports data protection and cybersecurity controls.')
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = 'Renewable energy'
    table.cell(0, 1).text = 'Solar investment'
    content = io.BytesIO()
    doc.save(content)
    pages, warnings, extension = reports.extract('review.docx', content.getvalue())
    assert extension == 'docx' and pages[0]['page'] is None
    assert 'Solar investment' in pages[0]['text']
    assert any('pagination' in w for w in warnings)


def test_scheduled_refresh_is_due_for_accounts_only(client):
    assert register(client).status_code == 200
    client.post('/api/watchlist', headers=headers(client), json={'company_id': 'directory:dbs'})
    due = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with db.connect() as con:
        con.execute('UPDATE watchlist SET created_at=?', (due,))
    with TestClient(app) as guest:
        guest.post('/api/watchlist', headers=headers(guest), json={'company_id': 'directory:grab'})
        with db.connect() as con:
            con.execute("UPDATE watchlist SET created_at=? WHERE company_id='directory:grab'", (due,))
        worker.schedule()
    with db.connect() as con:
        queued = con.execute('SELECT company_id FROM jobs').fetchall()
    assert [row['company_id'] for row in queued] == ['directory:dbs']


def test_library_paginates_all_saved_records_and_is_private(client):
    for _ in range(3):
        item = run_analysis(client, refresh=True)
        client.patch('/api/analyses/' + item['id'], headers=headers(client), json={'saved': True})
    first = client.get('/api/library?limit=2').json()
    assert first['total'] == 3 and first['has_more'] and len(first['items']) == 2
    second = client.get('/api/library?limit=2&offset=2').json()
    assert len(second['items']) == 1 and not second['has_more']
    assert client.get('/api/stats').json()['saved'] == 3
    with TestClient(app) as other:
        headers(other)
        assert other.get('/api/library').json()['total'] == 0


def test_signing_up_during_background_analysis_keeps_ownership(client, monkeypatch):
    def collect(company):
        assert register(client).status_code == 200
        return {'sources': [], 'warnings': [], 'cached': False}
    monkeypatch.setattr(sources, 'collect_news', collect)
    item = run_analysis(client, mode='live')
    assert client.get('/api/session').json()['user'] is not None
    assert client.get('/api/analyses/' + item['id']).status_code == 200


def test_signing_up_during_report_extraction_keeps_ownership(client, monkeypatch):
    original = reports.extract
    def extract(filename, content):
        assert register(client).status_code == 200
        return original(filename, content)
    monkeypatch.setattr(reports, 'extract', extract)
    uploaded = client.post('/api/reports', headers=headers(client), files={'file': ('notes.txt', b'Renewable energy and solar investments support carbon reduction and data protection controls.', 'text/plain')})
    assert uploaded.status_code == 200
    item = client.get('/api/analyses/' + uploaded.json()['analysis_id'])
    assert item.status_code == 200
    assert client.get('/api/reports/' + item.json()['report_id']).status_code == 200
