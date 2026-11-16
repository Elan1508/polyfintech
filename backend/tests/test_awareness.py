import csv
import io

import pytest

from app import awareness, db, facts, news, research
from conftest import headers


def csv_bytes(rows, high=True):
    fields = ['year', 'parent_entity', 'total_emissions_MtCO2e', 'commodity', 'production_value', 'production_unit']
    if high:
        fields += list(awareness.CO2_FIELDS)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        values = dict(year='2024', parent_entity='ExxonMobil', total_emissions_MtCO2e='100', commodity='Oil', production_value='20', production_unit='million bbl/yr')
        if high:
            values.update(dict.fromkeys(awareness.CO2_FIELDS, '0'))
            values['product_emissions_MtCO2'] = '90'
        values.update(row)
        writer.writerow(values)
    return out.getvalue().encode('utf8')


def upload(client, content):
    return client.post('/api/emissions/import', headers=headers(client), files={'file': ('official.csv', content, 'text/csv')}, data={'version': 'Test fixture only'})


def test_aggregation_retains_commodity_units_and_complete_co2():
    oil = {'commodity': 'Oil', 'production_value': '20'}
    gas = {'commodity': 'Natural Gas', 'production_value': '40', 'production_unit': 'Bcf/yr'}
    parsed = awareness.parse_csv(csv_bytes([oil, gas, oil]))
    point = parsed['entities']['ExxonMobil'][0]
    assert parsed['row_count'] == 2  # exact duplicate rows do not double count
    assert point['total_mtco2e'] == 200 and point['co2_mt'] == 180
    assert {(p['commodity'], p['unit'], p['value']) for p in point['production']} == {('Oil', 'million bbl/yr', 20), ('Natural Gas', 'Bcf/yr', 40)}
    missing = awareness.parse_csv(csv_bytes([{}, {'commodity': 'Gas', 'flaring_emissions_MtCO2': ''}]))
    assert missing['entities']['ExxonMobil'][0]['co2_mt'] is None


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1,000', '100 Mt'])
def test_invalid_numeric_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        awareness.parse_csv(csv_bytes([{'total_emissions_MtCO2e': value}]))


def test_conflicting_low_granularity_rows_and_partial_schemas_rejected():
    with pytest.raises(ValueError, match='conflicting totals'):
        awareness.parse_csv(b'year,parent_entity,total_emissions_MtCO2e\n2024,Shell,100\n2024,Shell,101\n')
    with pytest.raises(ValueError, match='Production data needs'):
        awareness.parse_csv(b'year,parent_entity,total_emissions_MtCO2e,production_value\n2024,Shell,100,1\n')


def test_import_is_idempotent_atomic_and_private(client):
    content = csv_bytes([{'year': '2020'}, {'year': '2024', 'total_emissions_MtCO2e': '120'}])
    first = upload(client, content)
    assert first.status_code == 200, first.text
    first_id = first.json()['id']
    assert upload(client, content).json()['unchanged'] is True
    assert upload(client, csv_bytes([{'year': '9999'}])).status_code == 422
    assert client.get('/api/emissions').json()['dataset']['id'] == first_id
    view = client.get('/api/companies/directory:exxonmobil/awareness').json()
    assert view['entity'] == 'ExxonMobil' and view['trend']['percent'] == 20
    assert view['country_scale']['year'] == 2024 and view['country_scale']['gas'] == 'CO2'
    assert view['country_scale']['company_mtco2'] == 90
    client.cookies.clear()
    headers(client)
    assert client.get('/api/emissions').json()['dataset'] is None
    assert client.get('/api/companies/directory:exxonmobil/awareness').json()['series'] == []
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM carbon_imports').fetchone()[0] == 1


def test_guest_import_moves_to_account_and_survives_new_session(client):
    assert upload(client, csv_bytes([{}])).status_code == 200
    result = client.post('/api/auth/register', headers=headers(client), json={'email': 'aware@example.com', 'password': 'StrongPassword2026!', 'name': 'Aware'})
    assert result.status_code == 200, result.text
    assert client.get('/api/emissions').json()['dataset']['row_count'] == 1
    with db.connect() as con:
        owner = con.execute('SELECT owner FROM carbon_imports').fetchone()[0]
    assert not owner.startswith('guest:')


def test_csrf_and_mapping_boundary_guards(client):
    headers(client)
    assert client.post('/api/emissions/import', files={'file': ('x.csv', csv_bytes([{}]))}).status_code == 403
    upload(client, csv_bytes([{}]))
    response = client.post('/api/emissions/mapping', headers=headers(client), json={'company_id': 'directory:dbs', 'entity': 'ExxonMobil'})
    assert response.status_code == 422
    response = client.post('/api/emissions/mapping', headers=headers(client), json={'company_id': 'directory:shell', 'entity': 'ExxonMobil'})
    assert response.status_code == 200  # explicit user mapping, prominently labelled as unverified group boundary
    view = client.get('/api/companies/directory:shell/awareness').json()
    assert view['mapping_kind'].startswith('User-selected')


def test_trends_do_not_invent_baselines_or_percent_from_zero():
    series = [{'year': 2019, 'value': 0}, {'year': 2024, 'value': 100}]
    assert awareness.trend(series, 'value', 2020) is None
    assert awareness.trend(series, 'value')['percent'] is None
    assert awareness.country_scale({'year': 2024, 'co2_mt': None}) is None
    assert awareness.country_scale({'year': 2010, 'co2_mt': 100}) is None


def test_comparison_uses_common_year_and_keeps_cross_sector_unranked(client):
    content = csv_bytes([{'year': '2023'}, {'year': '2024'}, {'year': '2023', 'parent_entity': 'Shell', 'total_emissions_MtCO2e': '80'}])
    upload(client, content)
    result = client.post('/api/compare', headers=headers(client), json={'company_ids': ['directory:exxonmobil', 'directory:shell']}).json()
    assert result['same_sector']
    assert result['emissions_metrics'][0]['year'] == 2023
    assert [c['value'] for c in result['emissions_metrics'][0]['cells']] == [100, 80]
    mixed = client.post('/api/compare', headers=headers(client), json={'company_ids': ['directory:exxonmobil', 'directory:dbs']}).json()
    assert mixed['same_sector'] is False and mixed['emissions_metrics'] == []


def test_statuses_do_not_convert_proposals_or_appeals_into_final_findings():
    assert news.reported_status('Company could face fine after lawsuit') == 'Alleged'
    assert news.reported_status('Company fined for pollution') == 'Fined'
    assert news.reported_status('Company appeals pollution penalty') == 'Alleged'
    assert news.reported_status('Regulator opens investigation into Company') == 'Under investigation'
    assert news.reported_status('Company settled pollution lawsuit') == 'Settled'
    assert news.reported_status('Pollution fine overturned by court') == 'Dismissed / overturned'


def test_catalog_covers_awareness_lineup_without_removing_sti():
    catalog = research.CATALOG['companies']
    assert len(catalog) == 47 and sum(bool(c.get('awareness_focus')) for c in catalog.values()) == 23
    assert sum(bool(c.get('sti')) for c in catalog.values()) == 30
    assert all(c.get('wikidata_id') and c['documents'] for c in catalog.values() if c.get('awareness_focus'))
    parsed = facts.parse('Our no-deforestation policy applies across the palm oil supply chain in 2025.')
    assert parsed[0]['metric'] == 'deforestation' and parsed[0]['value'] is None
    assert awareness.company_meta({'id': 'directory:dbs', 'demo_key': 'dbs', 'country': 'Singapore'})['region_group'] == 'ASEAN'
    intensity = facts.parse('In 2025 our steel production had an intensity of 1.79 tCO2e/tCS.')
    assert intensity[0]['metric'] == 'emissions_intensity' and all(f['metric'] != 'emissions' for f in intensity)
    tagged = news.tag({'kind': 'news', 'title': 'Regulator investigates Company over pollution', 'excerpt': '', 'self_reported': False})
    assert tagged['controversy'] and tagged['case_status'] == 'Under investigation'
    assert not any(f['metric'] == 'renewable' for f in facts.parse('We sell fuel blends with up to 100% renewable diesel in a dozen countries.'))
    assert not any(f['metric'] == 'net_zero' for f in facts.parse('Under MIT’s Net Zero by 2050 scenario, achieving net zero would cost more without hydrogen.'))
    baseline = facts.parse('In 2025 our Scope 1 and 2 emissions were 53 million tonnes of CO2e, reflecting a reduction against the base year for our target to halve emissions by 2030.')
    assert baseline[0]['status'] == 'reported' and baseline[0]['value'] == 53_000_000
    target = facts.parse('Our emissions target was 10 tCO2e by 2030.')
    assert target[0]['status'] == 'target'
    table = facts.parse('Interim target 2016 2023 2024 2025 2030 2050 83 million tonnes CO2e 41 million tonnes CO2e Baseline Actual Target.')
    assert table[0]['review_required'] and table[0]['value'] is None
