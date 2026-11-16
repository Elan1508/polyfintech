import importlib.util
from pathlib import Path

from app import analysis, config, db, sources, workspace
from conftest import headers


def owner_for(client):
    headers(client)
    with db.connect() as con:
        return con.execute('SELECT owner FROM sessions ORDER BY rowid DESC LIMIT 1').fetchone()['owner']


def save(owner, company_id, score, stamp, mode='demo', version=None, sector='Banks'):
    company = {**db.company(company_id), 'sector': sector}
    item = analysis.build(company, sources.demo_sources(db.company('directory:dbs')), mode=mode)
    item['scores']['momentum']['score'] = score
    item['created_at'] = stamp
    if version:
        item['scoring_version'] = version
    db.store_analysis(owner, item)
    return item


def test_search_scores_are_latest_and_private(client):
    owner = owner_for(client)
    save(owner, 'directory:dbs', 20, '2026-11-01T00:00:00+00:00', mode='live')
    newest = save(owner, 'directory:dbs', 53, '2026-11-02T00:00:00+00:00', mode='live')
    save('guest:other', 'directory:dbs', 99, '2026-11-03T00:00:00+00:00', mode='live')
    save('guest:other', 'directory:ocbc', 88, '2026-11-03T00:00:00+00:00', mode='live')
    companies = {row['id']: row for row in client.get('/api/companies?listed_only=true').json()['companies']}
    assert companies['directory:dbs']['analysis']['id'] == newest['id']
    assert companies['directory:dbs']['analysis']['scores']['momentum']['score'] == 53
    assert companies['directory:ocbc']['analysis'] is None
    assert 'sources' not in companies['directory:dbs']['analysis']


def test_peer_context_uses_unique_private_dated_comparable_companies(client):
    owner = owner_for(client)
    save(owner, 'directory:ocbc', 10, '2026-11-10T00:00:00+00:00')
    save(owner, 'directory:ocbc', 20, '2026-11-14T00:00:00+00:00')
    save(owner, 'directory:uob', 80, '2026-11-14T00:00:00+00:00')
    save(owner, 'directory:uob', 99, '2026-11-16T00:00:00+00:00')  # Future to selected analysis.
    save('guest:other', 'directory:aia', 0, '2026-11-14T00:00:00+00:00')
    save(owner, 'directory:keppel', 0, '2026-07-01T00:00:00+00:00')  # Too old.
    save(owner, 'directory:sea', 0, '2026-11-14T00:00:00+00:00', sector='Technology')
    save(owner, 'directory:singtel', 0, '2026-11-14T00:00:00+00:00', mode='live')
    current = save(owner, 'directory:dbs', 60, '2026-11-15T00:00:00+00:00')
    result = client.get('/api/analyses/' + current['id']).json()['context']['peers']['metrics']['momentum']
    assert result == {'available': True, 'peer_count': 2, 'sample_size': 3, 'median': 60, 'percentile': 50}


def test_peer_context_refuses_small_or_incomparable_samples(client):
    owner = owner_for(client)
    save(owner, 'directory:ocbc', 20, '2026-11-14T00:00:00+00:00')
    save(owner, 'directory:uob', 80, '2026-11-14T00:00:00+00:00', version='other-method')
    current = save(owner, 'directory:dbs', 60, '2026-11-15T00:00:00+00:00')
    metric = workspace.comparison_context(owner, current)['peers']['metrics']['momentum']
    assert metric['available'] is False and metric['median'] is None
    assert metric['peer_count'] == 1
    current['coverage']['status'] = 'Limited evidence'
    assert workspace.comparison_context(owner, current)['peers']['metrics'] == {}
    current['kind'] = 'report'
    assert workspace.comparison_context(owner, current)['trend'] == []


def test_trends_and_deltas_use_observed_dates_and_keep_versions(client):
    owner = owner_for(client)
    first = save(owner, 'directory:dbs', 40, '2026-11-01T00:00:00+00:00')
    current = save(owner, 'directory:dbs', 52, '2026-11-11T00:00:00+00:00')
    context = workspace.comparison_context(owner, current)
    assert [r['id'] for r in context['trend']] == [first['id'], current['id']]
    assert context['score_changes']['momentum'] == 12
    assert context['previous']['created_at'] == first['created_at']
    different = save(owner, 'directory:dbs', 80, '2026-11-12T00:00:00+00:00', version='new-method')
    context = workspace.comparison_context(owner, different)
    assert context['method_changed'] is True and context['score_changes'] == {}
    assert {r['scoring_version'] for r in context['trend']} == {first['scoring_version'], 'new-method'}


def test_risk_signal_counts_do_not_invent_scores_or_duplicate_report_terms():
    company = {'id': 'test', 'name': 'Example'}
    evidence = [{'id': f'page-{i}', 'title': 'Annual report', 'excerpt': 'A data breach and regulatory fine were reported.',
                 'publisher': 'Issuer', 'kind': 'disclosure', 'published_at': None, 'evidence_group': 'one-report'} for i in range(12)]
    item = analysis.build(company, evidence)
    assert analysis.risk_flag_count(item) == 2
    clean = analysis.build(company, [{**evidence[0], 'excerpt': 'No data breach was recorded. Our renewable energy programme continues.'}])
    assert analysis.risk_flag_count(clean) == 0
    assert clean['scores']['risk']['score'] is None
    assert analysis.risk_flag_count(analysis.build(company, [])) == 0


def test_source_package_excludes_private_and_generated_files():
    spec = importlib.util.spec_from_file_location('package_source', config.BACKEND.parent / 'scripts/package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ['frontend/node_modules/react/index.js', 'backend/.venv/pyvenv.cfg', 'frontend/dist/index.html',
                 'backend/runtime/reports/private.pdf', '.env', 'frontend/.env.local', 'data.sqlite3',
                 'backend/__pycache__/app.pyc', 'private.pem', 'artifacts/source.zip']:
        assert not module.included(name), name
    for name in ['backend/app/data/research_catalog.json', 'frontend/src/App.jsx', 'package.json', '.gitignore']:
        assert module.included(name), name
