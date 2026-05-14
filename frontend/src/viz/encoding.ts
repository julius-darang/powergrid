// Visual encoding — colors and radii.
// Voltage palette per the v2 plan §Phase 5.
// Load-flow palette: green / yellow / red / dark-red ramp matching the
// plan's loading buckets, plus a divergent bus voltage ramp around 1.0 pu.
import type { BusProps, LineProps } from '../api/client'

// Voltage palette. Exported as an ordered list so the Legend can render
// it without re-stating the values.
export const VOLTAGE_PALETTE: { kv: number; color: string; label: string }[] = [
  { kv: 350, color: '#7c3aed', label: '350 kV (HVDC)' },
  { kv: 230, color: '#e63946', label: '230 kV' },
  { kv: 138, color: '#f4a261', label: '138 kV' },
  { kv: 69,  color: '#2a9d8f', label: '60–69 kV' },
]
export const DISTRIBUTION_COLOR = '#457b9d' // < 35 kV, falls below VOLTAGE_PALETTE

const VOLTAGE_BY_KV: Record<number, string> = Object.fromEntries(
  VOLTAGE_PALETTE.map((v) => [v.kv, v.color]),
)
VOLTAGE_BY_KV[60] = VOLTAGE_BY_KV[69]

export function voltageColor(kv: number): string {
  return VOLTAGE_BY_KV[Math.round(kv)] ?? DISTRIBUTION_COLOR
}

// Line loading buckets per v2 plan: <50, 50-80, 80-100, >100.
export const LOADING_PALETTE: { min: number; color: string; label: string }[] = [
  { min: 0,   color: '#2d6a4f', label: '< 50 %' },
  { min: 50,  color: '#f4a261', label: '50–80 %' },
  { min: 80,  color: '#e63946', label: '80–100 %' },
  { min: 100, color: '#9b2226', label: '> 100 % (overload)' },
]

export function loadingColor(pct: number | null | undefined): string | null {
  if (pct == null || Number.isNaN(pct)) return null
  if (pct >= 100) return '#9b2226'
  if (pct >= 80)  return '#e63946'
  if (pct >= 50)  return '#f4a261'
  return '#2d6a4f'
}

// vm_pu divergent ramp. 1.00 is nominal; under 0.95 / over 1.05 are
// operator concern thresholds.
export const VM_PU_PALETTE: { label: string; color: string }[] = [
  { label: '< 0.85 (severe under)', color: '#7f1d1d' },
  { label: '0.85–0.90',             color: '#dc2626' },
  { label: '0.90–0.95',             color: '#f59e0b' },
  { label: '0.95–1.05 (healthy)',   color: '#16a34a' },
  { label: '1.05–1.10',             color: '#f59e0b' },
  { label: '> 1.10 (severe over)',  color: '#7f1d1d' },
]

export function vmPuColor(vm: number | null | undefined): string | null {
  if (vm == null || Number.isNaN(vm)) return null
  if (vm < 0.85) return '#7f1d1d'
  if (vm < 0.90) return '#dc2626'
  if (vm < 0.95) return '#f59e0b'
  if (vm <= 1.05) return '#16a34a'
  if (vm <= 1.10) return '#f59e0b'
  return '#7f1d1d'
}

// Bus radius: scale by voltage so transmission stands out from sub-tx.
export function busRadius(kv: number): number {
  if (kv >= 230) return 5
  if (kv >= 138) return 4
  if (kv >= 60)  return 3
  return 2
}

// Bus stroke style: hollow circles for synthetic buses per v2 plan §5.
export function busStyle(p: BusProps, mode: 'topology' | 'loadflow') {
  const lf = mode === 'loadflow' ? vmPuColor(p.vm_pu) : null
  const color = lf ?? voltageColor(p.voltage_kv)
  return {
    radius: busRadius(p.voltage_kv),
    color,
    weight: 1,
    fillColor: color,
    fillOpacity: p.is_synthetic ? 0 : 0.85, // hollow for synthetic
  }
}

// Line weight per voltage class.
export function lineWeight(kv: number): number {
  if (kv >= 230) return 2.5
  if (kv >= 138) return 2
  if (kv >= 60)  return 1.5
  return 1
}

export function lineStyle(p: LineProps, mode: 'topology' | 'loadflow') {
  const lf = mode === 'loadflow' ? loadingColor(p.loading_percent) : null
  const color = lf ?? voltageColor(p.voltage_kv)
  const dashed = p.is_synthetic || p.is_submarine
  return {
    color,
    weight: lineWeight(p.voltage_kv),
    opacity: 0.9,
    dashArray: dashed ? '6 4' : undefined,
  }
}
