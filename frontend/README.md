# Frontend — Phase 4 walking skeleton

Vite + React + TypeScript + react-leaflet. Renders the FastAPI backend's
GeoJSON onto a Leaflet/OSM base map with voltage coloring (topology mode)
or load-flow coloring (per-scenario `vm_pu` on buses, `loading_percent`
on lines).

## Dev

```
cd frontend
npm install            # TypeScript 5.9 keeps the ESLint/tooling peers aligned
npm run dev            # serves on http://localhost:5173
```

The Vite dev server proxies `/api/*` to `http://localhost:8000`, so the
backend needs to be running locally for data to load. Start it from the
repo root:

```
uvicorn backend.main:app --port 8000
```

## API types

The backend returns mixed GeoJSON FeatureCollections. The frontend keeps a
small local response contract in `src/api/client.ts` and narrows bus and line
properties at the render boundary. Update that contract when backend response
models change; runtime requests remain ordinary typed fetches.

## Layout

```
src/
├── api/
│   └── client.ts       typed fetch wrappers + local response contract
├── components/
│   └── MapView.tsx     react-leaflet canvas + Polyline/CircleMarker render
├── viz/
│   └── encoding.ts     voltage / vm_pu / loading-percent color & style
├── App.tsx             header + scenario toggle
└── App.css             full-bleed layout
```

## Visual encoding

| Class | Color | Source |
|---|---|---|
| Voltage 350 kV | `#7c3aed` (HVDC violet) | encoding.ts |
| Voltage 230 kV | `#e63946` | v2 plan |
| Voltage 138 kV | `#f4a261` | v2 plan |
| Voltage 60–69 kV | `#2a9d8f` | v2 plan |
| Loading > 100 % | `#9b2226` | v2 plan |
| Loading 80–100 % | `#e63946` | v2 plan |
| `vm_pu` < 0.90 | `#dc2626` | undervoltage |
| `vm_pu` < 0.95 | `#f59e0b` | marginal |
| `vm_pu` 0.95–1.05 | `#16a34a` | healthy |

Synthetic buses render hollow (`fillOpacity: 0`); synthetic + submarine
lines render dashed (`dashArray: '6 4'`) per the v2 plan §Phase 5.
