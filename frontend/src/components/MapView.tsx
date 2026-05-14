import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { LatLngExpression, LatLngTuple } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import {
  api,
  isBusFeature,
  isLineFeature,
  type BusProps,
  type Feature,
  type FeatureCollection,
  type LineProps,
  type ScenarioName,
} from '../api/client'
import { busStyle, lineStyle } from '../viz/encoding'

// Visayas extent — these are the four corners of the region the data
// covers. Centring here lets the map open with the whole grid in view.
const VISAYAS_CENTER: LatLngExpression = [10.7, 123.6]
const VISAYAS_ZOOM = 7

interface MapViewProps {
  scenario: ScenarioName | 'topology'
}

export default function MapView({ scenario }: MapViewProps) {
  const [data, setData] = useState<FeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Re-fetch whenever the scenario flips. Topology mode uses the
  // /transmission endpoint (60 kV+); load-flow mode pulls the full
  // /loadflow/{scenario} with vm_pu / loading_percent joined in.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const p = scenario === 'topology' ? api.transmission() : api.loadflow(scenario)
    p.then((d) => { if (!cancelled) setData(d) })
      .catch((e) => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [scenario])

  // Split features once per data change. Buses render as CircleMarkers,
  // lines as Polylines — the FeatureCollection is mixed so we narrow
  // by geometry.type here.
  const { buses, lines } = useMemo(() => {
    if (!data) return { buses: [], lines: [] }
    return {
      buses: data.features.filter(isBusFeature),
      lines: data.features.filter(isLineFeature),
    }
  }, [data])

  const mode = scenario === 'topology' ? 'topology' : 'loadflow'

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <MapContainer
        center={VISAYAS_CENTER}
        zoom={VISAYAS_ZOOM}
        style={{ width: '100%', height: '100%' }}
        preferCanvas={true}  /* Canvas renderer scales past SVG limits */
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {lines.map((f) => <LineFeature key={featureKey(f)} f={f} mode={mode} />)}
        {buses.map((f) => <BusFeature key={featureKey(f)} f={f} mode={mode} />)}
      </MapContainer>
      <StatusOverlay loading={loading} error={error} count={data?.features.length ?? 0} />
    </div>
  )
}

function featureKey(f: Feature): string {
  const p = f.properties as Record<string, unknown>
  return (p.bus_id as string) ?? (p.line_id as string) ?? Math.random().toString()
}

function BusFeature({ f, mode }: { f: Feature; mode: 'topology' | 'loadflow' }) {
  const p = f.properties as unknown as BusProps
  const geom = f.geometry as { type: 'Point'; coordinates: [number, number] } | null
  if (!geom) return null
  const [lon, lat] = geom.coordinates
  const style = busStyle(p, mode)
  return (
    <CircleMarker center={[lat, lon] as LatLngTuple} pathOptions={style} radius={style.radius}>
      <Tooltip direction="top" sticky>
        <BusTooltip p={p} />
      </Tooltip>
    </CircleMarker>
  )
}

function LineFeature({ f, mode }: { f: Feature; mode: 'topology' | 'loadflow' }) {
  const p = f.properties as unknown as LineProps
  const geom = f.geometry as { type: 'LineString'; coordinates: [number, number][] } | null
  if (!geom) return null
  const path = geom.coordinates.map(([lon, lat]) => [lat, lon] as LatLngTuple)
  const style = lineStyle(p, mode)
  return (
    <Polyline positions={path} pathOptions={style}>
      <Tooltip sticky>
        <LineTooltip p={p} />
      </Tooltip>
    </Polyline>
  )
}

function BusTooltip({ p }: { p: BusProps }) {
  return (
    <div style={{ fontSize: 12, lineHeight: 1.4 }}>
      <div><strong>{p.name || p.bus_id}</strong></div>
      <div>{p.voltage_kv} kV · {p.province ?? '—'}</div>
      {p.p_mw != null && <div>load: {p.p_mw.toFixed(1)} MW</div>}
      {p.vm_pu != null && <div>vm_pu: {p.vm_pu.toFixed(3)}</div>}
      {p.is_synthetic && <div style={{ color: '#92400e' }}>⚠ synthetic</div>}
    </div>
  )
}

function LineTooltip({ p }: { p: LineProps }) {
  return (
    <div style={{ fontSize: 12, lineHeight: 1.4 }}>
      <div><strong>{p.line_id}</strong></div>
      <div>{p.voltage_kv} kV · {p.length_km?.toFixed(1) ?? '?'} km</div>
      {p.loading_percent != null && <div>loading: {p.loading_percent.toFixed(0)} %</div>}
      {p.is_submarine && <div>submarine cable</div>}
      {p.is_synthetic && <div style={{ color: '#92400e' }}>⚠ synthetic</div>}
    </div>
  )
}

function StatusOverlay({ loading, error, count }: { loading: boolean; error: string | null; count: number }) {
  return (
    <div style={{
      position: 'absolute', top: 8, right: 8, zIndex: 1000,
      background: 'rgba(255,255,255,0.92)', padding: '6px 10px',
      borderRadius: 6, fontSize: 12, boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
    }}>
      {loading && <span>Loading…</span>}
      {!loading && error && <span style={{ color: '#b91c1c' }}>{error}</span>}
      {!loading && !error && <span>{count.toLocaleString()} features</span>}
    </div>
  )
}
