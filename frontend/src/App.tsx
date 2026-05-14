import { useCallback, useEffect, useMemo, useState } from 'react'
import MapView from './components/MapView'
import Sidebar from './components/Sidebar'
import InspectPanel, { type Selection } from './components/InspectPanel'
import { api, type Feature, type FeatureCollection, type ProvincesResponse, type ScenarioName } from './api/client'
import { type Scope } from './scope'
import './App.css'

type Mode = 'topology' | ScenarioName

const MODES: { value: Mode; label: string; help: string }[] = [
  { value: 'topology',     label: 'Topology',     help: 'Transmission >= 60 kV, voltage-colored' },
  { value: 'off_peak',     label: 'Off-peak',     help: 'Load flow @ off-peak' },
  { value: 'morning_peak', label: 'Morning peak', help: 'Load flow @ morning peak' },
  { value: 'evening_peak', label: 'Evening peak', help: 'Load flow @ evening peak (highest load)' },
]

export default function App() {
  const [mode, setMode] = useState<Mode>('topology')
  const [scope, setScope] = useState<Scope>({ kind: 'all' })
  const [showBoundaries, setShowBoundaries] = useState<boolean>(false)
  const [selection, setSelection] = useState<Selection>(null)
  const [data, setData] = useState<FeatureCollection | null>(null)

  // Province metadata fetched once at app load. Powers both the
  // sidebar (grouped list) and the header (island dropdown derived
  // from the unique islands), and lets the header subtitle resolve
  // a selected province's island.
  const [provinces, setProvinces] = useState<ProvincesResponse['provinces'] | null>(null)
  useEffect(() => {
    let cancelled = false
    api.provinces()
      .then((d) => { if (!cancelled) setProvinces(d.provinces) })
      .catch(() => { /* sidebar surfaces the error */ })
    return () => { cancelled = true }
  }, [])

  const islands = useMemo(() => {
    if (!provinces) return [] as string[]
    return Array.from(new Set(provinces.map((p) => p.island).filter(Boolean))).sort() as string[]
  }, [provinces])

  // Re-resolve the selected feature against the live FeatureCollection so
  // the inspect panel updates vm_pu / loading_percent on mode change.
  const selectedFeature = useMemo<Feature | null>(() => {
    if (!selection || !data) return null
    const key = selection.kind === 'bus' ? 'bus_id' : 'line_id'
    return data.features.find(
      (f) => (f.properties as Record<string, unknown>)[key] === selection.id,
    ) ?? null
  }, [selection, data])

  const handleDataChange = useCallback((d: FeatureCollection | null) => setData(d), [])

  // Synthetic counts (current view) — drives the disclaimer badge.
  const syntheticStats = useMemo(() => {
    if (!data) return { synthetic: 0, total: 0 }
    let synth = 0
    for (const f of data.features) {
      if ((f.properties as Record<string, unknown>).is_synthetic) synth++
    }
    return { synthetic: synth, total: data.features.length }
  }, [data])

  return (
    <div className="app-root">
      <header className="app-header">
        <div className="app-title">
          <h1>Philippine Power Grid</h1>
          <span className="app-subtitle">
            Visayas · {mode === 'topology' ? 'topology' : `${MODES.find((m) => m.value === mode)?.label.toLowerCase()} load flow`}
            {scope.kind !== 'all' && <> · <strong>{scope.name}</strong></>}
          </span>
        </div>

        <div className="header-controls">
          <SyntheticBadge {...syntheticStats} />

          <label className="boundaries-toggle" title="Show PSGC province polygons">
            <input
              type="checkbox"
              checked={showBoundaries}
              onChange={(e) => setShowBoundaries(e.target.checked)}
            />
            <span>Boundaries</span>
          </label>

          <label className="island-filter" title="Filter map to one island">
            <span>Island:</span>
            <select
              value={scope.kind === 'island' ? scope.name : ''}
              onChange={(e) => {
                const v = e.target.value
                setScope(v ? { kind: 'island', name: v } : { kind: 'all' })
              }}
            >
              <option value="">All Visayas</option>
              {islands.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </label>

          <div className="scenario-switch" role="radiogroup" aria-label="Scenario">
            {MODES.map((m) => (
              <button
                key={m.value}
                role="radio"
                aria-checked={mode === m.value}
                title={m.help}
                className={mode === m.value ? 'active' : ''}
                onClick={() => setMode(m.value)}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
      </header>
      <div className="app-body">
        <Sidebar
          provinces={provinces}
          scope={scope}
          onSelect={(name) => setScope(name ? { kind: 'province', name } : { kind: 'all' })}
        />
        <main className="app-map">
          <MapView
            scenario={mode}
            scope={scope}
            showBoundaries={showBoundaries}
            selection={selection}
            onSelect={setSelection}
            onDataChange={handleDataChange}
          />
        </main>
        <InspectPanel
          selection={selection}
          feature={selectedFeature}
          onClose={() => setSelection(null)}
        />
      </div>
    </div>
  )
}

function SyntheticBadge({ synthetic, total }: { synthetic: number; total: number }) {
  if (total === 0) return null
  const pct = (synthetic / total) * 100
  // Threshold: fade the badge for tiny synthetic minorities (< 5 %).
  // The Visayas dataset is ~50 % synthetic at evening_peak so the
  // badge is almost always loud.
  const level = pct >= 25 ? 'high' : pct >= 5 ? 'mid' : 'low'
  return (
    <span
      className={'synthetic-badge synthetic-' + level}
      title="Some elements are synthetic (population-weighted distribution feeders, hand-curated spurs). Synthetic buses render hollow; synthetic lines render dashed. See BUILD_JOURNAL for the data provenance."
    >
      ⚠ {pct.toFixed(0)}% synthetic
    </span>
  )
}
