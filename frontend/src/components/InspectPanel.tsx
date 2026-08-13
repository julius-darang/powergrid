import type { BusProps, Feature, LineProps } from '../api/client'

// Selection is by id, not by feature object — that way the panel
// re-resolves the live feature when the user switches scenarios, so
// vm_pu and loading_percent update without re-clicking.
export type Selection =
  | { kind: 'bus'; id: string }
  | { kind: 'line'; id: string }
  | null

interface InspectPanelProps {
  selection: Selection
  feature: Feature | null   // resolved from the current FeatureCollection
  onClose: () => void
}

export default function InspectPanel({ selection, feature, onClose }: InspectPanelProps) {
  if (!selection) return null
  return (
    <aside className="inspect">
      <div className="inspect-header">
        <strong>{selection.kind === 'bus' ? 'Bus' : 'Line'}</strong>
        <button onClick={onClose} className="inspect-close" aria-label="Close">×</button>
      </div>
      {!feature && (
        <div className="inspect-empty">
          <em>not in current view</em>
          <p>The selected {selection.kind} ({selection.id}) is outside the
            data the map is showing right now — try switching scenario or
            clearing the province filter.</p>
        </div>
      )}
      {feature && selection.kind === 'bus' && (
        <BusDetails p={feature.properties as unknown as BusProps} />
      )}
      {feature && selection.kind === 'line' && (
        <LineDetails p={feature.properties as unknown as LineProps} />
      )}
    </aside>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === '' || (typeof value === 'number' && Number.isNaN(value))) {
    return null
  }
  return (
    <div className="inspect-row">
      <span className="inspect-label">{label}</span>
      <span className="inspect-value">{value}</span>
    </div>
  )
}

function fmt(x: number | null | undefined, digits = 2, suffix = ''): string | null {
  if (x == null || Number.isNaN(x)) return null
  return `${x.toFixed(digits)}${suffix}`
}

function BusDetails({ p }: { p: BusProps }) {
  // vm_pu colored to mirror the map encoding — quick eyeball of voltage
  // health without having to remember which color means what.
  const vmColor =
    p.vm_pu == null ? undefined :
    p.vm_pu < 0.90 ? '#dc2626' :
    p.vm_pu < 0.95 ? '#f59e0b' :
    p.vm_pu <= 1.05 ? '#16a34a' : '#f59e0b'
  return (
    <div className="inspect-body">
      <h3 className="inspect-title">{p.name || p.bus_id}</h3>
      <div className="inspect-id">{p.bus_id}</div>
      <Section title="Topology">
        <Row label="Voltage" value={`${p.voltage_kv} kV`} />
        <Row label="Bus type" value={p.bus_type} />
        <Row label="Province" value={p.province} />
        <Row label="Island" value={p.island} />
      </Section>
      <Section title="Load">
        <Row label="P" value={fmt(p.p_mw, 2, ' MW')} />
        <Row label="Q" value={fmt(p.q_mvar, 2, ' MVAr')} />
      </Section>
      {(p.vm_pu != null || p.va_degree != null) && (
        <Section title="Load flow">
          <Row label="vm_pu" value={
            <span style={{ color: vmColor }}>{fmt(p.vm_pu, 4)}</span>
          } />
          <Row label="va" value={fmt(p.va_degree, 2, '°')} />
          <Row label="Convergence" value={p.convergence_mode?.toUpperCase()} />
        </Section>
      )}
      <Section title="Provenance">
        <Row label="Source" value={p.data_source} />
        <Row label="Synthetic" value={p.is_synthetic ? 'yes' : 'no'} />
      </Section>
    </div>
  )
}

function LineDetails({ p }: { p: LineProps }) {
  const lc =
    p.loading_percent == null ? undefined :
    p.loading_percent >= 100 ? '#9b2226' :
    p.loading_percent >= 80 ? '#e63946' :
    p.loading_percent >= 50 ? '#f4a261' : '#2d6a4f'
  return (
    <div className="inspect-body">
      <h3 className="inspect-title">{p.line_id}</h3>
      <div className="inspect-id">{p.from_bus} → {p.to_bus}</div>
      <Section title="Topology">
        <Row label="Voltage" value={`${p.voltage_kv} kV`} />
        <Row label="Length" value={fmt(p.length_km, 2, ' km')} />
        <Row label="Cable" value={p.cable_type} />
        <Row label="Submarine" value={p.is_submarine ? 'yes' : 'no'} />
      </Section>
      {(p.loading_percent != null || p.p_from_mw != null) && (
        <Section title="Load flow">
          <Row label="Loading" value={
            <span style={{ color: lc }}>{fmt(p.loading_percent, 1, ' %')}</span>
          } />
          <Row label="P from" value={fmt(p.p_from_mw, 2, ' MW')} />
          <Row label="P to" value={fmt(p.p_to_mw, 2, ' MW')} />
          <Row label="Convergence" value={p.convergence_mode?.toUpperCase()} />
        </Section>
      )}
      <Section title="Provenance">
        <Row label="Source" value={p.data_source} />
        <Row label="Synthetic" value={p.is_synthetic ? 'yes' : 'no'} />
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="inspect-section">
      <div className="inspect-section-title">{title}</div>
      {children}
    </div>
  )
}
