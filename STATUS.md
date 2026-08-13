---
name: powergrid
description: Philippine grid viz — heavy stack (PostGIS + FastAPI + pandapower), backend + pipeline done, frontend not started
domain: engineering
status: incubating
stack: PostGIS · FastAPI · pandapower · Jupyter pipeline · Docker
entry: scripts/run_phase1.py · scripts/run_phase2.py  (NEVER run notebooks individually)
has_repo: true
updated: 2026-07-31
---

# powergrid

## State
Phases 1–3 done: data foundation, topology + load flow, FastAPI (9 endpoints, PostGIS,
pytest green). **Phase 4 frontend (React + Leaflet) not started** — `frontend/src/` is empty.
Known debt: Pydantic schemas off `dict[str, Any]`, CORS allow-all, 522 MW stranded islands.

## Next action
Phase 4 — scaffold the React + Leaflet frontend in `frontend/src/`. Until that's underway
this project is incubating, not active.

## Conventions
- `.pi/skills/grid-data-provenance/` — the same sourced/pypsa-ph/estimate rule as visayasgrid.
- **Hard rule** (from `AGENTS.md`): never run notebooks individually for Phase 1/2 — use `scripts/run_phase*.py`.

## Pointers
- Anchor: `AGENTS.md` (read first). Phase status (drifts): `docs/journal/README.md`.
- Pipeline: `scripts/run_phase1.py`, `scripts/run_phase2.py`, `scripts/load_to_postgis.py`.
- Own `.git` (origin `github.com/julius-darang/powergrid`). Branch `master`.