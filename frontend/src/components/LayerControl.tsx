import { useState } from 'react'
import type { LayerState } from '../layers'
import { DISTRIBUTION_COLOR, VOLTAGE_PALETTE } from '../viz/encoding'

interface LayerControlProps {
  layers: LayerState
  onChange: (next: LayerState) => void
}

// Map overlay for layer toggles. Top-left position so it doesn't fight
// the legend (bottom-left) or status badge (top-right). Mirrors Open
// Infra Map's layer-toggle UX: each row is a check + swatch + label.
export default function LayerControl({ layers, onChange }: LayerControlProps) {
  const [open, setOpen] = useState(true)
  const set = (k: keyof LayerState, v: boolean) => onChange({ ...layers, [k]: v })

  return (
    <div className={'layer-control' + (open ? ' open' : '')}>
      <button
        className="layer-toggle"
        onClick={() => setOpen(!open)}
        title={open ? 'Hide layers' : 'Show layers'}
      >
        Layers {open ? '▾' : '▸'}
      </button>
      {open && (
        <div className="layer-body">
          <Row
            checked={layers.transmissionLines}
            onChange={(v) => set('transmissionLines', v)}
            swatch={<LineSwatch color={VOLTAGE_PALETTE[1].color} />}
            label="Transmission lines"
            hint="≥ 60 kV overland"
          />
          <Row
            checked={layers.transmissionBuses}
            onChange={(v) => set('transmissionBuses', v)}
            swatch={<DotSwatch color={VOLTAGE_PALETTE[1].color} />}
            label="Transmission buses"
            hint="≥ 60 kV substations"
          />
          <Row
            checked={layers.submarineCables}
            onChange={(v) => set('submarineCables', v)}
            swatch={<LineSwatch color={VOLTAGE_PALETTE[2].color} dashed />}
            label="Submarine cables"
            hint="all voltages"
          />
          <Row
            checked={layers.generators}
            onChange={(v) => set('generators', v)}
            swatch={<DotSwatch color="#ea580c" />}
            label="Generators"
            hint="any voltage"
          />
          <div className="layer-divider" />
          <Row
            checked={layers.distributionLines}
            onChange={(v) => set('distributionLines', v)}
            swatch={<LineSwatch color={DISTRIBUTION_COLOR} />}
            label="Distribution lines"
            hint="< 60 kV — dense, mostly synthetic"
          />
          <Row
            checked={layers.distributionBuses}
            onChange={(v) => set('distributionBuses', v)}
            swatch={<DotSwatch color={DISTRIBUTION_COLOR} />}
            label="Distribution buses"
            hint="< 60 kV — dense, mostly synthetic"
          />
        </div>
      )}
    </div>
  )
}

function Row({
  checked, onChange, swatch, label, hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  swatch: React.ReactNode
  label: string
  hint: string
}) {
  return (
    <label className="layer-row" title={hint}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="layer-swatch">{swatch}</span>
      <span className="layer-label">{label}</span>
    </label>
  )
}

function DotSwatch({ color }: { color: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12">
      <circle cx="6" cy="6" r="4.5" fill={color} stroke={color} strokeWidth="1" />
    </svg>
  )
}

function LineSwatch({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <svg width="18" height="6" viewBox="0 0 18 6">
      <line x1="0" y1="3" x2="18" y2="3"
        stroke={color} strokeWidth="2.5"
        strokeDasharray={dashed ? '4 3' : undefined} />
    </svg>
  )
}
