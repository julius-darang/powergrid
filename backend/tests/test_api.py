"""Sanity tests — hit a live DB. Run with: .venv/bin/pytest backend/tests/"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope='module')
def client():
    # TestClient drives lifespan, which opens the asyncpg pool.
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get('/api/health')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['status'] == 'ok'
    counts = body['counts']
    # Post Phase 1 recalibration (Day 27): 2959 buses, 2972 lines,
    # 7536 load-flow rows. These move slightly whenever Phase 1's
    # synthetic distribution feeders are regenerated; update when
    # run_phase1.py output changes.
    assert counts['buses'] == 2959
    assert counts['lines'] == 2972
    assert counts['load_flow_results'] == 7536


def test_scenarios(client):
    r = client.get('/api/scenarios')
    assert r.status_code == 200, r.text
    names = [s['name'] for s in r.json()['scenarios']]
    assert names == ['off_peak', 'morning_peak', 'evening_peak']
