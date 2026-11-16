import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / '.env')
load_dotenv(BACKEND.parent / '.env')
RUNTIME = Path(os.getenv('ESG_RUNTIME_DIR', str(BACKEND / 'runtime')))
DB_PATH = os.getenv('ESG_DB_PATH', str(RUNTIME / 'pulse.sqlite3'))
ALLOWED_ORIGINS = [s.strip() for s in os.getenv(
    'ESG_ALLOWED_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173'
).split(',') if s.strip()]
COOKIE_NAME = 'pulse_session'
SESSION_DAYS = 7
SCORING_VERSION = 'evidence-2.1'
REFRESH_SECONDS = max(3600, int(os.getenv('ESG_REFRESH_SECONDS', '86400')))
MAX_UPLOAD = 12 * 1024 * 1024
