"""Descriptive article tags; headlines are never treated as verified allegations."""
import re

from .analysis import RULES, contains, negated


def reported_status(title):
    """Describe only an explicitly reported stage; never adjudicate from RSS text."""
    if re.search(r'\b(?:dismissed|overturned|acquitted|cleared of|charges dropped)\b', title, re.I):
        return 'Dismissed / overturned'
    provisional = re.search(r'\b(?:may|might|could|faces?|seeks?|proposed|potential|appeals?|appealing|denies?|denied)\b', title, re.I)
    if not provisional and re.search(r'\b(?:settles?|settled|settlement reached|agrees? to (?:pay|settle))\b', title, re.I):
        return 'Settled'
    if not provisional and re.search(r'\b(?:fined|ordered to pay|penalty imposed|imposes? (?:a |an )?(?:fine|penalty))\b', title, re.I):
        return 'Fined'
    if re.search(r'\b(?:under investigation|investigates?|investigating|opens? (?:an? )?(?:investigation|probe)|probed)\b', title, re.I):
        return 'Under investigation'
    return 'Alleged'


def tag(source):
    if source.get('kind') != 'news':
        return source
    text = source['title'] + '. ' + source.get('excerpt', '')
    sentences = re.split(r'(?<=[.!?])\s+', text.lower())
    areas, positive, negative = [], [], []
    for area, rules in RULES.items():
        if any(contains(text, term) for terms in rules.values() for term in terms):
            areas.append(area)
        positive += [term for term in rules['positive'] if any(contains(s, term) and not negated(s, term) for s in sentences)]
        negative += [term for term in rules['negative'] if any(contains(s, term) and not negated(s, term) for s in sentences)]
    allegation = re.search(r'\b(?:lawsuit|sued|scandal|accused|allegations?|fined|penalty|under investigation|investigates?|investigating|investigation into|probe into|settled|settlement|ordered to pay|data breach|deforestation|forced labour|forced labor|corruption|fraud)\b', text, re.I)
    preventive = re.search(r'\b(?:zero.deforestation|no.deforestation|anti.corruption|prevent(?:ing|ion)?|policy|policies|pledge|commitment|training)\b', source['title'], re.I)
    event = re.search(r'\b(?:sued|lawsuit|scandal|accused|allegations?|fined|penalty|probe|breach|fraud)\b', source['title'], re.I)
    controversy = bool(allegation and (not preventive or event) and not source.get('self_reported'))
    return {**source, 'areas': areas, 'case_status': reported_status(source['title']) if controversy else None,
            'status_basis': 'Headline-reported stage; not a verified case history or finding against the company.' if controversy else None,
            'sentiment': 'controversy' if controversy else 'negative' if negative and not positive else 'positive' if positive and not negative else 'mixed' if positive and negative else 'neutral',
            'controversy': controversy, 'text_coverage': 'headline and RSS excerpt',
            'tag_notice': 'Automated topic tags. A reported allegation is not a finding of wrongdoing.'}


def timeline(sources):
    return sorted([s for s in sources if s.get('controversy')], key=lambda s: s.get('published_at') or '', reverse=True)


def updates(previous, current, since=None):
    old_ids = {s['id'] for s in (previous or {}).get('sources', [])}
    new = [s for s in current.get('sources', []) if s['id'] not in old_ids]
    if since:
        # Do not label an old article as a newly occurring controversy after a refresh.
        new = [s for s in new if s.get('published_at') and s['published_at'] > since]
    articles = timeline(new)
    if articles:
        s = articles[0]
        return {'kind': 'controversy', 'message': 'Reported controversy: ' + s['title'],
                'source_id': s['id'], 'publisher': s['publisher'], 'published_at': s.get('published_at'), 'url': s['url']}
    metrics = current.get('facts', {}).get('items', [])
    old_facts = {f['id'] for f in (previous or {}).get('facts', {}).get('items', [])}
    added = [f for f in metrics if f['id'] not in old_facts]
    if added:
        f = added[0]
        return {'kind': 'report_fact', 'message': f"Report evidence: {f['label']} · {f['display']}",
                'source_id': f['source_id'], 'publisher': f['publisher'], 'url': f['url'], 'published_at': None}
    return None
