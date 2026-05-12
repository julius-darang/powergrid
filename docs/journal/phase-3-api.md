# Phase 3 — FastAPI backend

> Day-by-day narrative for Phase 3. Starts from the Phase 2
> handoff in [`../closeouts/phase-2-closeout.md`](../closeouts/phase-2-closeout.md).
> Closeout: `../closeouts/phase-3-closeout.md` (to be written at
> the end of Phase 3).

## Inputs from Phase 2

- PostGIS live at `localhost:5432`, container `powergrid-db-1`
  (postgis/postgis:15-3.3 on linux/amd64 via Rosetta).
  `docker compose ps` shows healthy.
- Three tables populated by `scripts/load_to_postgis.py`:
  - `buses` — 2 952 rows (Day 26) → 2 959 rows after Day 27
    Phase 1 recalibration. `geom GEOMETRY(Point, 4326)`,
    `bus_id` primary key, columns `name`, `voltage_kv`,
    `province`, `island`, `bus_type`, `p_mw`, `q_mvar`,
    `is_synthetic`, `data_source`.
  - `lines` — 2 965 → 2 972 rows. `geom GEOMETRY(LineString,
    4326)` constructed from from-bus / to-bus coordinates.
    `line_id` primary key, FK to `buses.bus_id` on both ends.
  - `load_flow_results` — 7 572 → 7 536 rows. Long-format:
    each row is either a bus result (`bus_id` set, `vm_pu` /
    `va_degree` populated) or a line/transformer result
    (`line_id` set, `loading_percent` / `p_from_mw` / `p_to_mw`
    populated). Column `convergence_mode` holds `'nr'` or `'dc'`.
    After Day 27 every row is `'nr'`.
- GIST indexes on `buses.geom` and `lines.geom`. The six
  benchmark queries from `scripts/load_to_postgis.py` cover
  the canonical access patterns (viewport, province filter,
  KNN) — all under 30 ms median.

## Goals

Per `power-grid-viz-plan-v2.md` §4 (named "Phase 4" in the
plan; project numbering offset by one because the plan combined
data and load-flow into "Phase 1"):

1. **Serve GeoJSON from PostGIS.** Endpoints emit
   `FeatureCollection` shapes that a Leaflet frontend can
   consume directly. Properties include enough metadata to
   colour and filter elements.
2. **Surface load-flow results per scenario.** Bus voltage
   (`vm_pu`, `va_degree`) and line loading (`loading_percent`,
   `p_from_mw`, `p_to_mw`) merged with topology.
3. **Province / island filtering.** Sidebar selection picks
   one province or island; API returns just that subset.
4. **Viewport-driven panning.** Map pan/zoom hits a bbox-
   clipped endpoint that returns only what's visible.
5. **Metadata endpoints.** `/api/scenarios`, `/api/provinces`,
   `/api/health` for sidebar dropdowns and ops.

Skip the PNG / PDF export endpoints (`/api/export/*`) — those
are Phase 5 polish per the v2 plan.

## Days

### Day 27 — API scaffold built in parallel with Phase 1 recalibration

The user asked for "both in parallel" — Phase 1 feeder-impedance
recalibration (the convergence-cliff fix from the Phase 2
closeout) and the Phase 3 API scaffold. These are independent
tasks that touch disjoint parts of the repo: recalibration
edits live in `notebooks/{03,09,10}_*.ipynb` and the
processed-data CSVs, while the API scaffold lives in
`backend/{main.py, db/, services/, routers/, models/, tests/}`.
Zero file overlap, so they could genuinely run concurrently.

The execution model: dispatch a general-purpose subagent in the
background for the API work, do the recalibration inline.
Subagent prompts are by definition self-contained — the agent
doesn't see this conversation — so the prompt had to brief it
on the entire project state.

#### Briefing the subagent

The dispatched prompt covered:

- **Working directory** and venv (`.venv/bin/python`,
  `.venv/bin/uvicorn`). Don't create a new venv, don't install
  fastapi/uvicorn (already in requirements.txt).
- **Project plan** location (`power-grid-viz-plan-v2.md`,
  with a note that the v2 plan calls this "Phase 4" but the
  project calls it Phase 3 because data + load-flow were
  consolidated into Phase 1).
- **Existing closeouts** to read (Phase 1 + 2) for context.
- **The exact PostGIS schema** of all three tables.
- **The six benchmark queries** that already cover the API's
  access patterns — these are the queries the agent should
  template into endpoints.
- **The empty scaffolding** waiting to be filled in
  (`backend/routers/`, `backend/services/`,
  `backend/models/`).
- **Nine target endpoints** with method, path, and
  behaviour.
- **Architecture choices the agent should make autonomously:**
  asyncpg for async DB, `ST_AsGeoJSON(geom)::json` for GeoJSON
  emission, Pydantic v2 for response models, CORS allow-all
  with a TODO comment, FastAPI's `HTTPException` for 404 /
  422.
- **Testing approach:** pytest with `TestClient`, sanity tests
  that just hit `/api/health` and `/api/scenarios` against a
  live DB.
- **End-to-end verification protocol:** start uvicorn,
  `curl /api/health`, run `pytest`, kill uvicorn.
- **Project conventions:** terse code, no over-engineering,
  no README, one-line module docstrings, type hints, 4-space
  indent. Don't commit; just write files.

Total brief: ~80 lines of context.

#### What the subagent built

Files written (all under `/Users/julius/polymath/Projects/powergrid/`):

```
backend/__init__.py                   # empty package marker
backend/db/__init__.py                # empty
backend/db/connection.py              # asyncpg pool + lifespan helpers
backend/main.py                       # FastAPI app + CORS + routers
backend/models/__init__.py            # empty
backend/models/schemas.py             # Pydantic v2 response schemas
backend/routers/__init__.py           # empty
backend/routers/grid.py               # /api/grid/* — pure topology
backend/routers/analysis.py           # /api/loadflow/*, /api/provinces,
                                      # /api/scenarios, /api/health
backend/services/__init__.py          # empty
backend/services/geo.py               # SQL fragments + row → feature helpers
backend/tests/__init__.py             # empty
backend/tests/test_api.py             # 2 pytest sanity tests
requirements.txt                       # appended pytest + httpx
```

The agent worked autonomously for ~5 minutes. Its execution
sandbox blocked `pip install`, `python`, and `uvicorn`, so it
couldn't run its own tests — that part fell to the integration
step. Everything else was self-contained.

While the agent was running, the Phase 1 recalibration work
proceeded inline in parallel — `notebooks/{03,09,10}_*.ipynb`
edited, `run_phase1.py` re-ran (39 s), `run_phase2.py` re-ran
(23 s), `load_to_postgis.py` re-ran. The Phase 1 work touched
notebooks and processed-data CSVs; the agent's API work
touched only the `backend/` scaffolding. The two
streams never collided.

#### Architecture decisions and their alternatives

Each major decision had a defensible alternative; recording
them here so they don't have to be re-derived later.

**1. asyncpg, not SQLAlchemy.** asyncpg is already in
`requirements.txt`. The endpoints are read-only and SQL is
hand-written (the benchmark queries are the templates).
SQLAlchemy ORM overhead would have been pointless for what
amounts to "execute this prepared statement, map rows to
GeoJSON." The pool sits as a single global initialised in the
FastAPI `lifespan`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    try:
        yield
    finally:
        await close_pool()
```

Modest pool size — `min_size=1, max_size=8`. This is a single-
process dev server; a production deployment would tune this
against expected concurrency.

**2. `ST_AsGeoJSON(geom)::json`, not Python-side construction.**
Every SELECT includes:

```sql
SELECT ..., ST_AsGeoJSON(geom)::json AS geom_json
FROM buses
WHERE …
```

PostGIS emits a proper GeoJSON geometry dict (`{"type":
"Point", "coordinates": [124.5, 11.2]}`) per row. The Python
side never sees `(lon, lat)` tuples — they go through PostGIS
once at load time and come back as JSON forever after. This
matters because: (a) GeoJSON serialization is non-trivial for
LineStrings with N coordinates; (b) the geometry already lives
in PostGIS; (c) doing it in SQL means a single round-trip per
request, no chatty per-row queries.

The asyncpg detail: `::json` returns the value as a JSON
string in Python, while `::jsonb` would return a parsed dict.
We use `::json` (which is what `ST_AsGeoJSON` natively
returns) and decode in `_row_to_feature` if it comes back as
a string. `jsonb` would skip the decode but adds a PostGIS
type conversion; the `::json` path is cheaper.

**3. Single FeatureCollection per endpoint, mixed bus + line
features.** The v2 plan §4 examples show this shape, and the
frontend filters by `geometry.type === 'Point'` (buses) vs
`'LineString'` (lines). Alternative was `{buses: FC, lines:
FC}` which would have been more explicit but inconvenient for
common operations like "draw everything visible". Mixed FC
won because it matches how Leaflet's
`L.geoJSON` consumes the data.

**4. Loose Pydantic models.** Defined in
`backend/models/schemas.py`:

```python
class Feature(BaseModel):
    type: Literal['Feature'] = 'Feature'
    geometry: dict[str, Any]
    properties: dict[str, Any]

class FeatureCollection(BaseModel):
    type: Literal['FeatureCollection'] = 'FeatureCollection'
    features: list[Feature]
```

`properties: dict[str, Any]` is deliberately loose. Routers
return raw dicts; FastAPI doesn't re-validate every feature
on every response (would otherwise be 3 000+ validations per
`/api/loadflow/{scenario}` call). The schemas exist mainly
for `/docs` (auto-generated OpenAPI) and future tightening —
once the frontend pins what properties it actually consumes,
the dict can be narrowed to a TypedDict or stricter model.

**5. LEFT JOIN to `load_flow_results`** in the loadflow
endpoints. About 1 230 of 2 959 buses (≈42 %) are in the
connected big component and have load-flow results; the
remaining 58 % sit in disconnected fragments (per the Phase 2
audit). The LEFT JOIN means those 58 % still appear as
features in `/api/loadflow/{scenario}` with `vm_pu: null` —
the frontend can colour them differently (greyed-out, hatched,
etc.) rather than missing entirely. INNER JOIN would have
silently dropped 1 729 buses per request; users would have
no way to tell the difference between "out of service" and
"not in the data."

**6. CORS allow-all** with a TODO comment. The Phase 4
frontend doesn't exist yet; once its host is known, this
tightens to a specific origin. For development, allow-all
keeps `localhost:5173` (Vite default) and any other dev
origin working.

**7. `HTTPException` for 404 / 422.** Standard FastAPI
pattern. The 404 cases hit a cheap `SELECT 1 FROM buses
WHERE province = $1 LIMIT 1` before the expensive feature
query — wasted round-trip vs cleaner error contract; chose
the latter. The 422 cases (invalid bbox) are pure parameter
validation, never touch the DB.

#### Per-endpoint walkthrough

**`GET /api/health`** — three queries:

```sql
SELECT version()                 -- PostgreSQL 15.4 (Debian …)
SELECT PostGIS_Version()         -- 3.3 USE_GEOS=1 USE_PROJ=1 …
SELECT COUNT(*) FROM buses       -- 2959
SELECT COUNT(*) FROM lines       -- 2972
SELECT COUNT(*) FROM load_flow_results  -- 7536
```

Returns `{status: 'ok', db_version, postgis_version, counts:
{...}}`. Used by the pytest sanity test and any future uptime
monitor.

**`GET /api/scenarios`** — groups by `(scenario, convergence_mode)`,
picks the modal mode per scenario:

```python
SELECT scenario, convergence_mode, COUNT(*)::int AS n
FROM load_flow_results
WHERE convergence_mode IS NOT NULL
GROUP BY scenario, convergence_mode
```

After Day 27 this returns `[{name: 'off_peak', mode: 'nr'},
{name: 'morning_peak', mode: 'nr'}, {name: 'evening_peak',
mode: 'nr'}]`. Before Day 27 (when only off-peak NR-converged)
it would have returned `mode: 'dc'` for the other two.

**`GET /api/provinces`** — the sidebar payload. After the
integration fix (see "Bugs surfaced at integration" below):

```sql
SELECT b.province AS name,
       MIN(b.island) AS island,
       COUNT(*)::int AS bus_count,
       COUNT(DISTINCT r.bus_id)::int AS in_service_bus_count,
       COALESCE(SUM(b.p_mw), 0)::float AS total_load_mw,
       COALESCE(SUM(b.p_mw) FILTER (WHERE r.bus_id IS NOT NULL),
                0)::float AS in_service_load_mw,
       COUNT(*) FILTER (WHERE b.data_source = 'osm')::int AS osm_buses,
       COUNT(*) FILTER (WHERE b.is_synthetic)::int AS synthetic_buses
FROM buses b
LEFT JOIN load_flow_results r
  ON r.bus_id = b.bus_id AND r.scenario = 'evening_peak'
WHERE b.province IS NOT NULL
GROUP BY b.province ORDER BY b.province
```

Example payload for Aklan (a disconnected province):

```json
{
  "name": "Aklan", "island": "Panay",
  "bus_count": 46, "in_service_bus_count": 0,
  "total_load_mw": 75.0, "in_service_load_mw": 0.0,
  "osm_buses": 0, "synthetic_buses": 45
}
```

The frontend can use these numbers to render a province
sidebar with coverage indicators ("Aklan: 0/46 buses in
service").

**`GET /api/grid/transmission`** — all buses + lines with
`voltage_kv >= 60`. Returns 437 features (mostly the
138 kV / 230 kV / 350 kV backbone, the 60 kV substations,
and a handful of 69 kV lines). This is the default Leaflet
view: when the user first opens the map, draw the transmission
backbone, not the 2 700+ synthetic distribution buses.

**`GET /api/grid/province/{name}`** — buses + lines for a
province. Uses an existence check for clean 404. The line
query is the OR-on-FK pattern from the benchmark:

```sql
SELECT DISTINCT ON (l.line_id) l.line_id, l.from_bus, l.to_bus,
       l.voltage_kv, l.length_km, l.is_submarine, l.cable_type,
       l.is_synthetic, l.data_source,
       ST_AsGeoJSON(l.geom)::json AS geom_json
FROM lines l
JOIN buses b ON l.from_bus = b.bus_id OR l.to_bus = b.bus_id
WHERE b.province = $1
```

`DISTINCT ON (l.line_id)` because the OR-join can match a line
twice (once on `from_bus`, once on `to_bus`). Without it, plain
`DISTINCT` fails — see the bug section below.

**`GET /api/grid/island/{name}`** — same pattern keyed on
`b.island`.

**`GET /api/grid/viewport`** — bbox-clipped buses and lines:

```sql
SELECT … FROM buses
WHERE ST_Within(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))

SELECT … FROM lines
WHERE ST_Intersects(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))
```

Bbox validation rejects `minlon >= maxlon`, `minlat >= maxlat`,
or out-of-range coordinates with a 422.

The viewport endpoint is the one the frontend will hit most
often — every map pan/zoom triggers it. The benchmark showed
2.5–4.3 ms median across various bboxes; that's well below
the human-perceptible threshold for "feels instant."

**`GET /api/loadflow/{scenario}`** — joins the topology to
load-flow results via LEFT JOIN. Returns 5 931 features per
call (2 959 buses + 2 972 lines, every feature regardless of
whether it has a result row). Buses outside the connected
component have `vm_pu: null`, `va_degree: null`.

**`GET /api/loadflow/{scenario}/{province}`** — same with a
province filter on top, using the same OR-on-FK pattern as the
grid endpoint for the line subset.

#### Bugs surfaced at integration

The subagent's sandbox blocked uvicorn execution, so it
couldn't run its own end-to-end check. Two issues surfaced
when integration testing ran post-dispatch.

**Bug 1: `DISTINCT` over `json` columns fails.**

```
asyncpg.exceptions.UndefinedFunctionError:
  could not identify an equality operator for type json
```

The agent's `grid.py` line query used plain `SELECT DISTINCT
l.line_id, ..., ST_AsGeoJSON(l.geom)::json AS geom_json`.
PostgreSQL implements `DISTINCT` by comparing all columns in
the SELECT list, and `json` (the type, not `jsonb`) has no
equality operator — `json` is essentially a text type that
preserves whitespace and key order, so two values with the
same logical content might differ byte-for-byte. PostgreSQL
won't define equality on it.

`jsonb` has equality and could have been used (`::jsonb`), but
the right fix is `DISTINCT ON (l.line_id)` — dedupe by the
identity column instead of comparing the whole projection.

```diff
- SELECT DISTINCT l.line_id, ..., ST_AsGeoJSON(l.geom)::json
+ SELECT DISTINCT ON (l.line_id) l.line_id, ...,
+        ST_AsGeoJSON(l.geom)::json
```

Two endpoints affected (`/api/grid/province/...` and
`/api/grid/island/...`); both fixed. The analysis.py
`loadflow_province` endpoint already used `DISTINCT ON` —
the agent was inconsistent across files.

**Bug 2: `in_service_bus_count` filter on a value that
doesn't exist.**

The agent's `/api/provinces` SQL filtered:

```sql
COUNT(*) FILTER (WHERE bus_type != 'out_of_service')::int
  AS in_service_bus_count
```

Reasonable-looking assumption — but `bus_type` in this project
is one of `distribution`, `substation`, `tower`, `generator`,
`substation_synth`, `hvdc`. There is no `'out_of_service'`
value. The in-service distinction lives only in pandapower
(`net.bus.in_service`), not in the DB.

The agent had the schema documented in its brief but didn't
catch that the in-service flag was missing. Easy mistake —
it's a sensible-looking assumption that just doesn't match
reality.

Fix: derive in-service from membership in `load_flow_results`.
Phase 2 only emits result rows for buses inside the connected
big component, so presence in `load_flow_results` is a clean
proxy for "in service":

```sql
-- before
COUNT(*) FILTER (WHERE bus_type != 'out_of_service')::int

-- after
LEFT JOIN load_flow_results r
  ON r.bus_id = b.bus_id AND r.scenario = 'evening_peak'
GROUP BY b.province
…
COUNT(DISTINCT r.bus_id)::int AS in_service_bus_count
```

Worth noting: pinning to `r.scenario = 'evening_peak'` means
all three scenarios have to be loaded for this query to work
correctly. They are; if a future Phase 3 endpoint runs a
single scenario, this filter needs revisiting.

After both fixes, all nine endpoints work and return the
expected counts.

#### Verification end-to-end

After fixes, started uvicorn and walked every endpoint:

```
GET /api/health
  → 200, counts: 2959 / 2972 / 7536

GET /api/scenarios
  → 200, [off_peak/nr, morning_peak/nr, evening_peak/nr]

GET /api/provinces
  → 200, 16 provinces, Aklan/Antique/Biliran in_service=0

GET /api/grid/transmission
  → 200, 437 features

GET /api/grid/province/Cebu
  → 200, 1985 features

GET /api/grid/island/Cebu
  → 200, 1985 features

GET /api/grid/province/Nope
  → 404 (existence check)

GET /api/grid/viewport?minlon=125&maxlon=123…
  → 422 (bbox validation)

GET /api/grid/viewport?minlon=123.4&minlat=9.4&maxlon=124.5&maxlat=11.4
  → 200, 2544 features (Cebu bbox; matches benchmark counts)

GET /api/loadflow/evening_peak
  → 200, 5931 features

GET /api/loadflow/evening_peak/Cebu
  → 200, 1985 features, vm_pu min=0.847 max=1.000

GET /api/loadflow/garbage_scenario
  → 404 (scenario validation)
```

The Cebu evening-peak `vm_pu_min` of 0.847 matches the Phase 2
audit's per-province table (`docs/closeouts/phase-2-closeout.md`
"Per-province voltage health" — Cebu 0.847) exactly. API and
audit are reading the same underlying data through different
paths and agree to three decimal places.

Then `pytest`:

```
$ .venv/bin/pytest backend/tests/ -v
============================== test session starts ==============================
collected 2 items

backend/tests/test_api.py::test_health PASSED                            [ 50%]
backend/tests/test_api.py::test_scenarios PASSED                         [100%]

============================== 2 passed in 0.96s ===============================
```

Tests asserted the post-recalibration counts (2 959 / 2 972 /
7 536) — these will shift if Phase 1 re-runs change the row
counts again, so the test file has a comment marking them as
"update when run_phase1.py output changes."

### Patterns worth keeping

A short list of practices that worked well on Day 27 and
should stay for the rest of Phase 3:

- **Parallel-track dispatch when the file footprints are
  disjoint.** The agent worked in `backend/`, the inline
  recalibration worked in `notebooks/` + `scripts/`. Could
  also have used `isolation: "worktree"` for stronger guarantees;
  for this case the disjoint-footprint argument was sufficient.
- **Brief the subagent like a colleague who just walked in.**
  Schema, file paths, design decisions to make autonomously,
  conventions, verification protocol. The subagent's brief
  was ~80 lines; the work it produced needed minimal rework.
- **Subagents can't always verify their own work.** The agent
  was sandboxed away from `pip` and `uvicorn`, so two bugs
  slipped through. Always run end-to-end tests after a
  subagent returns. Schedule the integration test as part of
  the dispatch loop, not as an afterthought.
- **`ST_AsGeoJSON(geom)::json` over Python-side construction.**
  Whenever the geometry already lives in PostGIS, let PostGIS
  emit GeoJSON. Single round-trip, no chatty queries, no
  serialization bugs.
- **LEFT JOIN over INNER JOIN** when "not present" is a
  meaningful answer. The 58 % of buses outside the connected
  component aren't broken; they're modelling-limited. Visibly
  surfacing them with `null` results is more honest than
  silently dropping them.
- **`DISTINCT ON (id)` over plain `DISTINCT`** whenever a
  query SELECTs anything PostgreSQL can't compare. `json`,
  arrays of composite types, certain custom types. Cheaper too
  — Postgres only has to sort/hash by the identity column,
  not the whole row.

### Open threads for Phase 3 continuation

- **No `/api/export/{png,pdf}` endpoints.** Deferred per the
  v2 plan; Phase 5 polish.
- **CORS tightening.** `allow_origins=['*']` works for dev;
  pin to the frontend's host once Phase 4 lands.
- **OpenAPI / `/docs` review.** Auto-generated from the
  loose Pydantic schemas (`properties: dict[str, Any]`).
  Tighten once the frontend pins its expectations.
- **No pagination.** `/api/loadflow/evening_peak` returns
  5 931 features in one payload (~3 MB JSON). Fine for dev;
  consider cursor- or filter-based pagination if response
  size becomes a real concern.
- **No caching.** Every request hits PostGIS. The viewport
  query is fast enough not to matter (~3 ms median); the
  province / loadflow queries are 20–30 ms. A 60-second
  in-memory cache for `/api/provinces` and `/api/scenarios`
  would be cheap if endpoints get hit hard.
- **`line_synth_spur_006` persistent overload** — the API
  faithfully reports `loading_percent ≈ 195 %` on the Therma
  export spur. Not an API concern; a Phase 1 calibration
  thread (`max_i_ka` needs bumping from 0.7 to ~1.5).
- **No frontend yet.** The API exists in vacuum. The first
  Phase 4 consumer will surface whatever endpoint signatures
  feel awkward in practice; expect a small round of API
  refactoring once Leaflet code starts hitting it.