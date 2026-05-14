# Phase 1 closeout — data foundation

> The handoff document for Phase 2. Read this before opening
> [`docs/journal/phase-1-data.md`](../journal/phase-1-data.md);
> the day-by-day journal is archival.

---

## The artifact in one paragraph

After 20 days (plus the Day 27 recalibration noted below),
Phase 1 produces a single coherent set of CSVs that a Phase 2
load-flow run can consume without further patching:
`buses.csv` (2 959 rows, ~13 % `v1_curated`, ~6 % OSM
transmission, ~80 % synthetic distribution + virtual roots) and
`lines.csv` (2 972 rows, ~6 % OSM transmission, ~93 % synthetic
feeders and v1-derived backbone). Visayas total peak load =
2 282 MW, within 4 % of the published ~2 200 MW. The pipeline
runs end-to-end in ~39 s via `python scripts/run_phase1.py`.

> **Note on row counts.** Original Day 20 handoff produced
> 2 960 / 2 967. The Day 27 feeder-impedance recalibration
> (see "Resolved during post-Phase-1 cleanup" below) shifted
> the substation-merge step's tie-breaker by ~0.2 %, giving
> the current 2 959 / 2 972 numbers. Load total unchanged.

## What lives where

| File                                                 | What it is                                                |
| ---------------------------------------------------- | --------------------------------------------------------- |
| `backend/data/processed/buses.csv`                   | 2 959 rows — the deliverable                              |
| `backend/data/processed/lines.csv`                   | 2 972 rows — the deliverable                              |
| `backend/data/boundaries/psgc_provinces.geojson`     | 16 Visayas provinces with PSGC codes + island tag         |
| `backend/data/boundaries/visayas_islands.geojson`    | 9 dissolved island polygons                               |
| `backend/data/boundaries/province_peak_targets.csv`  | Hand-curated per-province peak demand (anchors Day 20)    |
| `scripts/run_phase1.py`                              | Orchestrator — the only entrypoint for rebuilding         |
| `notebooks/0X_*.ipynb`                               | The chain. Order encoded in `run_phase1.py:NOTEBOOKS`     |
| `backend/db/init.sql`                                | PostGIS schema, live and seeded as of Phase 2 Day 26       |

## Open threads carried into Phase 2

### Topology gaps the load flow will surface

- **Samar fragmentation.** 9 components on 31 buses, untouched by
  Days 17–20. Fix paths: (a) bump `SNAP_M` from 55 m to ~150 m in
  Phase 1B for Samar specifically, or (b) hand-encode the
  Calbayog ↔ Sta. Rita ↔ Paranas 138 kV chain. The 226 untagged
  transmission lines that Phase 1A's audit found in Samar (230 km)
  and Eastern Samar (166 km) likely contain the missing geometry.

  > **Update (Phase 2 audit).** The Phase 2A.3 connected-components
  > scan against the full graph found Samar fragmentation is much
  > worse than this estimate — 14 Samar-only components totalling
  > 290 buses, with 87 more Samar buses joining the big component
  > via Leyte. The "9 components / 31 buses" figure here was
  > measured against an earlier Phase 1 state and never refreshed.
- **Antique isolation.** Only the `sub_synth_antique` virtual root
  from Phase 1C — Antique has no real v1 substation. Mini-grid
  isolated from the transmission graph; load is realistic (55 MW)
  but the topology can't receive power from the rest of the system.
- **Biliran and Siquijor have one substation each, no incident
  lines.** Both submarine-fed in real life; cables not in OSM,
  not in v1. New realistic loads (22 / 15 MW) make the gap visible.
- **Leyte–Luzon HVDC has no north end.** `MAX_OFFSHORE_KM = 5`
  dropped the Luzon terminal in Phase 1B. Ormoc south end is
  labelled `bus_type='hvdc'`. Phase 2 must add an explicit
  external-grid bus connected to Ormoc so the load flow has an
  import path.

  > **Update (Phase 2 audit).** The "labelled `bus_type='hvdc'`"
  > claim was wrong — Phase 2A.3 found Ormoc 350 kV
  > (`sub_milagro_substation_104`) is actually
  > `bus_type='substation'`. Phase 2B added the ext_grid at that
  > bus anyway (`vm_pu=1.02`), so the load flow has its import
  > path.

### Calibration concerns (Phase 2)

- **Sparse provinces under-bus the load.** Capiz / Antique / Aklan
  carry 3.3 / 2.3 / 1.7 MW per distribution bus (vs Cebu 0.78).
  Per-bus totals match province peak; bus *count* is too low for
  realistic topology. Either accept and let load flow show the
  voltage drops, or boost `N_FEEDERS_PER_ROOT` for under-bussed
  provinces. The latter is the right move once Phase 2 confirms
  voltage levels are actually problematic.
- **Per-province peak targets are hand-curated rough estimates.**
  16-row CSV is good enough to anchor Phase 1's order of
  magnitude; Phase 2 calibration should replace it with real
  NGCP / DOE load curves. Most-likely-off: Bohol (tourism-driven,
  swingy), Samar group (sparse data), Cebu (industrial mix
  uncertain).

### Data-quality residuals (not blocking)

- **226 untagged transmission lines** from Phase 1A's audit —
  Samar 230 km, Eastern Samar 166 km, Leyte 73 km, Cebu 27 km.
  Voltage parser drops them; a future pass should snap their
  endpoints to known-voltage substations and inherit voltage.
  Helps Samar fragmentation and Cebu substation-merge problems.
- **9 over-merged substation clusters from Phase 1B.** Acceptable
  for now; revisit if Phase 2 reports lost detail at large
  facilities.
- **The Cebu Day-18 false-positive merges we deliberately didn't
  take.** At `MERGE_KM = 1.0` km we'd have collapsed
  Mandaue + Lapu-Lapu and Ormoc Solar + Ormoc 350 kV HVDC. The
  0.5 km choice was right for data quality. Genuine bay-level
  merges between 0.5 and 1.0 km can only be resolved from NGCP
  single-line diagrams; geometric heuristic at its useful limit.
- **176 self-loops removed in Phase 1B.** 44 % of OSM line input.
  Worth remembering when comparing raw counts.
- **Bohol −17 % area discrepancy** unresolved from Day 2. Anything
  aggregating "Visayas by island" that involves Bohol remains
  suspect until a diagnostic on GADM vs Panglao / satellite-island
  coverage.

### Process residuals

- **Empty scaffolding remains.** `backend/services/`,
  `backend/routers/`, `backend/models/`, `frontend/src/components/`,
  `frontend/src/hooks/` are still empty. Orchestrator made Phase 1
  reliable from notebooks, so promotion is no longer urgent — but
  it remains the right Phase 2 refactor.

  > **Update (Phase 3 Day 27).** Backend scaffolding populated by
  > the Phase 3 FastAPI scaffold (`backend/main.py`,
  > `backend/db/connection.py`, `backend/routers/`,
  > `backend/services/`, `backend/models/`, `backend/tests/`).
  > Frontend dirs still empty — Phase 4 work.

- **No rows in PostGIS.** Schema is live but empty. The loader
  pass reads `buses.csv` / `lines.csv` into Postgres and measures
  the < 100 ms GIST spatial-query rubric against real data.

  > **Update (Phase 2 Day 26).** Resolved. `scripts/load_to_postgis.py`
  > round-trips all three CSVs (buses / lines / load_flow_results)
  > in ~0.6 s; all six benchmarked GIST queries under 100 ms.

---

## Resolved during post-Phase-1 cleanup

- **Two v1 data-tag errors at the source.** `04BABATNGN` was
  tagged `island=Samar` (Babatngon is in Leyte); `08BVISTA` was
  tagged `island=Panay, description="…Iloilo"` (Buena Vista is in
  Guimaras). The Phase 1 spatial join already overrode these in the
  derived CSVs; the upstream `data/buses.csv` is now also correct,
  so source and derived no longer disagree.
- **Silent regression risk in the orchestrator.** `scripts/run_phase1.py`
  used to complete with whatever row counts the chain produced —
  Day 18 lost data this way and nothing caught it. The script now
  asserts `len(buses) ≥ 2 900`, `len(lines) ≥ 2 900`, and per-province
  distribution-load total within ±5 % of `province_peak_targets.csv`.
  Partial runs (`--from` / `--to`) skip the check.
- **Day 27 — Synthetic feeder impedance recalibration.** The
  Phase 2 closeout flagged a Newton–Raphson convergence cliff
  at ~0.66 of full load, traced to synthetic distribution
  feeders using overhead-conductor impedance values
  (`r=x=0.40 Ω/km`) applied to short radial fan-outs at
  13.8 kV. Recalibrated `DIST_R_OHM_PER_KM` to 0.10 and
  `DIST_X_OHM_PER_KM` to 0.15 across the three notebooks that
  generate synthetic distribution
  (`03_synthetic_distribution`, `09_iloilo_redistribution`,
  `10_redistribute_provinces`). After re-running `run_phase1.py`
  and `run_phase2.py`, NR converges for all three scenarios
  (off-peak `vm_pu_min = 0.903`, evening peak 0.743). Row
  counts shifted slightly from substation-merge tie-breakers
  (2 960/2 967 → 2 959/2 972) but load total is unchanged at
  2 282 MW. See [phase-2-loadflow.md Day 27](../journal/phase-2-loadflow.md).

---

## Where Phase 2 picks up

> **Status (post-handoff):** both moves below are now done.
> Phase 2 is closed; Phase 3 has started.
> See [`phase-2-closeout.md`](phase-2-closeout.md) and
> [`phase-3-api.md`](../journal/phase-3-api.md).

Two candidate next moves, mutually compatible:

1. **PostGIS loader** (~1 day). Read the deliverable CSVs into
   Postgres, confirm < 100 ms GIST queries on the example set
   from `power-grid-viz-plan-v2.md` lines 528–542. **Done
   (Phase 2 Day 26)** — `scripts/load_to_postgis.py`, slowest
   query 26 ms median.
2. **Phase 2 topology validation + load flow** (~3–5 days).
   NetworkX connected-components check on the cleaned graph,
   then pandapower newton-raphson. **Done (Phase 2 Days 22–25,
   plus Day 27 recalibration).** All three scenarios NR-converge.

Picking up either does not invalidate the other.
