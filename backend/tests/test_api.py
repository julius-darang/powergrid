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


@pytest.fixture(scope='module')
def sample_province(client):
    """A real province name pulled from /api/provinces — keeps tests
    decoupled from which provinces actually loaded."""
    r = client.get('/api/provinces')
    assert r.status_code == 200, r.text
    names = [p['name'] for p in r.json()['provinces']]
    assert names, 'no provinces in DB — did Phase 1 run?'
    return names[0]


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
    payload = r.json()
    names = [s['name'] for s in payload['scenarios']]
    assert names == ['off_peak', 'morning_peak', 'evening_peak']
    # Mode is either 'nr' or 'dc' (or None if the scenario didn't run)
    for s in payload['scenarios']:
        assert s['mode'] in ('nr', 'dc', None)


def test_provinces_shape(client):
    r = client.get('/api/provinces')
    assert r.status_code == 200, r.text
    provinces = r.json()['provinces']
    assert len(provinces) > 0
    expected = {
        'name', 'island', 'bus_count', 'in_service_bus_count',
        'total_load_mw', 'in_service_load_mw', 'osm_buses', 'synthetic_buses',
    }
    p0 = provinces[0]
    assert expected.issubset(p0.keys()), f'missing keys: {expected - p0.keys()}'
    # in_service can't exceed total
    assert p0['in_service_bus_count'] <= p0['bus_count']


def test_transmission_voltage_filter(client):
    r = client.get('/api/grid/transmission')
    assert r.status_code == 200, r.text
    feats = r.json()['features']
    assert len(feats) > 0
    for f in feats:
        v = f['properties']['voltage_kv']
        assert v >= 60.0, f'sub-transmission feature leaked: {v} kV'


def test_viewport_bbox_validation(client):
    # min == max → invalid
    r = client.get('/api/grid/viewport', params={
        'minlon': 121.0, 'minlat': 14.0, 'maxlon': 121.0, 'maxlat': 14.5,
    })
    assert r.status_code == 422

    # latitude out of range
    r = client.get('/api/grid/viewport', params={
        'minlon': 120.0, 'minlat': -91.0, 'maxlon': 122.0, 'maxlat': 15.0,
    })
    assert r.status_code == 422


def test_province_404(client):
    r = client.get('/api/grid/province/Atlantis')
    assert r.status_code == 404


def test_scenario_404(client):
    r = client.get('/api/loadflow/midday_peak')
    assert r.status_code == 404


def test_loadflow_bus_has_vm_pu(client):
    r = client.get('/api/loadflow/evening_peak')
    assert r.status_code == 200, r.text
    feats = r.json()['features']
    # Buses are Point features; lines are LineString. Buses carry vm_pu.
    bus_feats = [f for f in feats if f['geometry'] and f['geometry']['type'] == 'Point']
    assert bus_feats, 'no bus features in loadflow response'
    # vm_pu key should be present on every bus (possibly None for buses
    # outside the connected component)
    for f in bus_feats:
        assert 'vm_pu' in f['properties']
    # At least some should be non-null — connected component is not empty.
    assert any(f['properties']['vm_pu'] is not None for f in bus_feats)


def test_loadflow_province_scoped(client, sample_province):
    r = client.get(f'/api/loadflow/evening_peak/{sample_province}')
    assert r.status_code == 200, r.text
    feats = r.json()['features']
    bus_feats = [f for f in feats if f['geometry'] and f['geometry']['type'] == 'Point']
    # Every bus in the response belongs to the requested province.
    for f in bus_feats:
        assert f['properties']['province'] == sample_province


def test_loadflow_island_scoped(client):
    # Cebu island always has data — it's a core Phase 1 region.
    r = client.get('/api/loadflow/evening_peak/island/Cebu')
    assert r.status_code == 200, r.text
    feats = r.json()['features']
    bus_feats = [f for f in feats if f['geometry'] and f['geometry']['type'] == 'Point']
    assert bus_feats, 'no buses in Cebu island loadflow'
    for f in bus_feats:
        assert f['properties']['island'] == 'Cebu'


def test_island_404(client):
    r = client.get('/api/loadflow/evening_peak/island/Atlantis')
    assert r.status_code == 404
