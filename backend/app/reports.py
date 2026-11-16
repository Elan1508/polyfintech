import hashlib
import io
import json
import re
import uuid
import zipfile

from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader

from . import config, db


def extract(filename, content):
    extension = filename.rsplit('.', 1)[-1].lower()
    if extension not in ('pdf', 'docx', 'txt'):
        raise HTTPException(415, 'Choose a PDF, DOCX, or UTF-8 TXT document.')
    if not content or len(content) > config.MAX_UPLOAD:
        raise HTTPException(413, 'The document must be between 1 byte and 12 MB.')
    pages, warnings = [], []
    try:
        if extension == 'pdf':
            if not content.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF header')
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise HTTPException(422, 'This PDF is password protected. Upload an unlocked copy.')
            if len(reader.pages) > 500:
                raise HTTPException(422, 'This report exceeds 500 pages. Upload the relevant sections.')
            for number, page in enumerate(reader.pages, 1):
                stream = page.get_contents()
                if stream and len(stream.get_data()) > 8 * 1024 * 1024:
                    raise HTTPException(422, f'Page {number} is too complex to extract safely.')
                text = page.extract_text() or ''
                pages.append({'page': number, 'label': f'Page {number}', 'text': text.strip()})
            blank = sum(not p['text'].strip() for p in pages)
            if blank:
                warnings.append(f'{blank} pages have no extractable text. Image-only pages require OCR and are not analysed.')
        elif extension == 'docx':
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(f.file_size for f in archive.infolist()) > 40 * 1024 * 1024:
                    raise HTTPException(422, 'The expanded DOCX is too large. Upload the relevant sections.')
            doc = Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            paragraphs += [' | '.join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows]
            for index in range(0, len(paragraphs), 8):
                pages.append({'page': None, 'label': f'Section {index // 8 + 1}', 'text': '\n'.join(paragraphs[index:index + 8])})
            warnings.append('DOCX references use extracted sections. Word pagination is not preserved.')
        else:
            text = content.decode('utf-8-sig')
            paragraphs = re.split(r'\n\s*\n', text)
            for index in range(0, len(paragraphs), 5):
                pages.append({'page': None, 'label': f'Section {index // 5 + 1}', 'text': '\n\n'.join(paragraphs[index:index + 5])})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, 'This document could not be read. Check that it is valid and unencrypted.')
    if sum(len(p['text']) for p in pages) < 30:
        raise HTTPException(422, 'No usable text was found. Scanned PDFs need OCR before upload.')
    if sum(len(p['text']) for p in pages) > 1_500_000:
        raise HTTPException(422, 'The report contains too much text. Upload the relevant sections.')
    return pages, warnings, extension


def store(owner, filename, content, company):
    pages, warnings, extension = extract(filename, content)
    report_id = uuid.uuid4().hex
    folder = config.RUNTIME / 'uploads'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{report_id}.{extension}'
    path.write_bytes(content)
    mime = {'pdf': 'application/pdf', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'txt': 'text/plain'}[extension]
    try:
        with db.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            resolved_owner = db.resolve_owner(owner, con)
            con.execute('INSERT INTO reports VALUES (?,?,?,?,?,?,?)',
                        (report_id, resolved_owner, filename, mime, str(path), json.dumps(pages), db.now()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    sources = []
    for index, page in enumerate(pages):
        text = page['text']
        # Every page is retained for search; scoring uses one contribution per dimension per page.
        if text.strip():
            sources.append({'id': f'report_{report_id}_{index}', 'title': f"{filename} · {page['label']}",
                            'excerpt': text, 'publisher': 'User-uploaded report', 'published_at': None,
                            'collected_at': db.now(), 'kind': 'report', 'url': f'/api/reports/{report_id}/file',
                            'page': page['page'], 'section': page['label'], 'report_id': report_id, 'self_reported': True})
    return report_id, sources, pages, warnings
