"""Pydantic v2 response schemas. Kept loose — properties are dict[str, Any]."""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field


Geometry = dict[str, Any]  # GeoJSON geometry — PostGIS hands us the dict


class Feature(BaseModel):
    type: Literal['Feature'] = 'Feature'
    geometry: Geometry | None
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal['FeatureCollection'] = 'FeatureCollection'
    features: list[Feature]


class Scenario(BaseModel):
    name: str
    mode: str | None = Field(None, description="'nr' or 'dc' — convergence mode")


class ProvinceInfo(BaseModel):
    name: str
    island: str | None
    bus_count: int
    in_service_bus_count: int
    total_load_mw: float
    osm_buses: int
    synthetic_buses: int


class Health(BaseModel):
    status: str
    db_version: str | None = None
    postgis_version: str | None = None
    counts: dict[str, int]
