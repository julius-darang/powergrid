"""/api/boundaries/* — static GeoJSON overlays (province + island polygons).

Files live in `backend/data/boundaries/` and are bundled with the app —
not in PostGIS because they're never spatially joined; the frontend
just renders them as polygon overlays. Loaded once at module import,
served from memory.
"""
from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

router = APIRouter(prefix='/api/boundaries', tags=['boundaries'])

DATA_DIR = Path(__file__).resolve().parent.parent / 'data' / 'boundaries'

# Pre-load into memory. ~6 MB each; fine for a single-process dev server.
# In production this would move to a CDN or static asset host.
_PROVINCES_BYTES: bytes | None = None
_ISLANDS_BYTES: bytes | None = None


def _load(name: str) -> bytes:
    path = DATA_DIR / name
    if not path.exists():
        raise HTTPException(500, f'boundary file missing: {name}')
    # Round-trip through json.dumps to drop pretty-printing whitespace.
    obj = json.loads(path.read_text())
    return json.dumps(obj, separators=(',', ':')).encode('utf-8')


@router.get('/provinces')
async def provinces_geojson():
    """PSGC province polygons (FeatureCollection of MultiPolygons).

    Each feature has properties: psgc_code, province, region, island_name.
    Cached aggressively — provinces don't change without a code release.
    """
    global _PROVINCES_BYTES
    if _PROVINCES_BYTES is None:
        _PROVINCES_BYTES = _load('psgc_provinces.geojson')
    return Response(
        content=_PROVINCES_BYTES,
        media_type='application/geo+json',
        headers={'Cache-Control': 'public, max-age=86400, immutable'},
    )


@router.get('/islands')
async def islands_geojson():
    """Visayas island polygons. Same shape, broader coverage units."""
    global _ISLANDS_BYTES
    if _ISLANDS_BYTES is None:
        _ISLANDS_BYTES = _load('visayas_islands.geojson')
    return Response(
        content=_ISLANDS_BYTES,
        media_type='application/geo+json',
        headers={'Cache-Control': 'public, max-age=86400, immutable'},
    )
