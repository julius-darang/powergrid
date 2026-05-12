"""/api/grid/* — pure-topology endpoints (no load-flow joins)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db.connection import acquire
from backend.services.geo import (
    BUS_PROP_COLS, LINE_PROP_COLS,
    fetch_buses, fetch_lines, rows_to_collection,
)

router = APIRouter(prefix='/api/grid', tags=['grid'])


@router.get('/transmission')
async def transmission():
    """All transmission buses + lines (>= 60 kV). Single FeatureCollection."""
    async with acquire() as conn:
        # 60 kV cutoff lines up with the project's 69 kV / 138 kV / 230 kV
        # transmission classes; sub-60 is distribution.
        buses = await fetch_buses(conn, 'voltage_kv >= $1', 60.0)
        lines = await fetch_lines(conn, 'voltage_kv >= $1', 60.0)
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}


@router.get('/province/{province_name}')
async def by_province(province_name: str):
    async with acquire() as conn:
        # Existence check — cheap, gives us a clean 404.
        exists = await conn.fetchval(
            'SELECT 1 FROM buses WHERE province = $1 LIMIT 1', province_name
        )
        if not exists:
            raise HTTPException(404, f'province not found: {province_name}')
        buses = await fetch_buses(conn, 'province = $1', province_name)
        # Lines hang off buses; either endpoint in the province counts.
        # Mirrors `province_filter_lines_via_buses` from load_to_postgis.py.
        # DISTINCT ON because plain DISTINCT can't equate json columns;
        # we dedupe by line_id which is the unique identity anyway.
        line_sql = (
            "SELECT DISTINCT ON (l.line_id) l.line_id, l.from_bus, l.to_bus, "
            "l.voltage_kv, l.length_km, l.is_submarine, l.cable_type, "
            "l.is_synthetic, l.data_source, "
            "ST_AsGeoJSON(l.geom)::json AS geom_json "
            "FROM lines l JOIN buses b "
            "ON l.from_bus = b.bus_id OR l.to_bus = b.bus_id "
            "WHERE b.province = $1"
        )
        lines = await conn.fetch(line_sql, province_name)
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}


@router.get('/island/{island_name}')
async def by_island(island_name: str):
    async with acquire() as conn:
        exists = await conn.fetchval(
            'SELECT 1 FROM buses WHERE island = $1 LIMIT 1', island_name
        )
        if not exists:
            raise HTTPException(404, f'island not found: {island_name}')
        buses = await fetch_buses(conn, 'island = $1', island_name)
        # DISTINCT ON because plain DISTINCT can't equate json columns;
        # we dedupe by line_id which is the unique identity anyway.
        line_sql = (
            "SELECT DISTINCT ON (l.line_id) l.line_id, l.from_bus, l.to_bus, "
            "l.voltage_kv, l.length_km, l.is_submarine, l.cable_type, "
            "l.is_synthetic, l.data_source, "
            "ST_AsGeoJSON(l.geom)::json AS geom_json "
            "FROM lines l JOIN buses b "
            "ON l.from_bus = b.bus_id OR l.to_bus = b.bus_id "
            "WHERE b.island = $1"
        )
        lines = await conn.fetch(line_sql, island_name)
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}


@router.get('/viewport')
async def viewport(
    minlon: float = Query(...),
    minlat: float = Query(...),
    maxlon: float = Query(...),
    maxlat: float = Query(...),
):
    """Buses + lines inside a lon/lat envelope. Uses the GIST indexes."""
    if minlon >= maxlon or minlat >= maxlat:
        raise HTTPException(422, 'invalid bbox: min must be < max')
    if not (-180 <= minlon <= 180 and -180 <= maxlon <= 180):
        raise HTTPException(422, 'longitude out of range')
    if not (-90 <= minlat <= 90 and -90 <= maxlat <= 90):
        raise HTTPException(422, 'latitude out of range')

    async with acquire() as conn:
        buses = await fetch_buses(
            conn,
            'ST_Within(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))',
            minlon, minlat, maxlon, maxlat,
        )
        lines = await fetch_lines(
            conn,
            'ST_Intersects(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))',
            minlon, minlat, maxlon, maxlat,
        )
    feats = (
        rows_to_collection(buses, BUS_PROP_COLS)['features']
        + rows_to_collection(lines, LINE_PROP_COLS)['features']
    )
    return {'type': 'FeatureCollection', 'features': feats}
