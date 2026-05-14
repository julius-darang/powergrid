# Phase 2 closeout — topology validation + load flow

> Handoff document for Phase 3. Read this before
> [`docs/journal/phase-2-loadflow.md`](../journal/phase-2-loadflow.md);
> the day-by-day journal is archival.

---

## The artifact in one paragraph

Phase 2 produces a working pandapower model of the connected
mainland Visayas (Cebu + Negros + Leyte + Bohol + Samar — 1 230
buses in the big connected component, out of 2 959 total) and
three-scenario load-flow results. After the Day 27 Phase 1
feeder-impedance recalibration, **Newton–Raphson converges
cleanly for all three scenarios** with no DC fallback —
off-peak `vm_pu_min = 0.903`, morning peak 0.779, evening peak
0.743. The pipeline runs end-to-end in ~23 s via
`python scripts/run_phase2.py`. All deliverables also live in
PostGIS — `scripts/load_to_postgis.py` round-trips the CSVs
into the `buses` / `lines` / `load_flow_results` tables in
~0.6 s and benchmarks the six API access patterns from the v2
plan §3.2; slowest is 26 ms median, well inside the 100 ms
rubric.

## What lives where

| File | What it is |
|---|---|
| `backend/data/processed/topology_audit.csv` | 66 connected components — Big component (#0) has 1 230 buses across 5 islands; rest are fragments |
| `backend/data/processed/bus_component_map.csv` | 2 959 rows — `bus_id → component_id` |
| `backend/data/processed/pp_network.json` | Assembled pandapower network: 2 959 buses (1 230 in service), 2 425 lines (1 038 in service), 547 transformers (256 in service), 4 generators, 1 ext_grid slack |
| `backend/data/processed/bus_index_map.csv` | `bus_id ↔ pp_index` for joining results back to canonical IDs |
| `backend/data/processed/load_flow_results.csv` | 7 536 rows — long-format, all `convergence_mode = 'nr'`, schema matches `init.sql.load_flow_results` |
| `backend/data/processed/load_flow_summary.csv` | 3 rows — per-scenario mode, voltage range, slack import |
| `backend/data/processed/loadflow_audit.csv` | 27 rows — per-(scenario, province) voltage and angle stats |
| `backend/data/processed/loadflow_coverage.csv` | 16 rows — per-province in-service coverage |
| `scripts/run_phase2.py` | Orchestrator — 4 notebooks chained, post-condition assertions |
| `notebooks/12_topology_audit.ipynb` | NetworkX connected-components audit |
| `notebooks/13_pandapower_build.ipynb` | Network build: buses, lines/transformers split, loads, gens, slack |
| `notebooks/14_loadflow.ipynb` | Three-scenario load flow (NR + DC fallback path retained as safety net) |
| `notebooks/15_loadflow_audit.ipynb` | Per-province voltage/loading audit |
| `scripts/load_to_postgis.py` | 2A loader + GIST benchmark — idempotent CSV→DB round-trip |

## Headline numbers

- **Topology fragmentation worse than Phase 1 closeout estimated.** 66
  components, not "a handful". Big component (#0) covers
  Cebu/Negros/Leyte/Bohol/Samar mainland. Panay+Guimaras is its own
  225-bus component (#1) with no working submarine link to Negros.
  Three Cebu-only fragments (#2/3/4 at 205/50/50 buses) — new finding,
  not in the Phase 1 closeout. Samar has 14 small Samar-only fragments
  on top of the 87 buses that joined the big component.
- **Load modelled: 826 MW out of 2 282 MW total** (36 %). 522 MW of
  in-province load sits in disconnected fragments and is not in any
  scenario: Iloilo 250, Capiz 80, Aklan 75, Antique 55, Guimaras 25,
  Biliran 22, Siquijor 15.
- **Generator dispatch (hand-curated):** Therma Visayas 300 MW,
  Tongonan 120, Palinpinon 1 100, Palinpinon 2 80 = 600 MW total.
  Slack at Ormoc 350 kV absorbs the difference: off-peak exports
  −243 MW (Visayas → Luzon), morning peak imports +134 MW, evening
  peak imports +223 MW.
- **Post-recalibration voltage profile** (Day 27 onward). Off-peak
  `vm_pu_min = 0.903` (was 0.766 with the original 0.40/0.40
  feeder impedance). Evening peak `vm_pu_min = 0.743`, with
  Negros Occidental at 100 % of buses under 0.95 — operationally
  stressed, but the Jacobian solves cleanly. The collapse is a
  real engineering signal (NegOcc has no local generation —
  Palinpinon×2 is in NegOr, Therma is in Cebu) rather than a
  numerical artifact.
- **Persistent line overload:** `line_synth_spur_006` from Therma to
  `sub_osm_83` at 138 kV reports 180–195 % loading across all three
  scenarios. Generator export line under-rated (`max_i_ka = 0.7` for
  300 MW gen export ≈ 167 MVA capacity). Phase 1 calibration
  concern; independent of feeder impedance.

## Open threads carried into Phase 3

### Convergence and modelling

- ~~**NR convergence cliff at ~0.66 of full load.**~~ **RESOLVED on Day 27.**
  Recalibrated `DIST_R_OHM_PER_KM` 0.40→0.10 and `DIST_X_OHM_PER_KM`
  0.40→0.15 across the three Phase 1 synthetic-feeder notebooks
  (03, 09, 10). NR now converges for all three scenarios with no
  DC fallback. Evening-peak `vm_pu_min` = 0.743 — operationally
  stressed but well above the Jacobian-singularity threshold.
  See Phase 2 journal Day 27.
- **522 MW of load not in the load flow** because their host components
  are disconnected. Real-world fixes are not in Phase 2 scope:
  Panay–Negros submarine cable needs reconstruction (Phase 1 had it
  but as a fragment), Biliran/Siquijor submarine feeds aren't in OSM.
- **Generator dispatch is a 4-row hand-estimate.** Phase 3 calibration
  should replace with real NGCP DDP or DOE numbers. Cebu likely
  needs more local generation (additional plants: CEDC, KSPC, others
  not tagged `bus_type=generator` in Phase 1).
- **Transformer sn_mva is generous defaults** (75/150/300 MVA by HV
  tier). Right-size if Phase 3 audits show transformers running below
  20 % loaded everywhere.
- **Submarine cable max_i_ka = 0.645** may underrate the actual
  cables — but most reported overloads sit on synthetic spur lines,
  not submarine cables, so this is lower priority.

### Phase 1 calibration concerns that became visible in Phase 2

- **Phase 1 closeout numbers were stale.** Audit found 66 components,
  not the "Samar 9 components / 31 buses" the closeout described.
  Phase 1's connectivity claims were measured before the Day 18+
  redistribution / merge work and weren't refreshed.
- **Synthetic distribution feeder impedance** as above — the single
  largest convergence blocker.
- **Phase 1 didn't model transformers** at all. Phase 2B fabricated
  547 of them inline (any `lines.csv` row with cross-voltage
  endpoints became a transformer). A Phase 1 refactor would add a
  `transformers.csv` deliverable and remove the inline conversion.

### Process

- ~~**Empty backend scaffolding.**~~ **RESOLVED on Day 27 by the
  Phase 3 scaffold.** `backend/main.py`, `backend/db/connection.py`,
  `backend/routers/{grid,analysis}.py`, `backend/services/geo.py`,
  `backend/models/schemas.py`, `backend/tests/test_api.py` now
  populated. Nine endpoints live and verified. See
  [phase-3-api.md Day 27](../journal/phase-3-api.md).
- **Empty frontend scaffolding.** `frontend/src/components/`,
  `frontend/src/hooks/` still empty. No React, no Leaflet.
  Phase 4 work.

## Resolved during Phase 2

- **HVDC tagging.** Phase 1 closeout said Ormoc south end was
  labelled `bus_type='hvdc'`. Audit found it's actually
  `bus_type='substation'` at 350 kV. No code change — closeout
  carries the correction so future readers don't go looking for a
  field that doesn't exist.
- **Phase 1 closeout's deferred PostGIS loader.** OrbStack
  installed; container runs; `scripts/load_to_postgis.py` round-
  trips all three CSVs and benchmarks the six API access patterns.
  The single slowest query (`province_filter_lines_via_buses` —
  `lines JOIN buses` with `OR` on `from_bus`/`to_bus`) is ~26 ms
  median. The KNN nearest-bus query is sub-millisecond.
  `init.sql` now also includes the `convergence_mode` column on
  `load_flow_results` (Phase 2 added it inline; now it's in the
  canonical schema for future container starts).
- **NR convergence cliff at ~0.66 of full load.** Day 27 Phase 1
  recalibration lowered `DIST_R_OHM_PER_KM` (0.40 → 0.10) and
  `DIST_X_OHM_PER_KM` (0.40 → 0.15) across the three synthetic-
  distribution notebooks. NR now converges for all three scenarios;
  the DC fallback path is unused. Off-peak `vm_pu_min` improved
  from 0.766 to 0.903. See
  [phase-2-loadflow.md Day 27](../journal/phase-2-loadflow.md).
- **Phase 3 FastAPI scaffold.** Built in parallel with the Day 27
  recalibration via dispatched subagent. Nine endpoints
  (`/api/health`, `/api/scenarios`, `/api/provinces`,
  `/api/grid/{transmission,province/...,island/...,viewport}`,
  `/api/loadflow/{scenario,scenario/province}`), all verified
  end-to-end with curl + pytest. Two integration bugs fixed
  (`DISTINCT` over `json` columns; bogus `in_service_bus_count`
  filter). See [phase-3-api.md Day 27](../journal/phase-3-api.md).

## Where Phase 3 picks up

**Phase 3 has already started** — the FastAPI scaffold landed on
Day 27 alongside the Phase 1 recalibration. Nine endpoints live,
two pytest sanity tests passing, all six benchmarked access
patterns powered by `ST_AsGeoJSON(geom)::json` direct from
PostGIS.

The remaining Phase 3 threads:

1. **Frontend (Phase 4 of v2 plan).** React + Leaflet consuming
   the API. The empty `frontend/src/{components,hooks}/`
   directories are next.
2. **API tightening.** Pydantic schemas are loose
   (`properties: dict[str, Any]`) so FastAPI doesn't re-validate
   3 000+ features per request — once the frontend pins what
   it actually consumes, narrow the schemas for `/docs`.
3. **Export endpoints** (`/api/export/{png,pdf}`). Deferred per
   the v2 plan; Phase 5 polish.
4. **CORS tightening.** Allow-all currently; pin to the frontend
   host once Phase 4 lands.
5. **Pagination.** `/api/loadflow/evening_peak` returns 5 931
   features in one ~3 MB payload. Fine for dev; revisit if
   response size becomes a real concern.

Parallel calibration threads worth flagging:

- ~~**Therma export spur (`line_synth_spur_006`)** at 180–195 %
  loading.~~ **RESOLVED on Day 28.** `SPUR_OVERRIDES` table in
  notebook 13 §3a bumps `max_i_ka` 0.7 → 1.5; loading dropped to
  ~84 % across all scenarios. Phase 2 journal Day 28.
- ~~**NegOcc local generation.**~~ **Partially resolved on Day 28.**
  Added Helios solar (150 MW) and Bacolod biomass (80 MW) at
  `sub_osm_80` and `v1_06bacolod`. NegOcc evening_peak min `vm_pu`
  0.743 → 0.829; buses < 0.95 went from 100 % to 63 %. Closeout's
  100–200 MW estimate was light — 230 MW lifts NegOcc out of acute
  undervoltage but not above 0.95. Pushing further needs scenario-
  specific gen dispatch (Helios at 150 MW is unrealistic at evening
  peak — PV output is near zero). Phase 2 journal Day 28.
