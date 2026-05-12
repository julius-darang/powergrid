# Phase 2 closeout — topology validation + load flow

> Handoff document for Phase 3. Read this before
> [`docs/journal/phase-2-loadflow.md`](../journal/phase-2-loadflow.md);
> the day-by-day journal is archival.

---

## The artifact in one paragraph

Phase 2 produces a working pandapower model of the connected mainland
Visayas (Cebu + Negros + Leyte + Bohol + Samar, 1 230 buses in the
big connected component) and three-scenario load-flow results.
Newton–Raphson converges at off-peak (×0.40, 330 MW); morning and
evening peak load fall back to DC. The pipeline runs end-to-end in
~23 s via `python scripts/run_phase2.py`. The PostGIS loader (2A.1)
is intentionally not part of this chain — no container runtime was
available; it picks up cleanly once Docker / OrbStack is installed.

## What lives where

| File | What it is |
|---|---|
| `backend/data/processed/topology_audit.csv` | 66 connected components — Big component (#0) has 1 230 buses across 5 islands; rest are fragments |
| `backend/data/processed/bus_component_map.csv` | 2 952 rows — `bus_id → component_id` |
| `backend/data/processed/pp_network.json` | Assembled pandapower network: 2 952 buses (1 230 in service), 2 418 lines (1 038 in service), 547 transformers (256 in service), 4 generators, 1 ext_grid slack |
| `backend/data/processed/bus_index_map.csv` | `bus_id ↔ pp_index` for joining results back to canonical IDs |
| `backend/data/processed/load_flow_results.csv` | 7 572 rows — long-format, schema matches `init.sql.load_flow_results` for mechanical PostGIS load |
| `backend/data/processed/load_flow_summary.csv` | 3 rows — per-scenario convergence mode, voltage range, slack import |
| `backend/data/processed/loadflow_audit.csv` | 27 rows — per-(scenario, province) voltage and angle stats |
| `backend/data/processed/loadflow_coverage.csv` | 16 rows — per-province in-service coverage |
| `scripts/run_phase2.py` | Orchestrator — 4 notebooks chained, post-condition assertions |
| `notebooks/12_topology_audit.ipynb` | NetworkX connected-components audit |
| `notebooks/13_pandapower_build.ipynb` | Network build: buses, lines/transformers split, loads, gens, slack |
| `notebooks/14_loadflow.ipynb` | Three-scenario load flow (NR + DC fallback) |
| `notebooks/15_loadflow_audit.ipynb` | Per-province voltage/loading audit |

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
  Slack absorbs the difference (off-peak exports −232 MW, evening
  imports +184 MW).
- **Off-peak NR voltage health is poor.** Negros Occidental
  `vm_pu_min = 0.766` (153/190 buses < 0.95); Cebu `vm_pu_min = 0.823`
  (242/421 < 0.95); Bohol `vm_pu_min = 0.883`. Best: Southern Leyte 0.935.
- **Persistent line overload:** `line_synth_spur_006` from Therma to
  `sub_osm_83` at 138 kV reports 168-180 % loading across all three
  scenarios. Generator export line under-rated (`max_i_ka = 0.7` for
  300 MW gen export). Phase 1 calibration concern.

## Open threads carried into Phase 3

### Convergence and modelling

- **NR convergence cliff at ~0.66 of full load.** Synthetic 13.8 kV
  radial distribution feeders carry `r = 0.4 Ω/km, x = 0.4 Ω/km` —
  cumulative voltage drop pushes the Jacobian into singularity at
  heavy load. Two fix paths: (a) re-calibrate Phase 1 distribution
  impedance downward (likely correct — these are overhead-conductor
  values misapplied to short radial feeders) or (b) accept DC-only
  results for morning / evening peak. Currently doing (b).
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

- **PostGIS loader (2A.1) and GIST query verification (2A.2)
  deferred.** No container runtime available; needs Docker /
  OrbStack install. Pure mechanical work once a runtime exists —
  schema is live in `init.sql`, target row counts known.
- **Empty scaffolding still empty.** `backend/services/`,
  `backend/routers/`, `backend/models/`, `frontend/src/components/`,
  `frontend/src/hooks/`. No FastAPI, no React.

## Resolved during Phase 2

- **HVDC tagging.** Phase 1 closeout said Ormoc south end was
  labelled `bus_type='hvdc'`. Audit found it's actually
  `bus_type='substation'` at 350 kV. No code change — closeout
  carries the correction so future readers don't go looking for a
  field that doesn't exist.

## Where Phase 3 picks up

Two candidate next moves, mutually compatible:

1. **PostGIS loader** (~1 day, was 2A.1). Install Docker /
   OrbStack, run `docker compose up -d db`, write
   `scripts/load_to_postgis.py` to push `buses.csv`, `lines.csv`,
   and `load_flow_results.csv` into the schema. Confirm < 100 ms
   GIST queries. This is mechanical now that the deliverables exist.
2. **Phase 3 FastAPI backend** (per `power-grid-viz-plan-v2.md`
   §4). Endpoints `/api/grid/transmission`,
   `/api/loadflow/{scenario}`, `/api/provinces`. The empty
   `backend/services/` and `backend/routers/` directories are
   waiting. Reads either from the CSVs directly (fast to ship) or
   from PostGIS (correct long-term).

The cleanest sequence is PostGIS first (1) then API (2) — but if the
goal is a runnable end-to-end demo before installing Docker, the API
can read CSVs directly. Picking up either does not invalidate the
other.
