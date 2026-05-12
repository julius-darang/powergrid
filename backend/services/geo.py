"""SQL → GeoJSON feature helpers.

PostGIS emits GeoJSON natively via ST_AsGeoJSON(geom)::json — we avoid
building geometries Python-side. Each query SELECTs `geom_json` (the
geometry) plus the columns we want to expose as `properties`.
"""
from __future__ import annotations
import json
from typing import Any

import asyncpg

# Property columns surfaced to the frontend. Keep in sync with the
# Phase 4 GeoJSON examples in the v2 plan §4 (buses + lines).
BUS_PROP_COLS = (
    'bus_id', 'name', 'voltage_kv', 'province', 'island',
    'bus_type', 'p_mw', 'q_mvar', 'is_synthetic', 'data_source',
)
LINE_PROP_COLS = (
    'line_id', 'from_bus', 'to_bus', 'voltage_kv', 'length_km',
    'is_submarine', 'cable_type', 'is_synthetic', 'data_source',
)


def _row_to_feature(row: asyncpg.Record, prop_cols: tuple[str, ...]) -> dict[str, Any]:
    keys = set(row.keys())
    geom = row['geom_json']
    # asyncpg returns ::json as a str — decode once here.
    if isinstance(geom, str):
        geom = json.loads(geom)
    props = {c: row[c] for c in prop_cols if c in keys}
    # Merge any extra columns (e.g. loadflow vm_pu / loading_percent).
    for k in keys:
        if k == 'geom_json' or k in prop_cols:
            continue
        props[k] = row[k]
    return {'type': 'Feature', 'geometry': geom, 'properties': props}


def rows_to_collection(
    rows: list[asyncpg.Record], prop_cols: tuple[str, ...]
) -> dict[str, Any]:
    return {
        'type': 'FeatureCollection',
        'features': [_row_to_feature(r, prop_cols) for r in rows],
    }


# --- SQL fragments ---

# Bus / line SELECT lists. Use ST_AsGeoJSON(geom)::json so PostGIS emits
# proper geometry dicts; we just pass them through.
BUS_SELECT = (
    "SELECT bus_id, name, voltage_kv, province, island, bus_type, "
    "p_mw, q_mvar, is_synthetic, data_source, "
    "ST_AsGeoJSON(geom)::json AS geom_json "
    "FROM buses"
)

LINE_SELECT = (
    "SELECT line_id, from_bus, to_bus, voltage_kv, length_km, "
    "is_submarine, cable_type, is_synthetic, data_source, "
    "ST_AsGeoJSON(geom)::json AS geom_json "
    "FROM lines"
)


async def fetch_buses(conn: asyncpg.Connection, where: str = '', *args) -> list[asyncpg.Record]:
    sql = BUS_SELECT + (f' WHERE {where}' if where else '')
    return await conn.fetch(sql, *args)


async def fetch_lines(conn: asyncpg.Connection, where: str = '', *args) -> list[asyncpg.Record]:
    sql = LINE_SELECT + (f' WHERE {where}' if where else '')
    return await conn.fetch(sql, *args)
