"""Pydantic v2 schemas — the wire contract the Phase 4 frontend pins against.

The GeoJSON endpoints return mixed bus+line FeatureCollections; rather than
force a discriminated union (which would require adding a `kind` field and
breaking shape), we type the bus and line property bags as separate models
and let the frontend narrow by geometry.type at the call site. The smaller
endpoints (health, scenarios, provinces) use full response_model validation.
"""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ScenarioName = Literal['off_peak', 'morning_peak', 'evening_peak']
ConvergenceMode = Literal['nr', 'dc']


Geometry = dict[str, Any]  # GeoJSON geometry — PostGIS hands us the dict


class BusProperties(BaseModel):
    """Properties on a bus Feature (geometry.type == 'Point').

    Load-flow fields are present only on /api/loadflow/* responses and are
    None for buses outside the connected component for a given scenario.
    """
    model_config = ConfigDict(extra='forbid')

    bus_id: str
    name: str | None = None
    voltage_kv: float
    province: str | None = None
    island: str | None = None
    bus_type: str | None = None
    p_mw: float | None = None
    q_mvar: float | None = None
    is_synthetic: bool
    data_source: str | None = None

    # Load-flow join columns (present on /api/loadflow/*)
    vm_pu: float | None = None
    va_degree: float | None = None
    convergence_mode: ConvergenceMode | None = None


class LineProperties(BaseModel):
    """Properties on a line Feature (geometry.type == 'LineString')."""
    model_config = ConfigDict(extra='forbid')

    line_id: str
    from_bus: str
    to_bus: str
    voltage_kv: float
    length_km: float | None = None
    is_submarine: bool
    cable_type: str | None = None
    is_synthetic: bool
    data_source: str | None = None

    # Load-flow join columns
    loading_percent: float | None = None
    p_from_mw: float | None = None
    p_to_mw: float | None = None
    convergence_mode: ConvergenceMode | None = None


class Feature(BaseModel):
    type: Literal['Feature'] = 'Feature'
    geometry: Geometry | None
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal['FeatureCollection'] = 'FeatureCollection'
    features: list[Feature]


class Scenario(BaseModel):
    name: ScenarioName
    mode: ConvergenceMode | None = Field(
        None, description="Convergence mode actually used for this scenario."
    )


class ScenariosResponse(BaseModel):
    scenarios: list[Scenario]


class ProvinceInfo(BaseModel):
    name: str
    island: str | None
    bus_count: int
    in_service_bus_count: int
    total_load_mw: float
    in_service_load_mw: float
    osm_buses: int
    synthetic_buses: int


class ProvincesResponse(BaseModel):
    provinces: list[ProvinceInfo]


class HealthCounts(BaseModel):
    buses: int
    lines: int
    load_flow_results: int


class Health(BaseModel):
    status: Literal['ok']
    db_version: str | None = None
    postgis_version: str | None = None
    counts: HealthCounts
