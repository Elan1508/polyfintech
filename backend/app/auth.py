import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from . import config, db


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600_000)
    return f'pbkdf2_sha256$600000${salt.hex()}${digest.hex()}'


def check_password(password, stored):
    try:
        _, iterations, salt, digest = stored.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), digest)
    except (ValueError, TypeError):
        return False


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def session(request: Request):
    token = request.cookies.get(config.COOKIE_NAME, '')
    if not token:
        raise HTTPException(401, 'Your session has expired. Reload to continue.')
    with db.connect() as con:
        row = con.execute('SELECT * FROM sessions WHERE token_hash=? AND expires_at>?', (token_hash(token), db.now())).fetchone()
        user = con.execute('SELECT id,email,name FROM users WHERE id=?', (row['user_id'],)).fetchone() if row and row['user_id'] else None
    if not row:
        raise HTTPException(401, 'Your session has expired. Reload to continue.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), row['csrf']):
            raise HTTPException(403, 'Session verification failed. Reload and try again.')
    return {**dict(row), 'user': dict(user) if user else None}


def create_session(response: Response, request: Request, user=None, old=None):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    owner = user['id'] if user else f'guest:{uuid.uuid4().hex}'
    expires = (datetime.now(timezone.utc) + timedelta(days=config.SESSION_DAYS)).isoformat(timespec='seconds')
    with db.connect() as con:
        if old:
            db.migrate_guest(old['owner'], owner, con)
            con.execute('DELETE FROM sessions WHERE token_hash=?', (old['token_hash'],))
        con.execute('INSERT INTO sessions VALUES (?,?,?,?,?)', (token_hash(token), owner, user['id'] if user else None, csrf, expires))
        con.execute('DELETE FROM sessions WHERE expires_at<?', (db.now(),))
    response.set_cookie(config.COOKIE_NAME, token, httponly=True,
                        secure=request.url.scheme == 'https' or os.getenv('ESG_SECURE_COOKIES') == '1',
                        samesite='lax', max_age=config.SESSION_DAYS * 86400, path='/')
    return {'owner': owner, 'csrf': csrf, 'user': user}


def limit(key, maximum, seconds):
    current = time.time()
    with db.connect() as con:
        con.execute('DELETE FROM rate_limits WHERE expires_at<?', (current,))
        con.execute('INSERT INTO rate_limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, current + seconds))
        row = con.execute('SELECT count FROM rate_limits WHERE key=?', (key,)).fetchone()
    if row['count'] > maximum:
        raise HTTPException(429, 'Too many requests. Please wait before trying again.')
