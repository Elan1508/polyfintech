import math
import re
import uuid
from datetime import datetime, timezone

from . import config, db

RULES = {
    'E': {
        'positive': ['renewable', 'solar', 'decarbonisation', 'decarbonization', 'carbon reduction', 'net zero', 'net-zero', 'green financing', 'energy efficiency', 'sustainable bonds', 'electric vehicle', 'emissions reduction', 'low carbon', 'low-carbon'],
        'negative': ['deforestation', 'pollution', 'oil spill', 'environmental incident', 'greenwashing', 'illegal logging', 'emissions increase'],
        'neutral': ['climate', 'sustainability', 'environment', 'emissions', 'carbon']},
    'S': {
        'positive': ['worker safety', 'fair wages', 'employee wellbeing', 'diversity', 'inclusion', 'community investment', 'training programme', 'financial inclusion'],
        'negative': ['forced labour', 'forced labor', 'labour issue', 'labor issue', 'worker injury', 'fatality', 'discrimination', 'unsafe working', 'child labour', 'labour controversy'],
        'neutral': ['workforce', 'workers', 'labour', 'labor', 'employee', 'community']},
    'G': {
        'positive': ['board independence', 'independent directors', 'anti-corruption', 'anti-bribery', 'governance controls', 'transparency', 'responsible ai', 'model governance'],
        'negative': ['corruption', 'bribery', 'fraud', 'regulatory fine', 'regulatory investigation', 'regulatory scrutiny', 'governance controversy', 'sanction', 'lawsuit'],
        'neutral': ['governance', 'regulatory', 'disclosure', 'board']},
    'digital': {
        'positive': ['responsible ai', 'ai governance', 'model governance', 'cybersecurity investment', 'cybersecurity hiring', 'data governance', 'privacy controls', 'data protection', 'cybersecurity controls'],
        'negative': ['data breach', 'cyberattack', 'cyber attack', 'data leak', 'privacy violation', 'ransomware'],
        'neutral': ['artificial intelligence', 'cybersecurity', 'digital', 'automation', ' ai ']} }

LABELS = {'E': 'Environmental', 'S': 'Social', 'G': 'Governance', 'digital': 'Responsible technology'}


def contains(text, phrase):
    return re.search(r'(?<!\w)' + re.escape(phrase.strip()) + r'(?!\w)', text, re.I) is not None


def negated(text, phrase):
    # Sentence-scoped negation avoids counting "no data breach" as an incident.
    return bool(re.search(r'\banti[- ]' + re.escape(phrase) + r'\b', text, re.I) or
                re.search(r'\b(no|without|zero|not|denies?|denied|prevented)\b[^.!?;]{0,50}\b' + re.escape(phrase) + r'\b', text, re.I))


def signals_for(source, at):
    text = re.sub(r'\s+', ' ', source['excerpt'] + ' ' + source['title']).strip()
    try:
        published = datetime.fromisoformat(source['published_at'].replace('Z', '+00:00'))
        age = max(0, (at - published).days)
        freshness = max(0.25, math.exp(-age / 180))
    except (ValueError, TypeError, AttributeError):
        freshness = 0.5
    weight = 0.65 if source['kind'] == 'news' else 0.8 if source['kind'] in ('report', 'disclosure') else 0.5
    found = []
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    for dimension, rules in RULES.items():
        positive = [term for term in rules['positive'] if any(contains(s, term) and not negated(s, term) for s in sentences)]
        negative = [term for term in rules['negative'] if any(contains(s, term) and not negated(s, term) for s in sentences)]
        neutral = [term for term in rules['neutral'] if contains(text, term)]
        if not (positive or negative or neutral):
            continue
        direction = 'mixed' if positive and negative else 'negative' if negative else 'positive' if positive else 'context'
        units = min(2, len(positive)) - min(2, len(negative))
        contribution = round(10 * units * weight * freshness, 2)
        found.append({'id': f"{source['id']}_{dimension}", 'source_id': source['id'], 'dimension': dimension,
                      'direction': direction, 'terms': list(dict.fromkeys(positive + negative + neutral))[:10],
                      'positive_terms': positive, 'negative_terms': negative,
                      'positive_count': len(positive), 'negative_count': len(negative), 'contribution': contribution,
                      'source_weight': weight, 'freshness_weight': round(freshness, 3),
                      'explanation': f"{LABELS[dimension]} language: " + ', '.join((positive + negative + neutral)[:5])})
    return found


def clamp(value):
    return round(max(0, min(100, value)))


def source_identity(source):
    return source.get('report_id') or source.get('evidence_group') or source['id']


def risk_flag_count(item):
    sources = {s['id']: s for s in item['sources']}
    return len({(source_identity(sources[signal['source_id']]), signal['dimension'], term)
                for signal in item['signals'] if signal['source_id'] in sources
                for term in signal.get('negative_terms', [])})


def build(company, sources, mode='live', warnings=None, kind='company', report_id=None):
    at = datetime.now(timezone.utc)
    signals = [signal for source in sources for signal in signals_for(source, at)]
    source_index = {source['id']: source for source in sources}
    report_terms = {}
    for signal in signals:
        group_id = source_index[signal['source_id']].get('report_id') or source_index[signal['source_id']].get('evidence_group')
        if not group_id:
            continue
        key = (group_id, signal['dimension'])
        seen = report_terms.setdefault(key, {'positive': set(), 'negative': set()})
        positive = set(signal['positive_terms']) - seen['positive']
        negative = set(signal['negative_terms']) - seen['negative']
        positive_units = min(2, len(seen['positive'] | positive)) - min(2, len(seen['positive']))
        negative_units = min(2, len(seen['negative'] | negative)) - min(2, len(seen['negative']))
        seen['positive'].update(positive)
        seen['negative'].update(negative)
        signal['negative_count'] = negative_units
        signal['contribution'] = round(10 * (positive_units - negative_units) * signal['source_weight'] * signal['freshness_weight'], 2)
        if signal['contribution'] == 0 and signal['direction'] != 'context':
            signal['explanation'] += '. Repeated or capped report terms add no further score contribution.'
    dimensions = {}
    for key in RULES:
        rows = [s for s in signals if s['dimension'] == key]
        directional = [s for s in rows if s['direction'] != 'context']
        score = clamp(50 + sum(s['contribution'] for s in directional)) if directional else None
        dimensions[key] = {'score': score, 'label': LABELS[key], 'evidence_count': len(rows),
                           'directional_count': len(directional), 'source_ids': list(dict.fromkeys(s['source_id'] for s in rows)),
                           'status': 'Available' if directional else 'Context only' if rows else 'Insufficient evidence'}
    esg = [s for s in signals if s['dimension'] in ('E', 'S', 'G') and s['direction'] != 'context']
    momentum = clamp(50 + sum(s['contribution'] for s in esg)) if esg else None
    negatives = [s for s in signals if s['negative_count']]
    risk = clamp(sum(s['negative_count'] * s['source_weight'] * s['freshness_weight'] * 12 for s in negatives)) if negatives else None
    coverage = sum(1 for d in dimensions.values() if d['directional_count'])
    source_count = len({source_identity(s) for s in sources})
    recent_count = len({source_identity(s) for s in sources if s.get('published_at') and _recent(s['published_at'], at)})
    publishers = len({s['publisher'].casefold() for s in sources})
    enough = source_count >= 3 and coverage >= 2
    data_status = 'Demo evidence' if mode == 'demo' else 'Moderate coverage' if enough else 'Limited evidence'
    momentum_label = 'Improving signals' if momentum is not None and momentum >= 65 else 'Adverse signals' if momentum is not None and momentum < 40 else 'Mixed signals' if momentum is not None else 'Unassessed'
    risk_label = 'Elevated flags' if risk is not None and risk >= 45 else 'Flags detected' if risk is not None else 'No flags in collected evidence' if enough else 'Unassessed'
    digital_score = dimensions['digital']['score']
    opportunity = 'Improvement candidate' if enough and momentum is not None and momentum >= 65 and digital_score is not None and digital_score >= 60 and (risk is None or risk < 30) else 'Review risk evidence' if risk is not None and risk >= 45 else 'Continue research'
    notices = list(warnings or [])
    if mode == 'demo':
        notices.insert(0, 'Synthetic demo evidence. These results do not describe current company performance.')
    if not enough:
        notices.append('Coverage is limited. Missing evidence is not evidence of good or poor performance.')
    if kind == 'report':
        notices.append('Uploaded material is user-supplied and may contain self-reported claims. Publication date has not been verified; freshness receives the unknown-date weight.')
    if any(s.get('kind') == 'disclosure' for s in sources):
        notices.append('Company reports contain self-reported claims. Automated scores analyse selected passages, including targets and policies; they do not verify results or replace reading the full report.')
    return {'id': uuid.uuid4().hex, 'company': company, 'kind': kind, 'mode': mode, 'report_id': report_id,
            'created_at': db.now(), 'scoring_version': config.SCORING_VERSION, 'saved': False,
            'scores': {'momentum': {'score': momentum, 'label': momentum_label},
                       'risk': {'score': risk, 'label': risk_label},
                       'digital': {'score': digital_score, 'label': dimensions['digital']['status']}},
            'dimensions': dimensions, 'classification': opportunity,
            'coverage': {'status': data_status, 'source_count': source_count, 'excerpt_count': len(sources), 'publisher_count': publishers,
                         'recent_count': recent_count, 'dimensions_covered': coverage, 'languages': ['English'],
                         'description': 'Coverage counts available evidence, not confidence or factual accuracy.'},
            'summary': (f"This analysis brings together {source_count} source{'s' if source_count != 1 else ''} for {company['name']}. "
                        f"Scoring is available for {coverage} of the four ESG and digital areas. Review the reports and news below to understand the results."
                        if sources else 'Public ESG information is limited for this company. Explore its profile and available documents, or add an official report to build a fuller picture.'),
            'sources': sources, 'signals': signals, 'warnings': list(dict.fromkeys(notices)),
            'methodology': {'version': config.SCORING_VERSION,
                            'formula': 'Dimension/momentum = clamp(50 + sum of evidence contributions). A contribution is 10 × (positive terms capped at 2 − negative terms capped at 2) × source weight × freshness. Report terms are counted once per document/dimension, capped at 2 in each direction. Context-only evidence is unscored.',
                            'weights': {'news': 0.65, 'report': 0.8, 'disclosure': 0.8, 'demo': 0.5},
                            'freshness': 'exp(−days/180), minimum 0.25. Unknown publication date: 0.5.',
                            'risk': 'Sum of negative-term counts × source weight × freshness × 12, capped at 100. No negative evidence yields an unscored risk value.',
                            'limitations': ['Research indicators, not accredited ESG ratings or investment recommendations.',
                                            'English phrase rules can miss nuance, negation, allegations, and non-English evidence.',
                                            'No inference of job counts, patents, market valuation, or price performance.',
                                            'Publisher diversity does not guarantee independent reporting. Scores are not sector-normalised.',
                                            'Document/news evidence can be incomplete and company claims are not independently verified.']}}


def _recent(value, at):
    try:
        return 0 <= (at - datetime.fromisoformat(value.replace('Z', '+00:00'))).days <= 90
    except (ValueError, TypeError):
        return False


def changes(previous, current):
    if not previous:
        return {'new_source_count': len({source_identity(s) for s in current['sources']}), 'score_changes': {}, 'method_changed': False, 'message': 'Your first analysis has been saved.'}
    old_ids = {source_identity(s) for s in previous['sources']}
    changed = previous['scoring_version'] != current['scoring_version']
    deltas = {}
    if not changed:
        for key, row in current['scores'].items():
            old = previous['scores'][key]['score']
            if old is not None and row['score'] is not None:
                deltas[key] = row['score'] - old
    new_count = len({source_identity(s) for s in current['sources']} - old_ids)
    return {'new_source_count': new_count, 'score_changes': deltas, 'method_changed': changed,
            'message': 'Methodology changed; numerical comparisons are paused.' if changed else
                       f'{new_count} new source{"s" if new_count != 1 else ""} since your last analysis. Scores may also change as sources age or leave the research period.'}
