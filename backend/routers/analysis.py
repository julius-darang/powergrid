"""/api/loadflow, /api/provinces, /api/scenarios, /api/health."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.db.connection import acquire
from backend.models.schemas import (
    FeatureCollection, Health, ProvincesResponse, ScenariosResponse,
)
from backend.services.geo import (
    BUS_PROP_COLS, LINE_PROP_COLS, rows_to_collection,
)

router = APIRouter(tags=['analysis'])

SCENARIOS = ('off_peak', 'morning_peak', 'evening_peak')


def _check_scenario(scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise HTTPException(
            404, f'scenario not found: {scenario}. valid: {list(SCENARIOS)}'
        )


# Bus + line load-flow joins. Left join because not every bus / line has
# a row in load_flow_results for every scenario (e.g. out-of-service or
# disconnected components — see phase-2 closeout).
_BUS_LOADFLOW_SQL = (
    "SELECT b.bus_id, b.name, b.voltage_kv, b.province, b.island, "
    "b.bus_type, b.p_mw, b.q_mvar, b.is_synthetic, b.data_source, "
    "r.vm_pu, r.va_degree, r.convergence_mode, "
    "ST_AsGeoJSON(b.geom)::json AS geom_json "
    "FROM buses b "
    "LEFT JOIN load_flow_results r "
    "  ON r.bus_id = b.bus_id AND r.scenario = $1"
)

_LINE_LOADFLOW_SQL = (
    "SELECT l.line_id, l.from_bus, l.to_bus, l.voltage_kv, l.length_km, "
    "l.is_submarine, l.cable_type, l.is_synthetic, l.data_source, "
    "r.loading_percent, r.p_from_mw, r.p_to_mw, r.convergence_mode, "
    "ST_AsGeoJSON(l.geom)::json AS geom_json "
    "FROM lines l "
    "LEFT JOIN load_flow_results r "
    "  ON r.line_id = l.line_id AND r.scenario = $1"
)


@router.get('/api/loadflow/{scenario}', response_model=FeatureCollection)
async def loadflow(scenario: str):
    _check_scenario(scenario)
    async with acquire() as conn:
        buses = await conn.fetch(_BUS_LOADFLOW_SQL, scenario)
        lines = await conn.fetch(_LINE_LOADFLOW_SQL, scenario)
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}


@router.get('/api/loadflow/{scenario}/{province}', response_model=FeatureCollection)
async def loadflow_province(scenario: str, province: str):
    _check_scenario(scenario)
    async with acquire() as conn:
        exists = await conn.fetchval(
            'SELECT 1 FROM buses WHERE province = $1 LIMIT 1', province
        )
        if not exists:
            raise HTTPException(404, f'province not found: {province}')
        buses = await conn.fetch(
            _BUS_LOADFLOW_SQL + ' WHERE b.province = $2', scenario, province,
        )
        # Lines: either endpoint in the province. DISTINCT because a line
        # joins on both ends and can match twice.
        line_sql = (
            "SELECT DISTINCT ON (l.line_id) l.line_id, l.from_bus, l.to_bus, "
            "l.voltage_kv, l.length_km, l.is_submarine, l.cable_type, "
            "l.is_synthetic, l.data_source, "
            "r.loading_percent, r.p_from_mw, r.p_to_mw, r.convergence_mode, "
            "ST_AsGeoJSON(l.geom)::json AS geom_json "
            "FROM lines l "
            "LEFT JOIN load_flow_results r "
            "  ON r.line_id = l.line_id AND r.scenario = $1 "
            "JOIN buses b ON l.from_bus = b.bus_id OR l.to_bus = b.bus_id "
            "WHERE b.province = $2"
        )
        lines = await conn.fetch(line_sql, scenario, province)
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}


@router.get('/api/provinces', response_model=ProvincesResponse)
async def provinces():
    """Sidebar payload: per-province counts and total connected load.

    `in_service_bus_count` is derived from `load_flow_results` membership
    — Phase 2 only emits rows for buses inside the connected big
    component, so presence in that table is a proxy for in-service.
    """
    sql = (
        "SELECT b.province AS name, "
        "MIN(b.island) AS island, "
        "COUNT(*)::int AS bus_count, "
        "COUNT(DISTINCT r.bus_id)::int AS in_service_bus_count, "
        "COALESCE(SUM(b.p_mw), 0)::float AS total_load_mw, "
        "COALESCE(SUM(b.p_mw) FILTER (WHERE r.bus_id IS NOT NULL), 0)::float "
        "  AS in_service_load_mw, "
        "COUNT(*) FILTER (WHERE b.data_source = 'osm')::int AS osm_buses, "
        "COUNT(*) FILTER (WHERE b.is_synthetic)::int AS synthetic_buses "
        "FROM buses b "
        "LEFT JOIN load_flow_results r "
        "  ON r.bus_id = b.bus_id AND r.scenario = 'evening_peak' "
        "WHERE b.province IS NOT NULL "
        "GROUP BY b.province ORDER BY b.province"
    )
    async with acquire() as conn:
        rows = await conn.fetch(sql)
    return {'provinces': [dict(r) for r in rows]}


@router.get('/api/scenarios', response_model=ScenariosResponse)
async def scenarios():
    """Available scenarios with the convergence mode actually used."""
    # convergence_mode is per-row in load_flow_results, but in practice
    # the whole scenario shares one mode (NR or DC fallback — Phase 2
    # closeout). Pick the most common via mode-style group-by.
    sql = (
        "SELECT scenario, convergence_mode, COUNT(*)::int AS n "
        "FROM load_flow_results "
        "WHERE convergence_mode IS NOT NULL "
        "GROUP BY scenario, convergence_mode"
    )
    async with acquire() as conn:
        rows = await conn.fetch(sql)
    mode_by_scenario: dict[str, str] = {}
    counts: dict[str, dict[str, int]] = {}
    for r in rows:
        counts.setdefault(r['scenario'], {})[r['convergence_mode']] = r['n']
    for sc, cs in counts.items():
        mode_by_scenario[sc] = max(cs, key=cs.get)
    return {
        'scenarios': [
            {'name': s, 'mode': mode_by_scenario.get(s)} for s in SCENARIOS
        ]
    }


@router.get('/api/health', response_model=Health)
async def health():
    async with acquire() as conn:
        db_version = await conn.fetchval('SELECT version()')
        postgis_version = await conn.fetchval('SELECT PostGIS_Version()')
        buses = await conn.fetchval('SELECT COUNT(*) FROM buses')
        lines = await conn.fetchval('SELECT COUNT(*) FROM lines')
        lf = await conn.fetchval('SELECT COUNT(*) FROM load_flow_results')
    return {
        'status': 'ok',
        'db_version': db_version,
        'postgis_version': postgis_version,
        'counts': {
            'buses': buses,
            'lines': lines,
            'load_flow_results': lf,
        },
    }
