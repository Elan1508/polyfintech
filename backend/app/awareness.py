"""Private Carbon Majors imports and explicitly bounded climate comparisons.

No licensed emissions rows enter shared analyses, caches or public seed files.
Country totals are an attributed, versioned Climate TRACE CO2 snapshot.
"""
import csv
import hashlib
import io
import json
import math
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from . import config, db, facts, research

DOWNLOADS = 'https://carbonmajors.org/Downloads'
METHOD = 'https://carbonmajors.org/Methodology'
TERMS = 'https://influencemap.org/terms'
MAX_BYTES = 30 * 1024 * 1024
CO2_FIELDS = ('product_emissions_MtCO2', 'flaring_emissions_MtCO2',
              'venting_emissions_MtCO2', 'own_fuel_use_emissions_MtCO2')
BOUNDARY = ('Carbon Majors attributes production-linked operational emissions and downstream combustion '
            'to fossil-fuel and cement producers. It covers parts of Scope 1 and Scope 3, not a full '
            'corporate inventory or Scope 2. Historical emissions can be reassigned to surviving parents. '
            'Estimates are not equivalent to company-reported operational emissions.')
SECTOR_METRICS = {
    'Oil & gas': [('Production', r'production|barrels|\bbbl\b'), ('Low-carbon investment', r'low.carbon|low.emission|transition investment'), ('Absolute emissions', r'emission')],
    'Mining': [('Coal production', r'coal|production'), ('Safety and tailings', r'injur|fatalit|tailing'), ('Absolute emissions', r'emission')],
    'Cement & steel': [('Process emissions', r'process emission|clinker|steel|cement'), ('Energy transition', r'renewable|low.carbon'), ('Absolute emissions', r'emission')],
    'Food & agriculture': [('Deforestation commitments', r'deforestation|\bndpe\b'), ('Traceability', r'traceab|certif'), ('Supply-chain emissions', r'scope 3|supply.chain|emission')],
    'Banking': [('Financed emissions', r'financed emission'), ('Portfolio transition', r'financ|portfolio'), ('Operational emissions', r'emission')],
    'Energy & infrastructure': [('Power generation mix', r'coal|renewable|capacity'), ('Absolute emissions', r'emission'), ('Safety', r'injur|fatalit')],
    'Transport': [('Fuel and fleet transition', r'fuel|fleet|electric'), ('Emissions intensity', r'intensity|emission'), ('Safety', r'injur|fatalit|safety')],
    'Technology': [('Energy and emissions', r'energy|renewable|emission'), ('Platform and data safeguards', r'privacy|data|cyber|safety'), ('Workforce', r'board|women|employee|labour|labor')],
}


def init(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS carbon_imports (
      id TEXT PRIMARY KEY, owner TEXT NOT NULL, digest TEXT NOT NULL,
      filename TEXT NOT NULL, version TEXT NOT NULL, created_at TEXT NOT NULL,
      granularity TEXT NOT NULL, row_count INTEGER NOT NULL, payload TEXT NOT NULL,
      UNIQUE(owner,digest));
    CREATE INDEX IF NOT EXISTS carbon_owner ON carbon_imports(owner,created_at DESC);
    CREATE TABLE IF NOT EXISTS carbon_mappings (
      owner TEXT NOT NULL, company_id TEXT NOT NULL, entity TEXT NOT NULL,
      PRIMARY KEY(owner,company_id));
    ''')


def group(company):
    entry = research.entry_for(company) or {}
    return entry.get('sector_group') or company.get('sector') or 'Not classified'


def company_meta(company):
    entry = research.entry_for(company) or {}
    asean = company.get('country') in ('SG', 'TH', 'MY', 'ID', 'VN', 'PH', 'BN', 'KH', 'LA', 'MM',
                                     'Singapore', 'Thailand', 'Malaysia', 'Indonesia', 'Vietnam', 'Philippines')
    return {**company, 'sector_group': group(company), 'awareness_focus': entry.get('awareness_focus', False),
            'carbon_producer': bool(entry.get('carbon_majors_names')),
            'region_group': 'ASEAN' if asean else 'Global benchmark'}


def number(value, field, line, required=False):
    value = (value or '').strip()
    if not value:
        if required:
            raise ValueError(f'Row {line}: {field} is required.')
        return None
    try:
        result = float(value)
    except ValueError:
        raise ValueError(f'Row {line}: {field} must be a number without unit labels.') from None
    if not math.isfinite(result) or result < 0 or result > 1e12:
        raise ValueError(f'Row {line}: {field} must be a finite, non-negative number.')
    return result


def parse_csv(content):
    if len(content) > MAX_BYTES:
        raise ValueError('Choose a CSV smaller than 30 MB.')
    try:
        reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not {'year', 'parent_entity', 'total_emissions_MtCO2e'} <= set(headers):
            raise ValueError('Use an official Carbon Majors CSV with year, parent_entity and total_emissions_MtCO2e columns.')
        production = {'commodity', 'production_value', 'production_unit'} <= set(headers)
        detailed = all(field in headers for field in CO2_FIELDS)
        if any(field in headers for field in ('commodity', 'production_value', 'production_unit')) and not production:
            raise ValueError('Production data needs commodity, production_value and production_unit together.')
        annual, products, seen = {}, defaultdict(float), set()
        count = 0
        for line, row in enumerate(reader, 2):
            if line > 200001:
                raise ValueError('The CSV exceeds 200,000 rows.')
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Row {line}: column count does not match the header.')
            signature = tuple(row.get(h, '').strip() for h in headers)
            if signature in seen:
                continue
            seen.add(signature)
            name = row['parent_entity'].strip()
            year_text = row['year'].strip()
            if not name or len(name) > 180 or not re.fullmatch(r'\d{4}', year_text):
                raise ValueError(f'Row {line}: a valid parent entity and four-digit year are required.')
            year = int(year_text)
            if not 1750 <= year <= datetime.now(timezone.utc).year:
                raise ValueError(f'Row {line}: year is outside the supported range.')
            key = (name, year)
            if not production and key in annual:
                raise ValueError(f'Row {line}: conflicting totals for {name} in {year}. Import one granularity at a time.')
            point = annual.setdefault(key, {'year': year, 'total_mtco2e': 0, 'co2_mt': 0, 'co2_complete': detailed})
            point['total_mtco2e'] += number(row['total_emissions_MtCO2e'], 'total emissions', line, True)
            if detailed:
                co2 = [number(row[field], field, line) for field in CO2_FIELDS]
                point['co2_complete'] = point['co2_complete'] and all(v is not None for v in co2)
                point['co2_mt'] += sum(v for v in co2 if v is not None)
            if production:
                value = number(row['production_value'], 'production_value', line)
                commodity, unit = row['commodity'].strip(), row['production_unit'].strip()
                if value is not None:
                    if not commodity or not unit or len(commodity) > 120 or len(unit) > 120:
                        raise ValueError(f'Row {line}: production needs a commodity and unit.')
                    products[(name, year, commodity, unit)] += value
            count += 1
        if not count:
            raise ValueError('The CSV contains no data rows.')
    except UnicodeDecodeError:
        raise ValueError('Save the official CSV as UTF-8 before importing it.') from None
    except csv.Error:
        raise ValueError('The CSV could not be read. Check its quoting and column layout.') from None
    by_year = defaultdict(list)
    for (name, year, commodity, unit), value in products.items():
        by_year[(name, year)].append({'commodity': commodity, 'unit': unit, 'value': value})
    entities = {}
    for (name, year), point in sorted(annual.items()):
        if not point.pop('co2_complete'):
            point['co2_mt'] = None
        point['production'] = by_year[(name, year)]
        entities.setdefault(name, []).append(point)
    return {'entities': entities, 'row_count': count, 'granularity': 'high' if detailed else 'medium' if production else 'low'}


def import_csv(owner, content, filename, version):
    digest = hashlib.sha256(content).hexdigest()
    owner = db.current_owner(owner)
    with db.connect() as con:
        existing = con.execute('SELECT id FROM carbon_imports WHERE owner=? AND digest=?', (owner, digest)).fetchone()
    if existing:
        return {'id': existing['id'], 'unchanged': True, **workspace(owner)}
    data = parse_csv(content)
    import_id = uuid.uuid4().hex
    with db.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        owner = db.resolve_owner(owner, con)
        # Recheck inside the write transaction: duplicate simultaneous imports are idempotent.
        existing = con.execute('SELECT id FROM carbon_imports WHERE owner=? AND digest=?', (owner, digest)).fetchone()
        if not existing:
            con.execute('INSERT INTO carbon_imports VALUES (?,?,?,?,?,?,?,?,?)',
                        (import_id, owner, digest, filename, version.strip()[:100], db.now(), data['granularity'], data['row_count'], json.dumps(data)))
    return {'id': existing['id'] if existing else import_id, 'unchanged': bool(existing), **workspace(owner)}


def active(owner):
    with db.connect() as con:
        row = con.execute('SELECT * FROM carbon_imports WHERE owner=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (owner,)).fetchone()
    return dict(row) if row else None


def workspace(owner):
    row = active(owner)
    with db.connect() as con:
        mappings = dict(con.execute('SELECT company_id,entity FROM carbon_mappings WHERE owner=?', (owner,)).fetchall())
    if not row:
        return {'dataset': None, 'entities': [], 'mappings': mappings}
    data = json.loads(row.pop('payload'))
    years = [p['year'] for series in data['entities'].values() for p in series]
    row.pop('owner')
    return {'dataset': {**row, 'first_year': min(years), 'last_year': max(years), 'entity_count': len(data['entities']),
                        'source_url': DOWNLOADS, 'attribution': 'InfluenceMap / Carbon Majors', 'license_url': TERMS},
            'entities': sorted(data['entities']), 'mappings': mappings}


def set_mapping(owner, company_id, entity):
    row = active(owner)
    if not row or entity not in json.loads(row['payload'])['entities']:
        raise ValueError('Choose an entity in your latest imported dataset.')
    company = db.company(company_id)
    if not company or not (research.entry_for(company) or {}).get('carbon_majors_names'):
        raise ValueError('Manual mappings are supported for reviewed producer companies only.')
    with db.connect() as con:
        con.execute('INSERT INTO carbon_mappings VALUES (?,?,?) ON CONFLICT(owner,company_id) DO UPDATE SET entity=excluded.entity', (owner, company_id, entity))


def trend(series, field, baseline=None):
    points = [p for p in series if p.get(field) is not None]
    if len(points) < 2:
        return None
    last = points[-1]
    first = next((p for p in points if p['year'] == baseline), None) if baseline else next((p for p in points if p['year'] == 2020 and p['year'] < last['year']), points[0])
    if not first or first['year'] >= last['year']:
        return None
    delta = last[field] - first[field]
    pct = delta / first[field] * 100 if first[field] else None
    return {'from_year': first['year'], 'to_year': last['year'], 'from_value': first[field], 'to_value': last[field],
            'change': delta, 'percent': pct, 'direction': 'up' if delta > 0 else 'down' if delta < 0 else 'unchanged'}


def country_scale(point):
    path = config.BACKEND / 'app/data/climate_trace_countries.json'
    if point.get('co2_mt') is None or point['co2_mt'] <= 0 or not path.is_file():
        return None
    data = json.loads(path.read_text(encoding='utf8'))
    year = data['years'].get(str(point['year']))
    if not year:
        return None
    candidates = [c for c in year['countries'] if c['emissionsQuantity'] > 0]
    closest = min(candidates, key=lambda c: abs(math.log(point['co2_mt'] * 1e6 / c['emissionsQuantity']))) if candidates else None
    if not closest:
        return None
    return {**closest, 'year': point['year'], 'company_mtco2': point['co2_mt'], 'country_mtco2': closest['emissionsQuantity'] / 1e6,
            'ratio': point['co2_mt'] * 1e6 / closest['emissionsQuantity'], 'source_url': year['url'],
            'version': data['metadata']['dataVersion'], 'fetched_at': data['fetched_at'], 'attribution': data['attribution'],
            'license_url': data['license_url'], 'gas': 'CO2', 'sector_boundary': data['sector_boundary'],
            'notice': 'Scale illustration only: producer-attributed CO2 (including downstream combustion worldwide) and territorial country CO2 excluding forestry and land use have different boundaries and may overlap. Do not add these totals. This is not a like-for-like footprint comparison.'}


def view(owner, company, analysis=None, baseline=None):
    entry = research.entry_for(company) or {}
    sector = group(company)
    items = [f for f in facts.recheck((analysis or {}).get('facts', {})).get('items', []) if not f.get('review_required')]
    allowed = {'Production': {'production'}, 'Coal production': {'production'}, 'Low-carbon investment': {'low_carbon_investment'},
               'Absolute emissions': {'emissions'}, 'Operational emissions': {'emissions'}, 'Financed emissions': {'emissions'},
               'Deforestation commitments': {'deforestation'}, 'Traceability': {'traceability'}, 'Supply-chain emissions': {'emissions'},
               'Emissions intensity': {'emissions_intensity'}, 'Power generation mix': {'renewable', 'commitment'},
               'Energy and emissions': {'emissions', 'renewable', 'emissions_intensity'}}
    metrics = [{'label': label, 'facts': [f for f in items if f['metric'] in allowed.get(label, {f['metric']})
                                       and re.search(pattern, f.get('quote', ''), re.I)
                                       and (label != 'Absolute emissions' or f['status'] == 'reported')
                                       and (label != 'Operational emissions' or f.get('boundary') == 'operational')][:3]}
               for label, pattern in SECTOR_METRICS.get(sector, [('Absolute emissions', r'emission'), ('Workforce and safety', r'board|injur')])]
    result = {'sector_group': sector, 'metrics': metrics, 'series': [], 'production': [], 'trend': None,
              'country_scale': None, 'dataset': None, 'entity': None, 'applicable': bool(entry.get('carbon_majors_names')),
              'source_url': DOWNLOADS, 'methodology_url': METHOD, 'boundary': BOUNDARY,
              'notice': 'Language indicators describe collected wording, not environmental performance or investment quality.'}
    if (analysis or {}).get('mode') == 'demo':
        result['notice'] = 'Sample analysis: live emissions imports are excluded from demo views.'
        return result
    row = active(owner)
    if not row:
        return result
    data = json.loads(row['payload'])
    with db.connect() as con:
        mapping = con.execute('SELECT entity FROM carbon_mappings WHERE owner=? AND company_id=?', (owner, company['id'])).fetchone()
    # Match a reviewed exact parent alias, never a substring, subsidiary or broad legal name.
    entity = mapping['entity'] if mapping else next((name for name in entry.get('carbon_majors_names', []) if name in data['entities']), None)
    if entity not in data['entities']:
        return result
    series = data['entities'][entity]
    result.update({'series': series, 'entity': entity, 'trend': trend(series, 'total_mtco2e', baseline),
                   'dataset': {k: row[k] for k in ('id', 'version', 'created_at', 'granularity', 'filename')},
                   'mapping_kind': 'User-selected parent; verify the group boundary' if mapping else 'Reviewed exact parent name',
                   'country_scale': country_scale(series[-1])})
    keys = sorted({(p['commodity'], p['unit']) for point in series for p in point['production']})
    for commodity, unit in keys:
        points = [{'year': point['year'], 'value': p['value']} for point in series for p in point['production'] if (p['commodity'], p['unit']) == (commodity, unit)]
        result['production'].append({'commodity': commodity, 'unit': unit, 'series': points, 'trend': trend(points, 'value', baseline)})
    return result


def comparison(rows, same_sector):
    """One common calendar year and one source release; no cross-sector ranks."""
    if not same_sector or any(not row['awareness']['series'] for row in rows):
        return []
    if len({row['awareness']['entity'] for row in rows}) != len(rows):
        return []
    years = set.intersection(*({p['year'] for p in row['awareness']['series']} for row in rows))
    if not years:
        return []
    year = max(years)
    points = [next(p for p in row['awareness']['series'] if p['year'] == year) for row in rows]
    result = [{'label': 'Attributed emissions', 'unit': 'Mt CO2e', 'year': year,
               'cells': [{'value': p['total_mtco2e'], 'entity': row['awareness']['entity']} for p, row in zip(points, rows)]}]
    keys = set.intersection(*({(p['commodity'], p['unit']) for p in point['production']} for point in points))
    for commodity, unit in sorted(keys):
        result.append({'label': commodity + ' production', 'unit': unit, 'year': year,
                       'cells': [{'value': next(p['value'] for p in point['production'] if (p['commodity'], p['unit']) == (commodity, unit)),
                                  'entity': row['awareness']['entity']} for point, row in zip(points, rows)]})
    return result
