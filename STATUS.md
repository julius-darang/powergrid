---
name: powergrid
description: Philippine grid viz — development paused; React + Leaflet frontend and PostGIS/FastAPI/pandapower stack
domain: engineering
status: dormant
stack: PostGIS · FastAPI · pandapower · React + Vite + react-leaflet · Docker
entry: scripts/run_phase1.py · scripts/run_phase2.py  (NEVER run notebooks individually) · frontend/ (npm run dev · npm run build)
has_repo: true
updated: 2026-08-16
---

# powergrid

## State
Phases 1–3 done: data foundation, topology + load flow, and FastAPI (9 endpoints,
PostGIS, pytest green). **Phase 4 frontend is underway** — the Vite + React +
react-leaflet walking skeleton in `frontend/` includes typed API access, scenario
switching, layer controls, boundary filtering, inspection panels, and voltage/load-flow
encodings. A production build is present in `frontend/dist/`.
Known debt: Pydantic schemas off `dict[str, Any]`, CORS allow-all, 522 MW stranded islands.

## Next action
Paused. Do not spend current focus here. When reactivated, resume by running the
frontend/backend integration checks, then harden CORS and prepare deployment.

## Conventions
- `archive/pi-skills/grid-data-provenance/` — the same sourced/pypsa-ph/estimate rule as visayasgrid.
- **Hard rule** (from `AGENTS.md`): never run notebooks individually for Phase 1/2 — use `scripts/run_phase*.py`.

## Pointers
- Anchor: `AGENTS.md` (read first). Phase status: `docs/journal/README.md`.
- Frontend: `frontend/` (`npm run dev` / `npm run build`) and its `README.md`.
- Pipeline: `scripts/run_phase1.py`, `scripts/run_phase2.py`, `scripts/load_to_postgis.py`.
- Own `.git` (origin `github.com/julius-darang/powergrid`). Branch `master`.