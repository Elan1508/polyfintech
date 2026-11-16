import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config, profiles, public_research, research, worker
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'RUNTIME', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', str(tmp_path / 'test.sqlite3'))
    async def idle(stop):
        await stop.wait()
    monkeypatch.setattr(worker, 'run', idle)
    monkeypatch.setattr(profiles, 'collect', lambda company: {'summary':'', 'facts':[], 'market':[], 'sources':[], 'collected_at':'2026-11-15T00:00:00+00:00', 'notice':'Offline test'})
    monkeypatch.setattr(public_research, 'seed', lambda: None)
    monkeypatch.setattr(public_research, 'schedule', lambda: None)
    monkeypatch.setattr(research, 'collect', lambda company: {'sources': [], 'warnings': [], 'profile': research.preview(company)})
    with TestClient(app) as value:
        yield value


def headers(client):
    return {'X-CSRF-Token': client.get('/api/session').json()['csrf']}


def run_analysis(client, company='directory:dbs', mode='demo', refresh=False):
    response = client.post('/api/analyses', headers=headers(client), json={'company_id': company, 'mode': mode, 'refresh': refresh})
    assert response.status_code == 200, response.text
    data = response.json()
    if 'job' in data:
        assert worker.process_one()
        job = client.get('/api/jobs/' + data['job']['id']).json()
        assert job['status'] == 'complete', job
        analysis_id = job['analysis_id']
    else:
        analysis_id = data['analysis_id']
    return client.get('/api/analyses/' + analysis_id).json()
