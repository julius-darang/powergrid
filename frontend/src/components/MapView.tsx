import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L, { type LatLngBounds, type LatLngExpression, type LatLngTuple } from 'leaflet'
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
import type { Selection } from './InspectPanel'

const VISAYAS_CENTER: LatLngExpression = [10.7, 123.6]
const VISAYAS_ZOOM = 7

interface MapViewProps {
  scenario: ScenarioName | 'topology'
  province: string | null
  selection: Selection
  onSelect: (s: Selection) => void
  // Hand the current FeatureCollection back up so the inspect panel can
  // re-resolve the selected feature when mode/province changes.
  onDataChange: (d: FeatureCollection | null) => void
}

export default function MapView({
  scenario, province, selection, onSelect, onDataChange,
}: MapViewProps) {
  const [data, setData] = useState<FeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    let p: Promise<FeatureCollection>
    if (scenario === 'topology') {
      p = province ? api.provinceGrid(province) : api.transmission()
    } else {
      p = province ? api.provinceLoadflow(scenario, province) : api.loadflow(scenario)
    }
    p.then((d) => {
      if (cancelled) return
      setData(d)
      onDataChange(d)
    })
      .catch((e) => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [scenario, province, onDataChange])

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
        preferCanvas={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {lines.map((f) => {
          const id = (f.properties as Record<string, unknown>).line_id as string
          const isSelected = selection?.kind === 'line' && selection.id === id
          return (
            <LineFeature
              key={id}
              f={f}
              mode={mode}
              selected={isSelected}
              onClick={() => onSelect({ kind: 'line', id })}
            />
          )
        })}
        {buses.map((f) => {
          const id = (f.properties as Record<string, unknown>).bus_id as string
          const isSelected = selection?.kind === 'bus' && selection.id === id
          return (
            <BusFeature
              key={id}
              f={f}
              mode={mode}
              selected={isSelected}
              onClick={() => onSelect({ kind: 'bus', id })}
            />
          )
        })}
        <FitToData features={data?.features ?? []} active={Boolean(province)} />
      </MapContainer>
      <StatusOverlay
        loading={loading}
        error={error}
        count={data?.features.length ?? 0}
        province={province}
      />
    </div>
  )
}

function FitToData({ features, active }: { features: Feature[]; active: boolean }) {
  const map = useMap()
  useEffect(() => {
    if (!active) {
      map.setView(VISAYAS_CENTER, VISAYAS_ZOOM)
      return
    }
    const bounds = computeBounds(features)
    if (bounds) map.fitBounds(bounds, { padding: [30, 30] })
  }, [features, active, map])
  return null
}

function computeBounds(features: Feature[]): LatLngBounds | null {
  const pts: LatLngTuple[] = []
  for (const f of features) {
    if (!f.geometry) continue
    if (f.geometry.type === 'Point') {
      const [lon, lat] = (f.geometry as { coordinates: [number, number] }).coordinates
      pts.push([lat, lon])
    } else if (f.geometry.type === 'LineString') {
      for (const [lon, lat] of (f.geometry as { coordinates: [number, number][] }).coordinates) {
        pts.push([lat, lon])
      }
    }
  }
  if (pts.length === 0) return null
  return L.latLngBounds(pts)
}

interface FeatureRenderProps {
  f: Feature
  mode: 'topology' | 'loadflow'
  selected: boolean
  onClick: () => void
}

function BusFeature({ f, mode, selected, onClick }: FeatureRenderProps) {
  const p = f.properties as unknown as BusProps
  const geom = f.geometry as { type: 'Point'; coordinates: [number, number] } | null
  if (!geom) return null
  const [lon, lat] = geom.coordinates
  const base = busStyle(p, mode)
  // Selection ring: thicker stroke + dark outline. Doesn't change fill so
  // the underlying voltage/vm_pu color is still readable.
  const style = selected
    ? { ...base, color: '#0f172a', weight: 3, radius: base.radius + 2 }
    : base
  return (
    <CircleMarker
      center={[lat, lon] as LatLngTuple}
      pathOptions={style}
      radius={style.radius}
      eventHandlers={{ click: onClick }}
    >
      <Tooltip direction="top" sticky>
        <BusTooltip p={p} />
      </Tooltip>
    </CircleMarker>
  )
}

function LineFeature({ f, mode, selected, onClick }: FeatureRenderProps) {
  const p = f.properties as unknown as LineProps
  const geom = f.geometry as { type: 'LineString'; coordinates: [number, number][] } | null
  if (!geom) return null
  const path = geom.coordinates.map(([lon, lat]) => [lat, lon] as LatLngTuple)
  const base = lineStyle(p, mode)
  const style = selected
    ? { ...base, color: '#0f172a', weight: (base.weight ?? 2) + 2, opacity: 1 }
    : base
  return (
    <Polyline positions={path} pathOptions={style} eventHandlers={{ click: onClick }}>
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

function StatusOverlay({
  loading, error, count, province,
}: { loading: boolean; error: string | null; count: number; province: string | null }) {
  return (
    <div style={{
      position: 'absolute', top: 8, right: 8, zIndex: 1000,
      background: 'rgba(255,255,255,0.92)', padding: '6px 10px',
      borderRadius: 6, fontSize: 12, boxShadow: '0 1px 4px rgba(0,0,0,0.15)',
    }}>
      {loading && <span>Loading…</span>}
      {!loading && error && <span style={{ color: '#b91c1c' }}>{error}</span>}
      {!loading && !error && (
        <span>
          {province ? <strong>{province}</strong> : 'Visayas'}
          {' · '}{count.toLocaleString()} features
        </span>
      )}
    </div>
  )
}
