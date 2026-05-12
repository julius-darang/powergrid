# Phase 2 — Topology validation + load flow

> Day-by-day narrative for Phase 2. Starts from the Phase 1
> handoff in [`../closeouts/phase-1-closeout.md`](../closeouts/phase-1-closeout.md).
> Closeout: [`../closeouts/phase-2-closeout.md`](../closeouts/phase-2-closeout.md).

## Inputs from Phase 1

- `backend/data/processed/buses.csv` — 2 952 rows
- `backend/data/processed/lines.csv` — 2 965 rows
- `backend/db/init.sql` — PostGIS schema, live but empty

(Phase 1's closeout reported 2 960 / 2 967; the Day 21 voltage
inheritance pass shifted the counts slightly. The journal carries
the actual figures.)

## Goals (as set at the start of Phase 2)

Per `power-grid-viz-plan-v2.md` Phase 2:

1. **Topology validation gate.** NetworkX connected-components
   check on the cleaned graph. Document remaining gaps from the
   Phase 1 closeout.
2. **Load flow.** pandapower Newton–Raphson on the assembled
   network. Add external-grid bus at Ormoc HVDC south to provide
   an import path.
3. **Voltage / loading audit.** Surface the under-bussed sparse
   provinces (Capiz, Antique, Aklan) called out in the Phase 1
   closeout.

## What actually happened (one-line scan)

- The audit found 66 components, not the "handful" the Phase 1
  closeout implied.
- Phase 1 didn't model transformers; Phase 2B fabricated 547 of
  them inline.
- Phase 1 didn't dispatch generators; Phase 2B added 600 MW of
  hand-curated dispatch.
- Newton–Raphson converges at ~40 % load and diverges above ~66 %.
  Three-scenario delivery uses NR for off-peak, DC fallback for
  morning / evening peak.

---

## Day 22 — Plan, topology audit, decisions

### Setting the table

Phase 1 closed with a single-paragraph artifact summary and a list
of open threads. The natural Phase 2 question — *proceed straight
to load flow, or do a final evaluation first?* — resolved in two
turns: the closeout *is* the evaluation, so proceed; but plan first.

The Phase 2 plan landed in the Claude plan file (outside the
repo). Four sub-phases over an expected 5–6 days:

- **2A.** PostGIS loader + topology audit (~1.5 days).
- **2B.** pandapower assembly + topology gate (~1.5 days).
- **2C.** Newton–Raphson + three scenarios + persistence (~2 days).
- **2D.** Voltage / loading audit + closeout (~1 day).

Then the first obstacle: no container runtime on this machine.
No `docker`, no `podman`, no `colima`, no Docker Desktop, no
OrbStack, no native `psql`. 2A.1 (the loader) and 2A.2 (GIST
query verification) are blocked until something is installed.

Two paths surfaced. Path A: install OrbStack, keep plan order.
Path B: reorder — do the load flow first (which is in-memory and
needs only the CSVs), defer the DB work until a runtime exists.
Path B is strategically better — the load flow is what Phase 2 is
trying to de-risk, and the DB loader was first only on the
assumption Docker was already running. **Default to B.** That
puts 2A.1/2A.2 at the tail and surfaces them as deferred items in
the closeout.

### 2A.3 — Topology audit

[`notebooks/12_topology_audit.ipynb`](../../notebooks/12_topology_audit.ipynb)
is a single-purpose audit. Build a NetworkX `MultiGraph` from
`buses.csv` (nodes) and `lines.csv` (edges, with `voltage_kv` and
`is_submarine` carried through), compute connected components, and
emit a per-component table to
`backend/data/processed/topology_audit.csv`.

The graph: 2 952 nodes, 2 965 edges. The component count was a
surprise — **66 components**, where Phase 1's closeout had implied
"Samar fragmentation: 9 components / 31 buses" and treated the
rest as connected. The size histogram:

```
 1 230 buses ×   1 component   ← the big one
   225        ×   1            ← Panay + Guimaras
   205        ×   1            ← Cebu only
    50        ×   2            ← Cebu only
    30        ×   1
    26        ×   1
    25        ×  22            ← Phase 1C synthetic radials
    24        ×   2
    23        ×   3
    22        ×   4
    21        ×   5
    20        ×   4
    19        ×   7
    18        ×   2
     7        ×   1
     5        ×   1
     2        ×   7
     1        ×   1            ← tower_0096 in Bohol, degree 0
```

The headline checks against the Phase 1 closeout's named threads:

- **Big component #0 (1 230 buses)** spans Cebu (421), Negros (308),
  Leyte (232), Bohol (182), and Samar (87) — the submarine-connected
  mainland backbone. Five islands joined into one electrical block.
  This is the closest the closeout's "single connected Visayas"
  hope ever gets.
- **Component #1 (225 buses)** is Panay + Guimaras: Iloilo 158,
  Capiz 25, Aklan 21, Guimaras 21. **Not connected to #0.** The
  Negros–Panay submarine cable that real grids have is missing
  from the model. *Antique is not in this component* — Antique
  has its own component (closeout-flagged).
- **Three Cebu-only fragments** (#2, #3, #4 at 205 / 50 / 50 buses).
  *New finding.* The closeout didn't flag internal Cebu
  fragmentation; the audit measures it for the first time. 305
  Cebu buses sit outside #0 on the same physical island as #0's
  421 Cebu buses, on subgraphs that have no path to the rest.
- **Antique:** one component of 25 buses, isolated. ✓ matches
  closeout.
- **Biliran / Siquijor:** one component each (19 / 22 buses).
  Internally connected via their Phase 1C synthetic feeder, but
  isolated from the mainland — the submarine cables are not in
  OSM or v1.
- **HVDC:** the closeout said the Ormoc south terminal was tagged
  `bus_type='hvdc'`. Audit found zero buses with that tag — Ormoc
  is `bus_type='substation'` at 350 kV. Not a code change, but
  Phase 2's slack assignment can't key off the tag.
- **Isolated buses (degree 0):** one (`tower_0096`, Bohol).

The audit also writes
`backend/data/processed/bus_component_map.csv` (one row per bus,
maps to `component_id`), which Phase 2B reads to mark buses
outside #0 as `in_service=False`.

### Decisions from the audit

Two slack-bus options surfaced — "Ormoc 350 kV HVDC south"
(closeout-recommended) vs "Cebu South substation" (geographically
central). The defaults baked into the plan: Ormoc, `vm_pu=1.02`,
tag fragments `in_service=False` rather than dropping them.
Confirmed; proceed to 2B.

---

## Day 23 — Pandapower build, transformer crisis, generator dispatch

### First attempt: lines straight through

[`notebooks/13_pandapower_build.ipynb`](../../notebooks/13_pandapower_build.ipynb)
starts at `pp.create_empty_network(f_hz=60)` and walks
`buses.csv` and `lines.csv` straight into `net.bus` and
`net.line`. Every bus is added; `in_service` is `True` iff the
audit placed it in component 0 (1 230 of 2 952). Every line is
added; `in_service` requires both endpoints in service.

The slack lands at `sub_milagro_substation_104` (Ormoc 350 kV)
with `vm_pu = 1.02`, representing the Luzon import via HVDC.
Topology gate via `pp.topology.unsupplied_buses`: zero
unsupplied, one in-service component of 1 230 — matches the
audit. Save to `pp_network.json`.

First `pp.runpp(..., algorithm='nr')`: **does not converge after
10 iterations.** Bumped to 50 iterations, tried `init='dc'`,
tried tighter and looser tolerances. Nothing worked. DC works
fine (`pp.rundcpp`) — converges and reports max line loading
of 159 % and angle spread of −35° to 0°.

That gap between "DC works" and "NR fails" is informative. DC
ignores voltage magnitudes and reactive flow; if those quantities
are well-defined the system should solve, but if `vm_pu` collapses
the Jacobian becomes singular.

Diagnostic: dump the line table grouped by `(v_from, v_to)`:

```
v_from  v_to   count
13.8    13.8    2 258
138.0   13.8      344
        138.0      76
69.0    13.8       63
230.0   13.8       62
69.0    69.0       34
230.0   230.0      34
        138.0      18
...
```

**547 lines connect buses at different voltages.** That's the
problem. A 138 kV substation does not connect to a 13.8 kV bus
by a line — it connects through a transformer. Phase 1 stored
the connection as a `lines.csv` row anyway, which is fine as a
graph representation but wrong for power-flow physics. With no
voltage step-down, pandapower expects 138 kV and 13.8 kV buses
to sit at the same `vm_pu`, which is impossible, hence the
Jacobian fails.

### Recovery: split lines into lines + transformers

Three options surfaced for the user (paths A / B / C): fabricate
transformers in Phase 2B (cheapest, doesn't touch Phase 1 CSVs),
DC-only Phase 2 (loses `vm_pu`), stop and add transformers to
Phase 1 (cleanest but ~half-day). **Default: A.**

The notebook gets a new §3 / §3a / §3b structure:

- **§3** classifies every `lines.csv` row as same-voltage or
  cross-voltage using a `voltage_kv` map from `buses.csv`.
- **§3a** creates `pp.create_line_from_parameters` for the
  2 418 same-voltage rows, unchanged from the original build.
- **§3b** creates `pp.create_transformer_from_parameters` for
  the 547 cross-voltage rows. The higher-voltage endpoint is
  the `hv_bus`; the lower is `lv_bus`. Impedance uses sensible
  defaults — `vk_percent = 12`, `vkr_percent = 0.5`,
  `pfe_kw = 50`, `i0_percent = 0.1`. `sn_mva` scales with HV
  tier:

  | HV side | `sn_mva` |
  |---|---:|
  | 350 kV | 300 |
  | 230 kV | 150 |
  | 138 kV |  75 |
  | 69 / 60 kV |  30 |

The point is generosity — Phase 2 doesn't know the real
transformer ratings, but oversizing prevents transformer
loading from bottlenecking the load flow. Phase 2D can
right-size if any are running below 20 %.

Re-run. NR: still fails.

### Second crisis: no generator dispatch

The convergence test scans load scaling. At `×0.25` (206 MW)
NR works (`vm_pu` 0.82–1.02). At `×0.50` it fails. So
somewhere between 25 % and 50 % of full load there's a
convergence cliff.

Looking at `buses.csv`: five buses with `bus_type='generator'`,
all in big-component component 0 except Nabas (in Panay
component #1, out of service). All five have `p_mw = NaN`.
Phase 1 identified the generators but didn't dispatch them.

Without local injection, the slack at Ormoc has to push 826 MW
through cascading submarine cables to reach Cebu, Negros,
Bohol, Samar. That's neither physically possible nor
numerically stable. The DC top-10 line loading at full load
flags `line_synth_spur_006` from Therma Visayas to its
substation at 168 % loading; submarine cables Maasin–Tugas at
192 %, Ubay–Tugas at 182 %.

The fix: a `§4a` cell with hand-curated generator dispatch.
Plausible peak numbers for Visayas plants:

| Generator | Plant | `p_mw` |
|---|---|---:|
| `v1_05therma` (Cebu) | Therma Visayas | 300 |
| `v1_04tongona` (Leyte) | Tongonan geothermal | 120 |
| `v1_06pgpp1` (Negros Oriental) | Palinpinon unit 1 | 100 |
| `v1_06pgpp2` (Negros Oriental) | Palinpinon unit 2 | 80 |
| **Total local injection** | | **600** |

`pp.create_gen` with `vm_pu=1.0`, `slack=False`. The 826 MW
load minus 600 MW local gen leaves 226 MW + losses for the
Ormoc slack to import — close to real-world dispatch shape
for Visayas under Luzon import.

Re-run NR at full load: **still fails.** Re-run with
`gen_p_mw` boosted to 1 050 MW and then 1 230 MW: still fails.
Re-run with load at `×0.90`: fails. At `×0.70`: fails.

Bisect:

```
NR convergence cliff between 0.653 (works) and 0.660 (fails)
At factor=0.653125: vm_pu min=0.457
```

At 65 % load the worst bus voltage is **0.457 pu** — clear
voltage collapse. The Jacobian becomes singular around there.
There's no amount of generator dispatch that fixes this:
local generation reduces the cable transit, but the radial
distribution feeders themselves have impedance high enough
that cumulative drops on long branches push voltages below
the solvability threshold.

The synthetic feeders use `r = 0.4 Ω/km`, `x = 0.4 Ω/km`.
These are overhead-conductor values, applied to short radial
spans carrying tens of MW. The drops accumulate. That's a
Phase 1 calibration concern, which Phase 2 will document but
not fix.

---

## Day 24 — Three scenarios, NR + DC fallback

The plan called for three operating scenarios: morning_peak
(0.85), evening_peak (0.95), off_peak (0.40). Per the bisect,
only off-peak sits below the convergence cliff. Decision:
**NR where it converges, DC fallback where it doesn't.** This
matches the plan's explicit fallback option.

[`notebooks/14_loadflow.ipynb`](../../notebooks/14_loadflow.ipynb)
loads `pp_network.json`, scales `net.load.p_mw` and
`net.load.q_mvar` by the scenario factor, runs `pp.runpp`, and
on `LoadflowNotConverged` re-loads the network and runs
`pp.rundcpp` instead. Generators are *not* scaled — they stay
at their build-time dispatch, and the slack absorbs the
difference (negative slack at off-peak = net export).

Per-scenario summary:

| Scenario | Factor | Mode | Wall | Load (MW) | Gen | Slack | `vm_pu` min–max | Max line load |
|---|---:|---|---:|---:|---:|---:|---|---:|
| off_peak | 0.40 | nr | 0.03 s | 330 | 600 | −232 | 0.766–1.020 | 179.5 % |
| morning_peak | 0.85 | dc | 0.32 s | 702 | 600 | +102 | — | 169.7 % |
| evening_peak | 0.95 | dc | 0.33 s | 784 | 600 | +184 | — | 168.6 % |

Off-peak comes in well below the unity-voltage benchmark — even
at 40 % of peak load, the worst bus sits at 0.766 pu, which
means real undervoltage is showing through. That's not a
solver artifact; that's the synthetic-feeder impedance issue
showing up at the lightest operating point we can solve.

Worth flagging: `line_synth_spur_006` (Therma Visayas →
`sub_osm_83`) shows 179 % loading even at off-peak. That's a
generator export line undersized for the gen dispatch
(`max_i_ka = 0.7` on the line, ~167 MVA, but Therma is
dispatched at 300 MW). Phase 1 wasn't sized for a 300 MW
local injection at that bus; Phase 2's hand-curated gen
exceeds the spur's rating. Phase 2D will surface it.

### Persistence

The plan was to push results into `init.sql.load_flow_results`,
but with DB deferred we write to
`backend/data/processed/load_flow_results.csv` instead. **Schema
matches the table exactly** — same column names, same null
conventions — so the eventual `COPY FROM` is mechanical:

```
scenario, bus_id, line_id, vm_pu, va_degree, loading_percent,
p_from_mw, p_to_mw, convergence_mode
```

For bus rows `bus_id` is set and `line_id` is null; vice versa
for line / transformer rows. `convergence_mode` is `'nr'` or
`'dc'` per scenario. Total: 3 scenarios × (1 230 bus rows
+ 1 294 line+trafo rows) = 7 572 rows.

Also `load_flow_summary.csv` (3 rows, the table above) for
quick scans.

---

## Day 25 — Orchestrator, audit, closeout

### `scripts/run_phase2.py`

Mirrors `scripts/run_phase1.py`. Four notebooks chained:

```
12_topology_audit.ipynb     2A.3
13_pandapower_build.ipynb   2B
14_loadflow.ipynb           2C
15_loadflow_audit.ipynb     2D
```

Pre-flight: print state snapshot (audit components,
load_flow_results rows). Per-step: state snapshot + wall
time. Final: verification. The verification gate is the
single most useful thing carried over from Phase 1 — it
caught Day 18's silent regression and the same idea
applies here:

```
MIN_AUDIT_COMPONENTS = 1
MIN_RESULT_ROWS = 7 000
EXPECTED_SCENARIOS = {'off_peak', 'morning_peak', 'evening_peak'}
```

End-to-end: **23 seconds.** `--from` and `--to` work as in
Phase 1 for iterating on a single notebook.

### 2D — Per-province audit

[`notebooks/15_loadflow_audit.ipynb`](../../notebooks/15_loadflow_audit.ipynb)
joins `load_flow_results.csv` against `buses.csv` and computes
per-(scenario, province) statistics. Output:
`loadflow_audit.csv` (27 rows = 3 scenarios × 9 in-service
provinces) and `loadflow_coverage.csv` (16 rows, one per
province, showing how much of each is in-service).

Two findings worth keeping.

**Coverage.** Seven provinces have *zero* in-service buses:

| Province | Buses (total) | Load (MW) not modelled |
|---|---:|---:|
| Iloilo | 158 | 250 |
| Aklan | 46 | 75 |
| Antique | 25 | 55 |
| Capiz | 25 | 80 |
| Siquijor | 22 | 15 |
| Guimaras | 21 | 25 |
| Biliran | 19 | 22 |

**522 MW unmodelled** — 23 % of the total Visayas peak. This
isn't a Phase 2 limitation per se; it's a direct consequence
of the disconnected components from the audit. Until the
Negros–Panay submarine and the Biliran / Siquijor feeds are
in the model, no load flow can include them.

**Off-peak voltage health** (NR scenario):

```
province           vm_pu_min  vm_pu_mean  n_under_0.95 / total
Negros Occidental  0.766      0.901       153 / 190 (80%)
Cebu               0.823      0.940       242 / 421 (57%)
Negros Oriental    0.895      0.959       50 / 118 (42%)
Bohol              0.883      0.960       61 / 182 (34%)
Eastern Samar      0.902      0.954       13 / 25  (52%)
Leyte              0.916      0.984       24 / 194 (12%)
Samar              0.919      0.972       12 / 46  (26%)
Northern Samar     0.914      0.985       4 / 16   (25%)
Southern Leyte     0.935      0.994       3 / 38   (8%)
```

Even at off-peak the network is operationally poor across most
provinces — 80 % of Negros Occidental buses below 0.95 isn't a
real-grid number, it's the synthetic feeder impedance issue
showing through. Phase 1 calibration concern, surfaced
quantitatively for the first time.

### Closeout

[`docs/closeouts/phase-2-closeout.md`](../closeouts/phase-2-closeout.md)
is one-screen, matches the Phase 1 closeout's structure:
artifact-in-one-paragraph → what-lives-where → open threads
carried into Phase 3 → resolved during Phase 2 → where Phase 3
picks up.

Open threads, ordered by load-bearing weight on Phase 3:

1. **NR convergence cliff at ~0.66.** Single largest issue.
   Fix path: lower synthetic 13.8 kV feeder impedance from
   `r = x = 0.4 Ω/km` toward underground-cable values
   (~`0.1 / 0.15`). Probably a half-day Phase 1 calibration
   pass.
2. **522 MW of fragment load not modelled.** Requires
   topology work on Phase 1 (Negros–Panay submarine,
   Biliran / Siquijor cables, Cebu fragment merge).
3. **Generator dispatch is a 4-row hand-estimate.** Should
   come from NGCP DDP or DOE data; Cebu in particular needs
   more plants tagged.
4. **Transformer sn_mva is generous defaults.** Phase 3
   audit can right-size.
5. **2A.1 / 2A.2 PostGIS work deferred.** Awaiting Docker /
   OrbStack install.

The closeout's "Where Phase 3 picks up" lists PostGIS loader
and FastAPI as the two candidate next moves. Both are
mutually compatible; the cleanest sequence is PostGIS first
because the deliverables are mechanical to load now that
schema and CSV layout agree.

---

## Day 26 — Container runtime + PostGIS loader (2A.1 / 2A.2)

The Phase 2 closeout deferred 2A because no container runtime was
installed. Day 26 fills that gap and runs both items end to end.

### Installing OrbStack

`brew install --cask orbstack` finished in under a minute.
OrbStack symlinks the `docker` and `docker-compose` CLIs into
`/usr/local/bin/` once the app launches — the first
`open -a OrbStack` did that automatically. `orbctl doctor`
confirmed everything healthy. The container starts via the
existing `docker-compose.yml` (one note: Docker emitted a
deprecation warning about the obsolete `version: "3.9"` key —
cosmetic, the file still works).

```
$ docker compose up -d db
[+] Running 12/12 ✓
$ docker compose ps
NAME             STATUS                    PORTS
powergrid-db-1   Up 49 seconds (healthy)   0.0.0.0:5432->5432/tcp
```

`init.sql` ran automatically via the `docker-entrypoint-initdb.d/`
bind-mount: `buses`, `lines`, `load_flow_results` tables and the
PostGIS 3.3.4 extension all in place after first start. One
quirk: the `postgis/postgis:15-3.3` image is `linux/amd64` and
runs under Rosetta on Apple Silicon. Works, just slower than a
native arm64 build would be — the GIST benchmarks below still
clear the 100 ms rubric easily.

### `scripts/load_to_postgis.py` — the loader

The script reads `buses.csv`, `lines.csv`, and
`load_flow_results.csv` and inserts via `psycopg2.execute_values`
in one transaction (`with conn:`). Idempotent — `TRUNCATE …
CASCADE` runs first, so re-running drops any prior rows. Three
geometry constructions matter:

- **Bus geom** is built inline from `(lon, lat)` with
  `ST_SetSRID(ST_MakePoint(%s, %s), 4326)`.
- **Line geom** is a two-point LINESTRING from the from_bus and
  to_bus coordinates. Built as WKT in Python
  (`f'LINESTRING({fc.lon} {fc.lat}, {tc.lon} {tc.lat})'`) and
  passed through `ST_GeomFromText(%s, 4326)`. A pre-built
  `bus_coord` dataframe-indexed-by-bus_id makes the per-line
  lookup O(1).
- **`load_flow_results.convergence_mode`** wasn't in the
  original schema. The script `ALTER TABLE … ADD COLUMN IF NOT
  EXISTS` it at the top of the load, and `init.sql` was also
  updated so future container starts have it natively.

The load finishes in well under a second:

```
buses                 2952 rows  (0.13 s)
lines                 2965 rows  (0.28 s)
load_flow_results     7572 rows  (0.21 s)
```

`ANALYZE` runs at the end to refresh planner statistics — the
GIST benchmarks immediately after depend on this.

### 2A.2 — GIST query benchmark

Six queries cover the API access patterns from
`power-grid-viz-plan-v2.md` §3.2: viewport (what the map draws
on every pan/zoom), province filter (sidebar "show only Cebu"),
and KNN nearest-N (click-to-inspect). Each runs 5 times with a
warm-up pass first; the script reports min / median / max and
asserts every max under 100 ms.

```
query                                rows   min_ms   med_ms   max_ms  ok?
viewport_buses_cebu                  1240     1.76     2.66     4.61  ✓
viewport_lines_cebu                  1294     2.27     4.34    25.73  ✓
viewport_buses_full_visayas          2866     2.41     2.50     4.28  ✓
province_filter_buses                 977     0.87     0.94     1.02  ✓
province_filter_lines_via_buses      1004    27.86    29.19    29.70  ✓
knn_nearest_10_buses                   10     0.30     0.34     0.46  ✓
```

The slowest query, `province_filter_lines_via_buses`, is a
join with `OR` across two FK columns
(`l.from_bus = b.bus_id OR l.to_bus = b.bus_id`). PostgreSQL
can't index the OR cleanly so it scans both directions and
deduplicates — the same query rewritten with `UNION ALL` and
distinct-keys would be faster, but at 30 ms it's well inside
the rubric and Phase 3 can refactor if it ever matters.

The KNN query (`ORDER BY geom <-> point LIMIT 10`) deserves a
mention: it goes through the GIST index's KNN extension and
clears 10 rows in under half a millisecond. Click-to-inspect
will feel instant.

### What changed and what's next

- `scripts/load_to_postgis.py` added (~190 lines, idempotent,
  loader + benchmark in one file).
- `backend/db/init.sql` updated: `convergence_mode TEXT` added
  to `load_flow_results`.
- Phase 2 closeout updated: 2A.1 and 2A.2 moved from "deferred"
  to "resolved during Phase 2"; "Where Phase 3 picks up" now
  recommends the FastAPI work directly since PostGIS is seeded.

Phase 2 is now genuinely complete. The remaining open thread
worth a return visit is the synthetic-feeder impedance issue
(the NR convergence cliff at ~0.66 of full load) — but that
sits parallel to Phase 3, not in front of it.
