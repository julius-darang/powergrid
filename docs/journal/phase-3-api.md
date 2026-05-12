# Phase 3 — FastAPI backend

> Day-by-day narrative for Phase 3. Starts from the Phase 2
> handoff in [`../closeouts/phase-2-closeout.md`](../closeouts/phase-2-closeout.md).
> Closeout: `../closeouts/phase-3-closeout.md` (to be written at
> the end of Phase 3).

## Inputs from Phase 2

- PostGIS live at `localhost:5432` with `buses` (2 959 rows),
  `lines` (2 972), `load_flow_results` (7 536; all
  `convergence_mode='nr'` after Day 27 recalibration).
- Six GIST query patterns benchmarked and under 100 ms — these
  are exactly the access patterns the API needs.

## Goals

Per `power-grid-viz-plan-v2.md` §4: serve GeoJSON + load-flow
JSON to a future Leaflet frontend. Skip the PNG / PDF export
endpoints until Phase 5 polish.

## Days

### Day 27 — API scaffold

Phase 3 ran in parallel with the Phase 1 recalibration (Day 27
in the Phase 2 journal). A dispatched subagent wrote the
scaffold while the recalibration thread updated Phase 1
impedance values and re-ran both pipelines.

#### What landed

```
backend/main.py                 # FastAPI app + asyncpg lifespan + CORS
backend/db/connection.py        # asyncpg pool, init/close/acquire
backend/models/schemas.py       # Pydantic v2 response shapes
backend/services/geo.py         # SQL fragments + GeoJSON helpers
backend/routers/grid.py         # /api/grid/*
backend/routers/analysis.py     # /api/loadflow/*, /api/provinces,
                                # /api/scenarios, /api/health
backend/tests/test_api.py       # pytest sanity tests via TestClient
```

The agent worked entirely in the previously-empty `backend/`
scaffolding — zero overlap with the Track A Phase 1
recalibration that was running concurrently in `notebooks/`
and `scripts/`.

#### Architecture decisions

- **`asyncpg`** for DB access (already in `requirements.txt`).
  Single global pool opened in FastAPI's `lifespan`. Modest
  size (min 1, max 8) — single-process dev server.
- **`ST_AsGeoJSON(geom)::json`** in every query — PostGIS
  emits proper geometry dicts; we never build geometries
  Python-side. The helper in `backend/services/geo.py`
  decodes the JSON if asyncpg returns it as a string.
- **Single FeatureCollection** per endpoint with buses + lines
  mixed; the frontend filters by `geometry.type` or by
  property keys (`bus_id` vs `line_id`). Alternative was
  `{buses: FC, lines: FC}`; the v2 plan §4 examples use the
  flat shape.
- **Loose Pydantic models.** `properties: dict[str, Any]` —
  routers return raw dicts so FastAPI doesn't re-validate
  every feature on every response. Schemas exist mainly for
  `/docs` and future tightening.
- **`LEFT JOIN` to `load_flow_results`** in the loadflow
  endpoints — buses outside the connected big component
  (~58 % of all buses, per the Phase 2 audit) still appear
  as features with `vm_pu: null`. The frontend can colour
  them differently.
- **CORS allow-all** with a TODO comment. Tighten once the
  Phase 4 frontend has a known host.

#### Endpoints

| Path | Returns |
|---|---|
| `GET /api/health` | DB version, PostGIS version, table counts |
| `GET /api/scenarios` | 3 scenarios + each scenario's convergence mode |
| `GET /api/provinces` | Per-province bus_count, in_service_bus_count, total_load_mw |
| `GET /api/grid/transmission` | Buses + lines with voltage_kv ≥ 60 kV |
| `GET /api/grid/province/{name}` | All buses + lines for a province |
| `GET /api/grid/island/{name}` | Same, keyed on island |
| `GET /api/grid/viewport?minlon=&minlat=&maxlon=&maxlat=` | Bbox-clipped buses + lines |
| `GET /api/loadflow/{scenario}` | All buses + lines joined to load-flow results |
| `GET /api/loadflow/{scenario}/{province}` | Same, province-filtered |

#### Bugs fixed at integration

The subagent worked in a sandbox that blocked `pip` and
`uvicorn` execution, so it couldn't run its own tests. Two
issues surfaced on integration:

1. **`DISTINCT` over `json` column** — Postgres has no
   equality operator for `json` (only `jsonb`), so plain
   `SELECT DISTINCT ... ST_AsGeoJSON(geom)::json` fails with
   `could not identify an equality operator for type json`.
   Fix: `DISTINCT ON (l.line_id)` to dedupe by the identity
   column. Two endpoints affected (`/api/grid/province/{name}`,
   `/api/grid/island/{name}`); both now work.
2. **`in_service_bus_count` filter on `bus_type !=
   'out_of_service'`** — never true; `bus_type` is one of
   `distribution`/`substation`/`tower`/`generator`. The
   in-service flag lives only in pandapower, not in the DB.
   Fix: derive in-service from membership in
   `load_flow_results` — `LEFT JOIN load_flow_results r ON
   r.bus_id = b.bus_id AND r.scenario = 'evening_peak'`,
   count distinct `r.bus_id`.

Both fixes inline; no architectural changes needed.

#### Verification

```
$ .venv/bin/pytest backend/tests/
============================== 2 passed in 0.96s ===============================

$ curl http://127.0.0.1:8000/api/health
{"status":"ok","counts":{"buses":2959,"lines":2972,"load_flow_results":7536}}

$ curl http://127.0.0.1:8000/api/grid/transmission | jq '.features | length'
437

$ curl http://127.0.0.1:8000/api/grid/viewport?minlon=123.4&minlat=9.4&maxlon=124.5&maxlat=11.4
features: 2544

$ curl http://127.0.0.1:8000/api/loadflow/evening_peak/Cebu | …
features: 1985, vm_pu min=0.847 max=1.000
```

The Cebu evening-peak `vm_pu_min` of 0.847 matches the Phase 2
audit's per-province table exactly — the API and the audit
read the same data through different paths and agree.

#### Open threads for Phase 3 continuation

- **No `/api/export/{png,pdf}` endpoints.** Deferred to Phase
  5 polish per the v2 plan. The CORS-allow-all setup also
  needs tightening once the frontend exists.
- **OpenAPI / `/docs` review.** FastAPI auto-generates from
  the Pydantic schemas, but the schemas are loose
  (`properties: dict`). Worth a tightening pass once the
  frontend pins its expectations.
- **No pagination.** `/api/loadflow/evening_peak` returns
  5 931 features in one payload. Fine for dev; consider
  cursoring or filtering before production.
- **Persistent line overload at `line_synth_spur_006`** —
  not an API concern but the API will faithfully report
  loading_percent ≈ 195 % on that one line until Phase 1
  right-sizes the Therma export spur's `max_i_ka`.