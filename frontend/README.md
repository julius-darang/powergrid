# Frontend — Phase 4 walking skeleton

Vite + React + TypeScript + react-leaflet. Renders the FastAPI backend's
GeoJSON onto a Leaflet/OSM base map with voltage coloring (topology mode)
or load-flow coloring (per-scenario `vm_pu` on buses, `loading_percent`
on lines).

## Dev

```
cd frontend
npm install            # legacy peer deps OK; Vite scaffold pinned ts ~6.0
npm run dev            # serves on http://localhost:5173
```

The Vite dev server proxies `/api/*` to `http://localhost:8000`, so the
backend needs to be running locally for data to load. Start it from the
repo root:

```
uvicorn backend.main:app --port 8000
```

## API types — codegen

The frontend pins against the backend's OpenAPI schema. Whenever a
response_model or path changes:

```
npm run codegen        # backend must be running on :8000
```

The generated file lives at `src/api/schema.gen.ts` (gitignored — regenerate
on clone). Hand-written wrappers in `src/api/client.ts` give the runtime
contract for bus / line property bags.

## Layout

```
src/
├── api/
│   ├── client.ts       typed fetch wrappers + BusProps/LineProps shape
│   └── schema.gen.ts   openapi-typescript output (gitignored)
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
