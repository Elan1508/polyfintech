"""Bounded single-page research brief, generated from an authorised stored analysis."""
import io
import re
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


def render(item):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(595.28, 841.89), pageCompression=1)
    pdf.setTitle(item['company']['name'] + ' | Company research brief')
    pdf.setAuthor('ESG Pulse 360')
    width, x, y = 511, 42, 798
    ink, muted, accent = colors.HexColor('#142a35'), colors.HexColor('#52636c'), colors.HexColor('#087c67')
    style = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5, leading=13, textColor=ink, alignment=TA_LEFT)

    def text(value, size=9.5, max_lines=4, color=ink, bold=False):
        nonlocal y
        # Fit by actual rendered height; clip with an ellipsis at a word boundary.
        value = str(value or '').replace('₂', '2').replace('−', '-').replace('’', "'")
        citation = re.search(r'\s+(\[\d+\])$', value)
        suffix = ' ' + citation[1] if citation else ''
        words = (value[:citation.start()] if citation else value).split()
        chosen = words[:]
        current = ParagraphStyle('line', parent=style, fontSize=size, leading=size + 3, textColor=color,
                                 fontName='Helvetica-Bold' if bold else 'Helvetica')
        while chosen:
            paragraph = Paragraph(escape(' '.join(chosen) + (' ...' if len(chosen) < len(words) else '') + suffix), current)
            _, h = paragraph.wrap(width, 1000)
            if h <= max_lines * (size + 3):
                paragraph.drawOn(pdf, x, y - h)
                y -= h + 5
                return
            chosen = chosen[:-1]

    def heading(label):
        nonlocal y
        y -= 5
        text(label.upper(), 9, 1, accent, True)

    refs = []
    def ref(url, title, page=None):
        key = (url, page)
        existing = next((i + 1 for i, row in enumerate(refs) if row[:2] == key), None)
        if existing:
            return existing
        refs.append((url, page, title))
        return len(refs)

    text('ESG PULSE 360 / COMPANY RESEARCH', 9, 1, accent, True)
    text(item['company']['name'], 23, 2, ink, True)
    text(f"{item['company'].get('ticker', '')} · {item['company'].get('exchange', '')} · {item['company'].get('sector', '')} | Analysed {item['created_at'][:10]}", 9, 2, muted)
    snapshot = item.get('snapshot') or {}
    knowledge = {s['id']: s for s in item['sources'] + item.get('knowledge_sources', [])}
    if snapshot.get('summary'):
        source = knowledge.get(snapshot.get('summary_source_id'))
        citation = f" [{ref(source['url'], source['title'])}]" if source else ''
        text(snapshot['summary'] + citation, max_lines=3)
    metadata = snapshot.get('facts', [])[:4]
    if metadata:
        text(' | '.join(f"{f['label']}: {f['value']}" + (f" ({f['as_of'][:4]})" if f.get('as_of') else '') for f in metadata), 9, 2, muted)
    financial = snapshot.get('market', [])[:4]
    if financial:
        n = ref(financial[0]['url'], financial[0]['provider'])
        text(' | '.join(f"{f['label']}: {f['value']:,.2f} {f.get('unit') or ''}" for f in financial) + f" · As of {(financial[0].get('as_of') or 'unspecified')[:10]} [{n}]", 8.5, 3, muted)
    heading('Research indicators')
    text(' | '.join(f"{label}: {item['scores'][key]['score'] if item['scores'][key]['score'] is not None else 'Unscored'}" for key, label in [('momentum', 'Report language'), ('risk', 'Risk signals'), ('digital', 'Digital signals')]) + f" | {item['coverage']['source_count']} sources", 10, 2, ink, True)
    climate = item.get('awareness') or {}
    series = climate.get('series', [])
    if series:
        point = series[-1]
        n = ref(climate['source_url'], 'InfluenceMap / Carbon Majors, ' + (climate['dataset'].get('version') or 'imported CSV'))
        heading('Independent climate evidence')
        change = climate.get('trend')
        reading = f"; {change['direction']} from {change['from_year']} to {change['to_year']}" if change else ''
        text(f"{climate['entity']}: {point['total_mtco2e']:,.2f} Mt CO2e in {point['year']}{reading}. Producer-attributed estimate [{n}]", max_lines=2)
        text('Partial Scope 1 and downstream Scope 3; different from operational emissions. Language scores do not establish emissions reductions. Check parent boundaries and dataset dates on the website.', 8.5, 3, muted)
    heading('Key report facts')
    facts = item.get('facts', {}).get('items', [])
    chosen = []
    for metric in ('emissions', 'emissions_intensity', 'net_zero', 'renewable', 'board_women', 'injury_rate'):
        row = next((f for f in facts if f['metric'] == metric and not f.get('review_required')), None)
        if row:
            chosen.append(row)
    if not chosen:
        text('No unambiguous figures were extracted. Open the source report to review its tables.', max_lines=2)
    for f in chosen[:3 if series else 5]:
        n = ref(f['url'], f['title'], f.get('page'))
        text(f"{f['label']}: {f['display']} · {f['status']} · {f['period'] or 'Period not explicit'} · {('p.' + str(f['page'])) if f.get('page') else 'Web section'} [{n}]", 9.5, 2)
    heading('Cited company brief')
    for line in [line for line in item.get('brief', {}).get('items', []) if line['section'].lower() != 'business'][:2 if series else 3]:
        n = ref(line['url'], line['publisher'], line.get('page'))
        text(f"{line['section']}: {line['text']} [{n}]", max_lines=3)
    if not item.get('brief', {}).get('items'):
        text(item['summary'], max_lines=3)
    heading('Sources · links open the original')
    for index, (url, page, title) in enumerate(refs):
        if y < 115:
            break
        top = y
        text(f"[{index + 1}] {title}" + (f' · physical PDF p.{page}' if page else ''), 8.5, 1, accent)
        if url.startswith('https://'):
            pdf.linkURL(url.split('#')[0] + (f'#page={page}' if page else ''), (x, y, x + width, top), relative=0)
    pdf.setStrokeColor(colors.HexColor('#dce5e7'))
    pdf.line(42, 88, 553, 88)
    y = 76
    text('Language indicators describe wording, not environmental performance or investment returns. Company targets are not achieved outcomes. Read full quotations, reporting boundaries and latest sources on the website.', 8.5, 3, muted)
    pdf.showPage()
    pdf.save()
    return output.getvalue()
