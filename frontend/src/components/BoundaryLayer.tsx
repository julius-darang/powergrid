import { useEffect, useState } from 'react'
import { GeoJSON } from 'react-leaflet'
import type { Feature as GJFeature, FeatureCollection as GJFeatureCollection, MultiPolygon, Polygon } from 'geojson'
import L from 'leaflet'
import { api } from '../api/client'

// PSGC province polygon overlay. Lazy-loaded — the GeoJSON is ~1.5 MB
// gzipped, so we don't fetch until the user toggles boundaries on.
// Subsequent re-toggles hit the in-memory cache here.

interface BoundaryLayerProps {
  visible: boolean
  highlight: string | null  // province name to highlight (or null)
}

let cached: GJFeatureCollection<Polygon | MultiPolygon> | null = null

export default function BoundaryLayer({ visible, highlight }: BoundaryLayerProps) {
  const [data, setData] = useState<GJFeatureCollection<Polygon | MultiPolygon> | null>(cached)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!visible || cached) return
    let cancelled = false
    // The API returns a backend Pydantic FeatureCollection; geojson types
    // are stricter (e.g. require coordinate arrays). Cast through unknown.
    ;(api.provinceBoundaries() as unknown as Promise<GJFeatureCollection<Polygon | MultiPolygon>>)
      .then((d) => {
        if (cancelled) return
        cached = d
        setData(d)
      })
      .catch((e) => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [visible])

  if (!visible || !data) {
    if (error) console.warn('boundary load failed:', error)
    return null
  }

  return (
    <GeoJSON
      // Key on highlight so react-leaflet rebuilds the layer when
      // selection changes (the GeoJSON style prop is read at create time
      // and is sticky otherwise).
      key={highlight ?? ''}
      data={data}
      style={(f: GJFeature | undefined) => {
        const name = (f?.properties as { province?: string } | undefined)?.province ?? ''
        const isHi = highlight === name
        return {
          color: isHi ? '#1e3a8a' : '#475569',
          weight: isHi ? 2.5 : 1,
          opacity: isHi ? 0.9 : 0.5,
          fillColor: isHi ? '#1e3a8a' : '#94a3b8',
          fillOpacity: isHi ? 0.08 : 0.03,
          // No event handlers — these are purely visual context. The
          // sidebar drives province selection.
          interactive: false,
        } as L.PathOptions
      }}
    />
  )
}
