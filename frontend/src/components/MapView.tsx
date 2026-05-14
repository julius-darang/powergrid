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
import type { Scope } from '../scope'
import { showBus, showLine, type LayerState } from '../layers'
import Legend from './Legend'
import BoundaryLayer from './BoundaryLayer'
import LayerControl from './LayerControl'

const VISAYAS_CENTER: LatLngExpression = [10.7, 123.6]
const VISAYAS_ZOOM = 7

interface MapViewProps {
  scenario: ScenarioName | 'topology'
  scope: Scope
  showBoundaries: boolean
  layers: LayerState
  onLayersChange: (next: LayerState) => void
  selection: Selection
  onSelect: (s: Selection) => void
  // Hand the current FeatureCollection back up so the inspect panel can
  // re-resolve the selected feature when mode/scope changes.
  onDataChange: (d: FeatureCollection | null) => void
}

export default function MapView({
  scenario, scope, showBoundaries, layers, onLayersChange,
  selection, onSelect, onDataChange,
}: MapViewProps) {
  const [data, setData] = useState<FeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // At scope=all + topology, the transmission endpoint is much cheaper
  // (~150 KB gz vs ~600 KB for /api/grid/all). Only fall back to the
  // full endpoint when the user actually needs distribution features.
  const needsFull = layers.distributionLines || layers.distributionBuses

  // Endpoint picker — six cases for loadflow (scope=all/island/province
  // × scenario), plus all|full split for topology.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const p: Promise<FeatureCollection> = (() => {
      if (scenario === 'topology') {
        if (scope.kind === 'province') return api.provinceGrid(scope.name)
        if (scope.kind === 'island')   return api.islandGrid(scope.name)
        return needsFull ? api.allGrid() : api.transmission()
      }
      if (scope.kind === 'province') return api.provinceLoadflow(scenario, scope.name)
      if (scope.kind === 'island')   return api.islandLoadflow(scenario, scope.name)
      return api.loadflow(scenario)
    })()
    p.then((d) => {
      if (cancelled) return
      setData(d)
      onDataChange(d)
    })
      .catch((e) => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [scenario, scope, needsFull, onDataChange])

  // Split features and apply the layer filter in one pass. Layer
  // changes are cheap because they're a JS-side filter — no refetch.
  const { buses, lines, visibleCount } = useMemo(() => {
    if (!data) return { buses: [], lines: [], visibleCount: 0 }
    const buses: Feature[] = []
    const lines: Feature[] = []
    for (const f of data.features) {
      if (isBusFeature(f)) {
        if (showBus(f, layers)) buses.push(f)
      } else if (isLineFeature(f)) {
        if (showLine(f, layers)) lines.push(f)
      }
    }
    return { buses, lines, visibleCount: buses.length + lines.length }
  }, [data, layers])

  const mode = scenario === 'topology' ? 'topology' : 'loadflow'

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <MapContainer
        center={VISAYAS_CENTER}
        zoom={VISAYAS_ZOOM}
        style={{ width: '100%', height: '100%' }}
        preferCanvas={true}
      >
        {/* CartoDB Positron — no labels, no roads, no POIs. Coastlines and
            water only. Free with attribution. Hosted via fastly. */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        <BoundaryLayer
          visible={showBoundaries}
          highlight={scope.kind === 'province' ? scope.name : null}
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
        <FitToData features={data?.features ?? []} active={scope.kind !== 'all'} />
      </MapContainer>
      <LayerControl layers={layers} onChange={onLayersChange} />
      <StatusOverlay
        loading={loading}
        error={error}
        count={visibleCount}
        total={data?.features.length ?? 0}
        scope={scope}
      />
      <Legend mode={mode} />
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
  loading, error, count, total, scope,
}: { loading: boolean; error: string | null; count: number; total: number; scope: Scope }) {
  const label = scope.kind === 'all' ? 'Visayas' : scope.name
  const hidden = total - count
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
          {scope.kind === 'all' ? label : <strong>{label}</strong>}
          {' · '}{count.toLocaleString()} shown
          {hidden > 0 && <span style={{ color: '#64748b' }}> · {hidden.toLocaleString()} hidden</span>}
        </span>
      )}
    </div>
  )
}
