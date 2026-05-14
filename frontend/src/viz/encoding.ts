// Visual encoding — colors and radii.
// Voltage palette per the v2 plan §Phase 5.
// Load-flow palette: green / yellow / red / dark-red ramp matching the
// plan's loading buckets, plus a divergent bus voltage ramp around 1.0 pu.
import type { BusProps, LineProps } from '../api/client'

const VOLTAGE_COLOR: Record<number, string> = {
  350: '#7c3aed',  // 350 kV HVDC: violet (extra-high)
  230: '#e63946',
  138: '#f4a261',
  69:  '#2a9d8f',
  60:  '#2a9d8f',
}

const DEFAULT_COLOR = '#457b9d' // distribution / unknown

export function voltageColor(kv: number): string {
  return VOLTAGE_COLOR[Math.round(kv)] ?? DEFAULT_COLOR
}

// Loading buckets per v2 plan: <50, 50-80, 80-100, >100.
export function loadingColor(pct: number | null | undefined): string | null {
  if (pct == null || Number.isNaN(pct)) return null
  if (pct >= 100) return '#9b2226'
  if (pct >= 80)  return '#e63946'
  if (pct >= 50)  return '#f4a261'
  return '#2d6a4f'
}

// vm_pu divergent ramp. 1.00 is nominal; under 0.95 / over 1.05 are
// operator concern thresholds.
export function vmPuColor(vm: number | null | undefined): string | null {
  if (vm == null || Number.isNaN(vm)) return null
  if (vm < 0.85) return '#7f1d1d'   // severe undervoltage
  if (vm < 0.90) return '#dc2626'   // undervoltage
  if (vm < 0.95) return '#f59e0b'   // marginal under
  if (vm <= 1.05) return '#16a34a'  // healthy
  if (vm <= 1.10) return '#f59e0b'  // marginal over
  return '#7f1d1d'                  // severe overvoltage
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

// Line weight per voltage class. Submarine cables get the dashArray
// treatment elsewhere (synthetic too — dashed stroke per v2 plan).
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
