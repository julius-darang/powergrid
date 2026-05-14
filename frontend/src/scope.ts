// Map scope — what region of the grid the map is currently rendering.
// One unified type so the header (island dropdown), sidebar (province
// list), and MapView all agree on what's active. Changing one
// dimension clears the other: picking a province replaces an island
// selection, picking an island replaces a province selection.
export type Scope =
  | { kind: 'all' }
  | { kind: 'island'; name: string }
  | { kind: 'province'; name: string }
