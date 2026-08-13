import { useState } from 'react'
import {
  DISTRIBUTION_COLOR, LOADING_PALETTE, VM_PU_PALETTE, VOLTAGE_PALETTE,
} from '../viz/encoding'

interface LegendProps {
  mode: 'topology' | 'loadflow'
}

// Bottom-left legend. Collapsible because it can get long once both
// loading + vm_pu sections are shown. Reads its palettes from
// encoding.ts so they stay in sync with the actual renderers.
export default function Legend({ mode }: LegendProps) {
  const [open, setOpen] = useState(true)

  return (
    <div className={'legend' + (open ? ' open' : '')}>
      <button
        className="legend-toggle"
        onClick={() => setOpen(!open)}
        title={open ? 'Hide legend' : 'Show legend'}
      >
        Legend {open ? '▾' : '▸'}
      </button>
      {open && (
        <div className="legend-body">
          {mode === 'topology' && (
            <Section title="Voltage">
              {VOLTAGE_PALETTE.map((v) => (
                <Row key={v.kv} swatch={<Dot color={v.color} />} label={v.label} />
              ))}
              <Row swatch={<Dot color={DISTRIBUTION_COLOR} />} label="< 35 kV (distribution)" />
            </Section>
          )}

          {mode === 'loadflow' && (
            <>
              <Section title="Bus vm_pu">
                {VM_PU_PALETTE.map((v) => (
                  <Row key={v.label} swatch={<Dot color={v.color} />} label={v.label} />
                ))}
              </Section>
              <Section title="Line loading">
                {LOADING_PALETTE.map((l) => (
                  <Row key={l.label} swatch={<Bar color={l.color} />} label={l.label} />
                ))}
              </Section>
            </>
          )}

          <Section title="Marker conventions">
            <Row
              swatch={<DotHollow color="#0f172a" />}
              label="hollow bus = synthetic"
            />
            <Row
              swatch={<Bar color="#0f172a" dashed />}
              label="dashed line = synthetic or submarine"
            />
          </Section>
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="legend-section">
      <div className="legend-section-title">{title}</div>
      {children}
    </div>
  )
}

function Row({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return (
    <div className="legend-row">
      <span className="legend-swatch">{swatch}</span>
      <span className="legend-label">{label}</span>
    </div>
  )
}

function Dot({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14">
      <circle cx="7" cy="7" r="5" fill={color} stroke={color} strokeWidth="1" />
    </svg>
  )
}

function DotHollow({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14">
      <circle cx="7" cy="7" r="5" fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}

function Bar({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <svg width="22" height="6" viewBox="0 0 22 6">
      <line
        x1="1" y1="3" x2="21" y2="3"
        stroke={color} strokeWidth="2.5"
        strokeDasharray={dashed ? '5 3' : undefined}
      />
    </svg>
  )
}
