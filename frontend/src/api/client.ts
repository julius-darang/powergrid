// Thin typed-fetch wrapper. The backend returns GeoJSON FeatureCollections
// with mixed bus + line features (geometry.type 'Point' vs 'LineString');
// we narrow at the call site rather than forcing a discriminated union.
import type { components } from './schema.gen'

export type FeatureCollection = components['schemas']['FeatureCollection']
export type Feature = components['schemas']['Feature']
export type ScenariosResponse = components['schemas']['ScenariosResponse']
export type ProvincesResponse = components['schemas']['ProvincesResponse']
export type Health = components['schemas']['Health']

export type ScenarioName = 'off_peak' | 'morning_peak' | 'evening_peak'

// Bus + line property bags, matched against backend BusProperties /
// LineProperties. Spelled out here (rather than imported) because the
// OpenAPI types treat them as `dict[str, Any]` on the Feature — the
// tighter types live in models/schemas.py for documentation; this is
// the runtime contract the map renders against.
export interface BusProps {
  bus_id: string
  name: string | null
  voltage_kv: number
  province: string | null
  island: string | null
  bus_type: string | null
  p_mw: number | null
  q_mvar: number | null
  is_synthetic: boolean
  data_source: string | null
  // /api/loadflow only
  vm_pu?: number | null
  va_degree?: number | null
  convergence_mode?: 'nr' | 'dc' | null
}

export interface LineProps {
  line_id: string
  from_bus: string
  to_bus: string
  voltage_kv: number
  length_km: number | null
  is_submarine: boolean
  cable_type: string | null
  is_synthetic: boolean
  data_source: string | null
  // /api/loadflow only
  loading_percent?: number | null
  p_from_mw?: number | null
  p_to_mw?: number | null
  convergence_mode?: 'nr' | 'dc' | null
}

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${path}: ${r.status} ${r.statusText}`)
  return (await r.json()) as T
}

export const api = {
  transmission: () => getJSON<FeatureCollection>('/api/grid/transmission'),
  // Full system (every bus + line). Used when the layer panel enables
  // distribution at scope=all. ~3 MB raw, ~600 KB gzipped.
  allGrid: () => getJSON<FeatureCollection>('/api/grid/all'),
  loadflow: (s: ScenarioName) => getJSON<FeatureCollection>(`/api/loadflow/${s}`),
  // Province-scoped: sub-transmission + distribution within the province
  // (provinceGrid) or the same with load-flow results joined (provinceLoadflow).
  provinceGrid: (name: string) =>
    getJSON<FeatureCollection>(`/api/grid/province/${encodeURIComponent(name)}`),
  provinceLoadflow: (s: ScenarioName, name: string) =>
    getJSON<FeatureCollection>(`/api/loadflow/${s}/${encodeURIComponent(name)}`),
  // Island-scoped: broader filter (Cebu / Negros / Leyte-Samar / Panay / Bohol).
  islandGrid: (name: string) =>
    getJSON<FeatureCollection>(`/api/grid/island/${encodeURIComponent(name)}`),
  islandLoadflow: (s: ScenarioName, name: string) =>
    getJSON<FeatureCollection>(`/api/loadflow/${s}/island/${encodeURIComponent(name)}`),
  scenarios: () => getJSON<ScenariosResponse>('/api/scenarios'),
  provinces: () => getJSON<ProvincesResponse>('/api/provinces'),
  health: () => getJSON<Health>('/api/health'),
  // Static GeoJSON overlay: PSGC province polygons. Lazy-loaded once
  // when the user first toggles the boundary layer on; cached client-
  // side via the endpoint's max-age=86400.
  provinceBoundaries: () => getJSON<FeatureCollection>('/api/boundaries/provinces'),
}

// Narrowing helpers — useful at the render boundary where mixed
// FeatureCollections need to be split into buses (Points) and lines
// (LineStrings).
export function isBusFeature(f: Feature): boolean {
  return f.geometry?.type === 'Point'
}
export function isLineFeature(f: Feature): boolean {
  return f.geometry?.type === 'LineString'
}
