// What layers the map renders. Filters live in the renderer (MapView),
// the toggle UI lives in LayerControl, and the state is owned by App
// so other components (status overlay, future export) can read it.
//
// Default state is "transmission only" — high-voltage backbone +
// generators + submarine cables. Distribution feeders are dense and
// largely synthetic; they're opt-in via the layer panel.
import type { BusProps, Feature, LineProps } from './api/client'

export interface LayerState {
  transmissionLines: boolean   // voltage_kv >= 60 (non-submarine)
  transmissionBuses: boolean   // voltage_kv >= 60 (non-generator)
  distributionLines: boolean   // voltage_kv < 60
  distributionBuses: boolean   // voltage_kv < 60 (non-generator)
  generators: boolean          // bus_type === 'generator', any voltage
  submarineCables: boolean     // is_submarine === true, any voltage
}

export const DEFAULT_LAYERS: LayerState = {
  transmissionLines: true,
  transmissionBuses: true,
  distributionLines: false,
  distributionBuses: false,
  generators: true,
  submarineCables: true,
}

const TRANSMISSION_KV_MIN = 60

export function showBus(f: Feature, layers: LayerState): boolean {
  const p = f.properties as unknown as BusProps
  if (p.bus_type === 'generator') return layers.generators
  if (p.voltage_kv >= TRANSMISSION_KV_MIN) return layers.transmissionBuses
  return layers.distributionBuses
}

export function showLine(f: Feature, layers: LayerState): boolean {
  const p = f.properties as unknown as LineProps
  if (p.is_submarine) return layers.submarineCables
  if (p.voltage_kv >= TRANSMISSION_KV_MIN) return layers.transmissionLines
  return layers.distributionLines
}
