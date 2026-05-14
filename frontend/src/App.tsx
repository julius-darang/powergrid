import { useCallback, useMemo, useState } from 'react'
import MapView from './components/MapView'
import Sidebar from './components/Sidebar'
import InspectPanel, { type Selection } from './components/InspectPanel'
import type { Feature, FeatureCollection, ScenarioName } from './api/client'
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
  const [province, setProvince] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection>(null)
  const [data, setData] = useState<FeatureCollection | null>(null)

  // Resolve the live feature for the inspect panel from the current
  // FeatureCollection. Selection is stored by id, so swapping scenarios
  // updates vm_pu / loading_percent without re-clicking.
  const selectedFeature = useMemo<Feature | null>(() => {
    if (!selection || !data) return null
    const key = selection.kind === 'bus' ? 'bus_id' : 'line_id'
    return data.features.find(
      (f) => (f.properties as Record<string, unknown>)[key] === selection.id,
    ) ?? null
  }, [selection, data])

  const handleDataChange = useCallback((d: FeatureCollection | null) => setData(d), [])

  return (
    <div className="app-root">
      <header className="app-header">
        <h1>Philippine Power Grid · Visayas</h1>
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
      </header>
      <div className="app-body">
        <Sidebar selected={province} onSelect={setProvince} />
        <main className="app-map">
          <MapView
            scenario={mode}
            province={province}
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
