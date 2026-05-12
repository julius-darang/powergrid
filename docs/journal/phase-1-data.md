# Build Journal — Philippine Power Grid Visualization

> A working developer log of the artifacts that have actually landed,
> through Day 20 (population-weighted load assignment — the model
> now lands within 4 % of the published Visayas peak demand).
> Source material for a later write-up; everything below is anchored
> in committed files, not the forward-looking plan.

---

## Why this project

The goal is a public web app that visualises the Philippine power grid in
two layers: the Visayas transmission backbone (69 / 138 / 230 kV) and
per-province distribution, with a load-flow model running underneath in
pandapower. Real NGCP topology is not public, and OSM coverage drops off
sharply below transmission voltages, so the build has to plan for
synthetic infill from day one without painting itself into a corner when
real data eventually arrives.

The plan you are working from is `power-grid-viz-plan-v2.md` — version 2,
written after a technical review that reshaped six decisions (SQLite →
PostGIS, schema additions for submarine cables and synthetic flags, a
mandatory topology-validation gate before any load-flow run, a longer
11-week timeline, and so on). Each Day 1 / Day 2 artifact below is a
direct response to one of those review verdicts.

---

## Day 1 — Foundations

### PostGIS, not SQLite

The first file that hits disk is [docker-compose.yml](docker-compose.yml):

```yaml
services:
  db:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: powergrid
      POSTGRES_USER: powergrid
      POSTGRES_PASSWORD: powergrid
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/db/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U powergrid"]
      interval: 5s
      timeout: 5s
      retries: 5
```

Twenty-two lines, one service, no application container yet — the database
is deliberately the first thing standing up. The review feedback row
*"PostGIS from the start (not SQLite)"* was marked Accepted, and the
reason becomes obvious the moment you sketch the work: every interesting
query in this project is a spatial join (bus points into province
polygons, lines clipped to island geometries, substations near feeders).
Doing that in SQLite + a third-party SpatiaLite extension is technically
possible and operationally miserable. PostGIS with a `GIST` index on
`geom` is the default that the rest of the stack expects.

The bind-mount of `init.sql` into `docker-entrypoint-initdb.d/` means the
schema is created on the very first `docker compose up`, and the named
`pgdata` volume keeps it across restarts. The healthcheck (`pg_isready`)
exists so that when the FastAPI service is added in a later week, it can
declare a `depends_on: db: { condition: service_healthy }` without
race-condition surprises.

### The schema as a contract

[backend/db/init.sql](backend/db/init.sql) is fifty-two lines and worth
reading top to bottom, because every column on it is load-bearing:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE buses (
    bus_id TEXT PRIMARY KEY,
    name TEXT,
    geom GEOMETRY(Point, 4326),
    voltage_kv FLOAT,
    province TEXT,
    island TEXT,
    bus_type TEXT,
    p_mw FLOAT,
    q_mvar FLOAT,
    is_synthetic BOOLEAN DEFAULT FALSE,
    data_source TEXT DEFAULT 'osm'
);

CREATE TABLE lines (
    line_id TEXT PRIMARY KEY,
    from_bus TEXT REFERENCES buses(bus_id),
    to_bus TEXT REFERENCES buses(bus_id),
    geom GEOMETRY(LineString, 4326),
    voltage_kv FLOAT,
    length_km FLOAT,
    r_ohm_per_km FLOAT,
    x_ohm_per_km FLOAT,
    max_i_ka FLOAT,
    is_submarine BOOLEAN DEFAULT FALSE,
    cable_type TEXT DEFAULT 'overhead',
    is_synthetic BOOLEAN DEFAULT FALSE,
    data_source TEXT DEFAULT 'osm'
);

CREATE TABLE load_flow_results (
    id SERIAL PRIMARY KEY,
    scenario TEXT,
    bus_id TEXT REFERENCES buses(bus_id),
    line_id TEXT REFERENCES lines(line_id),
    vm_pu FLOAT,
    va_degree FLOAT,
    loading_percent FLOAT,
    p_from_mw FLOAT,
    p_to_mw FLOAT
);

CREATE INDEX idx_buses_geom ON buses USING GIST(geom);
CREATE INDEX idx_lines_geom ON lines USING GIST(geom);
```

Four columns on this schema only exist because of the review:

- **`is_synthetic BOOLEAN` and `data_source TEXT`** on both `buses` and
  `lines`. The OSM coverage gap is a confirmed risk (Phase 1C exists
  specifically to fill it with a synthetic radial topology generator).
  If the schema does not distinguish OSM rows from synthetic rows from
  eventual real NGCP rows on day one, you cannot mix them safely later,
  and you cannot tell a viewer which lines on the map are real. Three
  cheap columns now; impossible to retrofit cleanly across a populated
  database in three months.
- **`is_submarine BOOLEAN` and `cable_type TEXT`** on `lines`. Visayas
  is a chain of islands joined by submarine XLPE cables (Leyte–Cebu,
  Cebu–Negros, Negros–Panay). Submarine cables have very different
  impedance than overhead conductors — the plan cites starting values
  of `r ≈ 0.0754 Ω/km`, `x ≈ 0.121 Ω/km`, `max_i_ka ≈ 0.645` for
  630 mm² XLPE — and quietly running an overhead impedance through them
  will silently give you a wrong load flow.

The `GEOMETRY(Point, 4326)` and `GEOMETRY(LineString, 4326)` types pin
the SRID to WGS 84 at the schema boundary, so nothing downstream needs
to guess. The two `GIST` indexes are not optional: without them every
spatial join the API does at request time would be a sequential scan.

### The Python toolchain

[requirements.txt](requirements.txt) is fifteen lines but reads like a
mission statement:

```
fastapi
uvicorn
pandapower
osmnx
geopandas
shapely
pandas
contextily
matplotlib
reportlab
psycopg2-binary
sqlalchemy
networkx
asyncpg
jupyter
```

You can map every entry to a phase of the plan. `osmnx` for Phase 1A
extraction. `geopandas` + `shapely` for Phase 1B cleaning. `networkx`
sits there for Phase 1C — the synthetic distribution generator builds a
Steiner-tree approximation of feeders rooted at the substation, and
NetworkX is the natural place for that. `pandapower` is the load-flow
engine; the choice of 60 Hz (vs the European 50 Hz default) is a
Philippines-specific detail captured in the plan. `contextily` adds an
OSM basemap underneath matplotlib plots, and `reportlab` is for the
publication-quality PDF export that the export router will produce later.
Both `psycopg2-binary` and `asyncpg` are pinned: psycopg for one-shot
notebook work, asyncpg for the FastAPI app once it shows up.

### First real pull from OSM

`backend/data/raw/extract_osm.py` (now removed; the same logic lives
in [notebooks/01_osm_extraction.ipynb](../../notebooks/01_osm_extraction.ipynb)
with idempotency guards added) was twenty-two lines and was the
first piece of code that produced a real artifact rather than
scaffolding:

```python
import osmnx as ox
import geopandas as gpd
from pathlib import Path

tags = {"power": ["line", "cable", "substation", "tower"]}
visayas_bbox = (123.0, 9.0, 126.5, 13.0)

print("Extracting Visayas power infrastructure from OSM...")
gdf = ox.features_from_bbox(bbox=visayas_bbox, tags=tags)
```

A few choices worth noting. The bbox is in OSMnx's `(west, south, east,
north)` order — `(123.0, 9.0, 126.5, 13.0)` covers the entire Visayas
group with some margin into the Sulu Sea so that the Negros and Panay
west coasts are not clipped. The tag set is deliberately narrow:
`line`, `cable`, `substation`, `tower`. `cable` is important because OSM
tags submarine interconnections as `power=cable`, not `power=line`, and
later cleaning code keys off exactly that distinction to flip
`is_submarine = TRUE`. `generator` was discussed but left out for now;
plant locations come in via a different path.

The script writes the result to
[backend/data/raw/visayas_power_raw.geojson](backend/data/raw/visayas_power_raw.geojson),
roughly 29 MB of mixed features. Everything downstream — voltage
filtering, geometry repair, node snapping, substation matching, the
coverage audit — is a transformation of this single file.

### The inherited v1 CSVs

The repo also carries three older CSVs from a v1 iteration:
[data/buses.csv](data/buses.csv), [data/lines.csv](data/lines.csv),
[data/admin_regions.csv](data/admin_regions.csv). Useful as ground truth
for sanity-checking the eventual OSM extraction (Babatngon, Calbayog,
Ormoc 350 kV HVDC and friends are all listed there with hand-curated
coordinates), but they predate the schema. Compare a `buses.csv` header
to `init.sql`:

```
v1 buses.csv:    name, x, y, v_nom, region, description, island, bus_type
init.sql buses:  bus_id, name, geom, voltage_kv, province, island,
                 bus_type, p_mw, q_mvar, is_synthetic, data_source
```

The new schema has dropped `description`, promoted `(x, y)` to a real
`GEOMETRY(Point, 4326)`, added province (the v1 had only region/island),
added the load-flow inputs `p_mw` / `q_mvar`, and tacked on the two
provenance columns. A small but real before-and-after of the review
feedback.

By the end of Day 1 the database boots clean, the OSM pull runs end to
end, and a 29 MB GeoJSON sits on disk waiting for the cleaning pipeline.
No FastAPI app yet, no React app, no tests.

---

## Day 2 — Building the geography substrate

Before any spatial join can run against the OSM pull, the project needs a
clean map of where the Visayas actually is, at two granularities: the
sixteen administrative provinces, and the nine physical islands those
provinces dissolve into. Both layers feed Phase 1B (province / island
tagging on every bus) and Phase 1C (the synthetic distribution
generator, which needs an island polygon as its bounding region).

The day's work is captured in one notebook:
[notebooks/00_boundary_prep.ipynb](notebooks/00_boundary_prep.ipynb).
Inputs are GADM 4.1 PH
([backend/data/boundaries/gadm41_PHL.gpkg](backend/data/boundaries/gadm41_PHL.gpkg),
75 MB) and a hand-built sixteen-row PSGC reference CSV
([backend/data/boundaries/psgc_provinces_reference.csv](backend/data/boundaries/psgc_provinces_reference.csv)).

### Step 2.1 — Load GADM and meet the flat-hierarchy gotcha

```python
adm1 = gpd.read_file(BOUND_DIR / 'gadm41_PHL.gpkg', layer='ADM_ADM_1')
print('PH provinces in GADM:', len(adm1))   # → 81
```

GADM 4.1 for the Philippines uses a flat hierarchy: `ADM_ADM_1` is the
province, `ADM_ADM_2` is the municipality. There is no region layer at
all. So a naive "filter to Visayas by region" approach is impossible from
GADM alone — you have to bring an external authoritative list of which
provinces *are* Visayas.

### Step 2.2 — Filter via the PSGC reference

The PSGC CSV is that authoritative list, sixteen rows covering Region VI
(Western Visayas), Region VII (Central Visayas), and Region VIII (Eastern
Visayas). The filter is an inner merge, which doubles as a validation:

```python
GADM_TO_PSA = {
    # 'Davao de Oro': 'Compostela Valley',  # alias pattern, unused here
}
adm1['psa_name'] = adm1['NAME_1'].replace(GADM_TO_PSA)

visayas = adm1.merge(psgc_ref, left_on='psa_name',
                     right_on='province_name', how='inner')

missing_from_gadm = set(psgc_ref['province_name']) - set(visayas['psa_name'])
assert len(visayas) == 16, f'Expected 16 Visayas provinces, got {len(visayas)}'
assert not missing_from_gadm, f'Need alias entries for: {missing_from_gadm}'
```

Two assertions, both green: all sixteen PSGC names matched GADM's
`NAME_1` on the first try, so the alias dict stayed empty. The scaffold
is there anyway — the next dataset will almost certainly need it (Davao
de Oro vs Compostela Valley is the canonical example).

### Step 2.3 — Province → Island mapping

A hand-curated dict, no clever inference:

```python
PROVINCE_TO_ISLAND = {
    'Aklan': 'Panay', 'Antique': 'Panay', 'Capiz': 'Panay', 'Iloilo': 'Panay',
    'Guimaras': 'Guimaras',
    'Negros Occidental': 'Negros', 'Negros Oriental': 'Negros',
    'Cebu': 'Cebu', 'Bohol': 'Bohol', 'Siquijor': 'Siquijor',
    'Leyte': 'Leyte', 'Southern Leyte': 'Leyte',
    'Biliran': 'Biliran',
    'Samar': 'Samar', 'Eastern Samar': 'Samar', 'Northern Samar': 'Samar',
}
```

Nine islands, not six. Guimaras, Siquijor, and Biliran each get their
own group despite being small, because all three are submarine-fed and
Phase 1C's synthetic distribution generator will treat each one as an
isolated radial network rooted at its own substation. Collapsing them
into Panay / Negros / Leyte would lose exactly the structural feature
the model needs.

### Step 2.4 — Dissolve

```python
islands = (
    visayas[['psa_name', 'island_name', 'geometry']]
    .dissolve(by='island_name', aggfunc={'psa_name': list})
    .rename(columns={'psa_name': 'provinces'})
    .reset_index()
)
assert len(islands) == 9
```

Aggregating `psa_name` as a list keeps the per-island province roster
attached to the geometry — useful for tooltips later, and for a sanity
check while you stare at the table.

### Step 2.5 — Area sanity check

Reproject to UTM 51N (EPSG:32651, the right metric CRS for the central
Philippines), compute area in km², compare against published values:

| Island   | Computed km² | Expected km² | Δ %    |
|----------|--------------|--------------|--------|
| Biliran  |       534.33 |          555 |  −3.7% |
| Bohol    |     3 976.87 |        4 820 | **−17.5%** |
| Cebu     |     4 878.70 |        4 950 |  −1.4% |
| Guimaras |       604.53 |          605 |  −0.1% |
| Leyte    |     7 246.73 |        7 370 |  −1.7% |
| Negros   |    12 800.33 |       13 300 |  −3.8% |
| Panay    |    11 757.25 |       12 300 |  −4.4% |
| Samar    |    13 120.97 |       13 400 |  −2.1% |
| Siquijor |       320.72 |          343 |  −6.5% |

The tolerance is ±10%, deliberately loose because GADM administrative
boundaries do not trace coastlines exactly. Eight islands are inside
that envelope. Bohol is not — it comes in 17.5% below the published
4 820 km², which is well past anything that could be explained by
coastline simplification. Plausible suspects: a chunk of Bohol's
satellite islands (Panglao, the Camotes group adjacent, the smaller
barangays) is sitting in a different `NAME_1` value and not merging in,
or GADM is simply cutting Bohol differently. Worth a Step 2.5b before
trusting any island-level aggregate that involves Bohol.

### Step 2.6 — Save

```python
provinces_out = visayas.rename(columns={'psa_name': 'province'})[
    ['psgc_code', 'province', 'region', 'island_name', 'geometry']
]
provinces_out.to_file(BOUND_DIR / 'psgc_provinces.geojson', driver='GeoJSON')

islands_out = islands.copy()
islands_out['provinces'] = islands_out['provinces'].apply(
    lambda xs: ','.join(sorted(xs))
)
islands_out.to_file(BOUND_DIR / 'visayas_islands.geojson', driver='GeoJSON')
```

Two outputs land on disk:
[psgc_provinces.geojson](backend/data/boundaries/psgc_provinces.geojson)
(16 features, 6 MB) and
[visayas_islands.geojson](backend/data/boundaries/visayas_islands.geojson)
(9 features, 6 MB). One last footgun handled in the second-to-last line:
GeoJSON has no list type, so the `provinces` column has to be flattened
to a comma-joined string before write.

---

## Day 3 — Phase 1A: OSM extraction (formalised) and the coverage audit

Day 1 already produced the raw OSM dump, but it was a 22-line standalone
script with no inventory step. Phase 1A wraps that pull in a proper
notebook and then runs the audit the v2 plan has been waiting on: a
quantitative, per-province picture of what OSM has, so Phase 1C can
stop guessing at scope.

Two notebooks land:
[notebooks/01_osm_extraction.ipynb](notebooks/01_osm_extraction.ipynb)
and
[notebooks/05_osm_coverage_audit.ipynb](notebooks/05_osm_coverage_audit.ipynb).
The audit writes
[backend/data/processed/coverage_audit.csv](backend/data/processed/coverage_audit.csv)
— sixteen rows, one per Visayas province, that the rest of the pipeline
keys off.

### 01 — Idempotent extraction

The Day 1 script is rewritten as a notebook cell with a `FORCE_REFRESH`
flag and a file-exists short-circuit:

```python
FORCE_REFRESH = False

if FORCE_REFRESH or not RAW.exists():
    tags = {'power': ['line', 'cable', 'substation', 'tower', 'generator']}
    visayas_bbox = (123.0, 9.0, 126.5, 13.0)
    gdf = ox.features_from_bbox(bbox=visayas_bbox, tags=tags)
    gdf.to_file(RAW, driver='GeoJSON')
else:
    print(f'Using cached {RAW}. Set FORCE_REFRESH=True to re-extract.')
```

Re-running the notebook no longer hammers the Overpass API for the 1–3
minutes it takes to refetch 29 MB. `generator` was added to the tag set
this time so plant locations are present in the same dump.

A quick inventory cell prints the high-level shape that every downstream
decision starts from:

```
Total features: 19607
Geometry types: {'Point': 18864, 'LineString': 631, 'Polygon': 112}

Power tag distribution:
  tower         18853
  line            589
  substation      121
  cable            44

Rows missing voltage tag: 19151 / 19607
```

Two facts to sit with. First, towers dominate — 18,853 of 19,607
features — because mappers tag transmission pylons individually; those
will become inferred bus candidates in Phase 1B but they are not
themselves lines. Second, 97.7% of rows have no `voltage` tag. Almost
all of that is towers (which rarely carry voltage tags), but it means
voltage-class filtering has to be tolerant or it will throw away real
lines.

### 05 — The audit, in five passes

The audit notebook is the deliverable. Each pass adds one column to the
eventual per-province table.

**§1. Voltage parsing.** OSM `voltage` is a free-text field — `'138000'`
is fine, `'138000;69000'` is fine, but the tail of the distribution
includes `'220_-_25000_Watts_(Appliaces_or_Electrical_Equipmnt_Max_Amperes_100_Amps)'`,
`'5.5_VDC'`, `'0'`, and a bare `'-'`. The parser splits on `;,/`,
extracts the first integer per part, normalises kV-vs-V by checking
whether the number is ≥ 1000, and drops anything outside `[0.4, 1000]`
kV. The cross-tab of `power` tag against parsed voltage class is the
first sanity check that the parser is working:

```
vclass      distribution  lv  transmission  unknown
power
cable                  0   0            33       11
line                   9  22           343      215
substation             0   0            46       75
tower                  0   0             0    18853
```

So out of 589 `power=line` features, 343 carry a parseable transmission
voltage and 215 are untagged — those untagged lines almost certainly
include real backbone, which is why §3 tracks them separately rather
than discarding them.

**§2. Subset to what matters.** Only lines and cables enter the
coverage calculation. The remaining counts are:

- Transmission lines: 374
- Distribution lines: 9
- Unknown-voltage lines: 226
- Submarine cables (`power=cable`): 44
- Substations: 121

The distribution count of nine is, by itself, the answer to the question
that triggered Phase 1A. OSM has effectively no distribution data for
Visayas. Phase 1C is the whole job, not a polish step.

**§3. Per-province line-km via clipped overlay.** Lines cross
provincial boundaries, so a `sjoin` would double-count. The audit uses
`gpd.overlay(..., how='intersection')` in UTM 51N (EPSG:32651) so that
each line is clipped to each province it touches and the resulting
geometry length is the true intra-province contribution. The
transmission-km column reveals the structural picture sharply:

```
Leyte                1889.7
Cebu                 1789.3
Samar                1275.6
Negros Occidental     386.9
Bohol                 380.2
Northern Samar        272.2
Negros Oriental       142.8
Southern Leyte         83.9
Iloilo                 42.2
Aklan, Antique, Biliran, Capiz, Eastern Samar,
Guimaras, Siquijor                           0
```

Seven provinces have *zero* OSM transmission line-km. Panay is the
worst — three of its four provinces (Aklan, Antique, Capiz) are empty,
and Iloilo has only 42 km. Cebu and Leyte and Samar are well-mapped;
everything else is in trouble or absent.

**§4. Substation count and submarine presence.** Substations are
point-counted with a representative-point sjoin (handles the 112
polygon-substations correctly). Cebu has 43, Leyte 19, Negros
Occidental 12, the rest in single digits. Submarine cables touch eight
provinces — Bohol, Cebu, Eastern Samar, Leyte, Negros Occidental,
Negros Oriental, Northern Samar, Southern Leyte — which matches the
known interconnection map (Leyte–Cebu, Cebu–Negros, Negros–Panay via
the Hilutangan / Bantayan straits, and the Samar–Leyte San Juanico
crossing).

**§5. Scoring rubric.** Two 0–3 scores per province. The transmission
score combines line-km and substation count; the distribution score is
line-km alone:

```python
def score_tx(km, n_subs):
    if km == 0 and n_subs == 0: return 0
    if km >= 150 and n_subs >= 3: return 3
    if km >= 30 and n_subs >= 2:  return 2
    return 1

def score_dx(km):
    if km == 0:    return 0
    if km >= 500:  return 3
    if km >= 50:   return 2
    return 1
```

`distribution_score` feeds the Phase 1C class assignment:
`0 → osm_empty`, `1 → osm_partial`, `2–3 → osm_good`.

### What the table actually says

The verbatim Phase 1C scope from `coverage_audit.csv`:

| Class       | Count | Provinces |
|-------------|-------|-----------|
| osm_empty   | 12    | Biliran, Bohol, Cebu, Guimaras, Negros Occidental, Negros Oriental, Aklan, Antique, Capiz, Iloilo, Eastern Samar, Siquijor |
| osm_partial | 4     | Leyte, Southern Leyte, Northern Samar, Samar |
| osm_good    | 0     | — |

Twelve provinces will get fully-synthesised distribution networks. Four
will use whatever OSM has as skeleton and infill the rest. Zero
provinces are good enough to use as-is. The Phase 1C generator is no
longer a "nice to have" — it is on the critical path for three
quarters of the Visayas footprint.

Worth flagging: a handful of provinces have meaningful
`unknown_voltage_km` — Samar 230 km, Eastern Samar 166 km, Leyte 73 km
— that are almost certainly real transmission lines lacking a `voltage`
tag in OSM. Phase 1B has a chance to recover these by snapping endpoints
to known-voltage substations and inheriting the voltage, but for now
they sit in their own column so they are not silently dropped.

The per-island summary lines up with the province table:

```
island_name  provinces  tx_km   dx_km  substations  any_submarine
Biliran              1     0.0    0.0            1          False
Bohol                1   380.2    0.0            9           True
Cebu                 1  1789.3    0.0           43           True
Guimaras             1     0.0    0.0            0          False
Leyte                2  1973.6    0.2           22           True
Negros               2   529.7    0.0           21           True
Panay                4    42.2    0.0            1          False
Samar                3  1547.8    0.0           13           True
Siquijor             1     0.0    0.0            1          False
```

Panay is the standout problem. Four provinces, one substation, 42 km of
transmission across the whole island. The visible 138 kV / 230 kV
backbone that runs Iloilo–Panay–Negros is simply not in OSM. Phase 1B
will have to lean on the v1 hand-curated CSV, the published NGCP
single-line diagrams, or both, to reconstruct it.

### Output and downstream consumers

The audit writes
[backend/data/processed/coverage_audit.csv](backend/data/processed/coverage_audit.csv).
Phase 1B reads `submarine_present` and `substation_count` for sanity
checks (a province with `submarine_present=True` but zero substations is
a topology error waiting to happen). Phase 1C reads `phase1c_class` per
province to branch into `osm_empty` (full synthesis) or `osm_partial`
(OSM skeleton + infill).

---

## Days 6–10 — Phase 1B: Transmission cleaning

Phase 1B turns the raw OSM dump and the Phase 1A audit into the two
artifacts every later phase keys off:
[backend/data/processed/buses.csv](backend/data/processed/buses.csv) and
[backend/data/processed/lines.csv](backend/data/processed/lines.csv).
All of the work lives in
[notebooks/02_transmission_cleaning.ipynb](notebooks/02_transmission_cleaning.ipynb)
— thirteen numbered sections that map almost one-to-one onto the v2
plan's 1B.1 through 1B.5 steps, plus the bus-voltage assignment and
schema-finalisation passes that the plan glosses over.

### §1–2 — Voltage filter and geometry repair

The voltage parser is lifted directly from the audit notebook, so the
two pipelines agree on what counts as transmission. The selection rule
admits any line whose parsed `voltage_kv_max ≥ 60`, *plus* every
`power=cable` feature regardless of voltage tag — submarine cables are
often missing the tag, and dropping them on that basis would silently
disconnect the inter-island network.

```python
is_line  = raw['power'].isin(['line', 'cable']) & raw.geometry.geom_type.isin(['LineString', 'MultiLineString'])
is_tx_v  = raw['voltage_kv_max'] >= 60
is_cable = raw['power'] == 'cable'
lines_raw = raw[is_line & (is_tx_v | is_cable)].copy()
# → 396 lines (352 overhead, 44 cable)
```

`explode(index_parts=False)` flattens MultiLineStrings into individual
segments; segments < 1 m get dropped as numerical noise. Everything
that follows operates in EPSG:32651 (UTM 51N) so distances and lengths
are in real metres.

### §3–4 — Endpoints and substation prep

Every line contributes two endpoints. Substations are projected to
UTM, each gets a stable identifier (slugified `name` if present, else
`sub_osm_{idx}`), and a `representative_point()` so polygon-substations
and node-substations are treated identically downstream.

```
Total endpoints: 792 (= 2 × 396 lines)
Substations: 121 | named: 95
```

### §5 — Clustering via NetworkX connected components

The v2 plan calls for a shapely `STRtree` plus hand-rolled union-find
to snap endpoints. The notebook gets the same result by building a
NetworkX graph and reading off `connected_components`, which is
shorter, easier to reason about, and trivial to instrument:

```python
G = nx.Graph()
G.add_nodes_from((('ep', i) for i in range(len(ep_geoms))))

# Endpoint-endpoint edges within SNAP_M (55 m)
pairs = ep_tree.query(ep_geoms, predicate='dwithin', distance=SNAP_M)
for a, b in zip(*pairs):
    if a < b:
        G.add_edge(('ep', int(a)), ('ep', int(b)))

# Substation-endpoint edges within SUB_MATCH_M (500 m) of substation polygon
sub_buffered = [g.buffer(SUB_MATCH_M) for g in subs_m.geometry]
sub_tree = STRtree(sub_buffered)
ep_to_sub_pairs = sub_tree.query(ep_geoms, predicate='intersects')
for ep_idx, sub_idx in zip(*ep_to_sub_pairs):
    G.add_edge(('ep', int(ep_idx)), ('sub', int(sub_idx)))

components = list(nx.connected_components(G))
```

Each component becomes one bus. Components that contain a substation
node inherit that substation's `bus_id`; the rest are synthetic tower
buses named `tower_NNNN`. Two diagnostics fall out of the same pass:

- **2 382 endpoint-endpoint edges** added at 55 m tolerance, **816**
  endpoint-substation edges at 500 m, total **3 198** edges across
  **860** nodes (792 endpoints + 68 substations that found at least
  one nearby endpoint).
- **9 components with > 1 substation** — pairs of distinct substations
  pulled into the same cluster by the 500 m radius. These are the
  cases the plan v2 warned about as the failure mode of bumping the
  tolerance. Nine over-merges is small enough to accept for now.

### §7 — Province assignment and the `MAX_OFFSHORE_KM` gate

The first sjoin against province polygons leaves 27 buses unassigned.
A naive nearest-polygon snap would assign them to whichever Visayas
province happened to be closest — except many of these buses are
nowhere near Visayas:

| Where they actually sit                  | What naive snap chose       | True distance |
|------------------------------------------|-----------------------------|---------------|
| Sorsogon / Camarines Sur (Luzon)         | "Northern Samar"            | up to 174 km  |
| Surigao del Norte / del Sur (Mindanao)   | "Southern Leyte"            | up to 110 km  |
| Masbate (Region V)                       | "Northern Samar"            | ~50 km        |

These are the Leyte–Luzon HVDC north terminal, Mindanao 138 kV
substations the bbox accidentally caught, and the Masbate substation —
none of them belong in a Visayas-only model. A 5 km cutoff
distinguishes "submarine cable terminal slightly offshore of an
island" from "feature in another major landmass entirely":

```python
MAX_OFFSHORE_KM = 5
nearest = gpd.sjoin_nearest(unassigned_m, prov_m,
                            how='left', distance_col='snap_dist_m')
in_range  = nearest_map[nearest_map['snap_dist_m'] <= MAX_OFFSHORE_KM * 1000]
out_range = nearest_map[nearest_map['snap_dist_m']  > MAX_OFFSHORE_KM * 1000]
```

On the current dump every single one of the 27 unassigned buses is
> 5 km from any Visayas polygon, so all 27 get dropped (and the 26
lines that referenced them get dropped downstream in §9's
orphan-bus filter). Without the cutoff the bus table silently
contained Luzon HVDC infrastructure tagged as Visayas — a quiet but
load-flow-breaking error.

### §8–9 — Lines, self-loops, and impedance by class

Each endpoint inherits its cluster's `bus_id` via the `ep_to_cluster`
map; the lines table is then `(from_bus, to_bus, length_km, voltage_kv,
...)`. A non-trivial cleanup pass happens here:

- **176 self-loops removed** — lines whose two endpoints snapped into
  the same cluster. That is 44% of the original 396 segments. These
  are jumpers inside substations, bus-bar links, and very short
  internal connections; they are not transmission lines and would only
  pollute the topology.
- **26 orphan lines removed** — at least one endpoint referenced a
  bus dropped by the `MAX_OFFSHORE_KM` gate.

After both passes: **194 lines**. Impedance comes from a small lookup
keyed on voltage class:

| Voltage | r Ω/km | x Ω/km | max kA |
|---------|--------|--------|--------|
| 60 kV   | 0.18   | 0.42   | 0.45   |
| 69 kV   | 0.15   | 0.40   | 0.50   |
| 138 kV  | 0.08   | 0.40   | 0.70   |
| 230 kV  | 0.05   | 0.40   | 0.90   |
| 350 kV  | 0.04   | 0.30   | 1.20   |
| 500 kV  | 0.03   | 0.30   | 1.50   |

Submarine cables (`power=cable`) override the table entirely with the
XLPE values the v2 plan specifies: `r=0.0754`, `x=0.121`,
`max_i_ka=0.645`. Cables without a parsed voltage default to 138 kV —
the typical inter-island link voltage.

### §10–11 — Bus voltage and schema finalisation

A bus's nominal voltage is the **max** of the voltages of every line
incident to it. A substation serving both a 230 kV bay and a 138 kV
bay therefore comes out at 230 kV — Phase 2's topology validation will
later insert explicit transformers between mismatched voltage levels,
but for the Phase 1 deliverable the max-voltage rule is the cleanest
single-bus representation.

The final schema rename matches `init.sql` exactly:

```
buses.csv: bus_id, name, lat, lon, voltage_kv, province, island,
           bus_type, p_mw, q_mvar, is_synthetic, data_source
lines.csv: line_id, from_bus, to_bus, voltage_kv, length_km,
           r_ohm_per_km, x_ohm_per_km, max_i_ka, is_submarine,
           cable_type, is_synthetic, data_source
```

Tower buses get `is_synthetic=True` so they can be distinguished from
real substations in the eventual map; everything carries
`data_source='osm'`.

### §12 — Validation against the plan rubric

Five assertions and three sanity checks. Every assertion passes:

| Check                                        | Result                  | Plan target |
|----------------------------------------------|-------------------------|-------------|
| `bus_id` unique                              | ✓                       | required    |
| `line_id` unique                             | ✓                       | required    |
| All `from_bus` / `to_bus` reference real buses | ✓                     | required    |
| All buses have province + island             | ✓                       | required    |
| Substation buses                             | **101**                 | 80–150 ✓    |
| Tower (synthetic snap) buses                 | 85                      | —           |
| Total buses                                  | 186                     | —           |
| Lines                                        | 194 (21 submarine)      | —           |
| **Connected components**                     | **67** (51 isolated)    | **1**       |

The bus count is comfortably inside the rubric. The connectivity is
not. The v2 plan explicitly flagged the snapping tolerance as the
highest in-phase risk and said to iterate it based on Phase 2
connectivity feedback; this is exactly that signal. The big component
is 79 buses, the next largest is 14, and 51 buses are completely
isolated — substations OSM has tagged with no incident lines in the
pulled extract. Per-island:

```
Biliran      buses=  1   components=1
Bohol        buses= 14   components=5
Cebu         buses= 54   components=15
Leyte        buses= 45   components=17
Negros       buses= 38   components=16
Panay        buses=  2   components=1
Samar        buses= 31   components=17
Siquijor     buses=  1   components=1
```

Cebu, Leyte, Negros, and Samar each fragment into 15–17 pieces, which
is far too high for a real transmission backbone. The fix is a Phase 2
question: either raise `SNAP_M` from 55 m, raise `SUB_MATCH_M` from
500 m, or import the v1 hand-curated CSV as a "known interconnections"
overlay that bridges OSM gaps.

### Submarine layer is at least directionally right

```
Submarine lines: 21
Voltage distribution: 138 kV → 16,  230 kV → 4,  350 kV → 1
```

That matches what the real Visayas grid looks like: a 138 kV
inter-island spine (Cebu–Negros, Cebu–Bohol, Leyte–Samar via the San
Juanico crossing), a few 230 kV crossings, and the lone 350 kV remnant
of the Leyte–Luzon HVDC AC stub (the Luzon-side terminal was correctly
dropped by §7's offshore gate, leaving one orphaned segment).

### Output

```
Wrote ../backend/data/processed/buses.csv  (186 rows)
Wrote ../backend/data/processed/lines.csv  (194 rows)
```

Both files conform exactly to the `init.sql` schema. Phase 1C can now
treat each substation in `buses.csv` as a candidate root for a
synthetic distribution tree, and Phase 2 can read both files into
pandapower and tell us exactly where the connectivity breaks.

---

## Days 11–15 — Phase 1C: Synthetic distribution

Phase 1A confirmed it and Phase 1B underlined it: OSM has effectively
no distribution data anywhere in Visayas. Zero provinces classified
`osm_good`, four `osm_partial` with single-digit line counts, twelve
`osm_empty`. Phase 1C builds the distribution layer from scratch and
appends it to the same `buses.csv` and `lines.csv` the transmission
pipeline produced, so the downstream PostGIS loader sees one
contiguous network.

The work lives in
[notebooks/03_synthetic_distribution.ipynb](notebooks/03_synthetic_distribution.ipynb).
It writes back the same two CSVs (now with the synthetic rows
appended) plus a per-province
[synth_distribution_summary.csv](backend/data/processed/synth_distribution_summary.csv).

### Approach: radial fan-out from every substation

The v2 plan's `generate_radial_distribution` starter places feeder
endpoints with rejection sampling and linear branches. The notebook
keeps that shape and pins four constants that determine the whole
output:

```python
DIST_VOLTAGE_KV     = 13.8       # standard PH primary distribution
N_FEEDERS_PER_ROOT  = 4
BRANCHES_PER_FEEDER = 6
LOAD_PER_BUS_MW     = 1.5        # peak P per distribution bus, PF 0.9
RNG = np.random.default_rng(seed=20260511)   # deterministic synthesis
```

Each root (transmission substation) gets four feeders. Each feeder is
a six-bus chain extending outward. Feeders fan out at evenly spaced
bearings around the root (with a random phase offset so neighbouring
substations don't all radiate in the same pattern). Each branch bus
is placed in a ±35° wedge in the chosen direction, at progressively
greater distance, with rejection sampling against the province
polygon so no feeder leaves its home province:

```python
def random_point_in_polygon(poly, around_point_m, min_dist_m, max_dist_m,
                            bearing_rad, rng):
    wedge_half_width = math.radians(35)
    for _ in range(MAX_REJECT_TRIES):
        d = rng.uniform(min_dist_m, max_dist_m)
        theta = rng.uniform(bearing_rad - wedge_half_width,
                            bearing_rad + wedge_half_width)
        x = around_point_m.x + d * math.cos(theta)
        y = around_point_m.y + d * math.sin(theta)
        p = Point(x, y)
        if poly.contains(p):
            return p
    return None
```

The seeded RNG (`20260511`) means re-running the notebook produces
byte-identical output, which matters for downstream caching and PR
diffs.

### Virtual roots for the four Panay/Guimaras provinces

Phase 1B left Aklan, Antique, Capiz, and Guimaras with zero
transmission substations — they got nothing from OSM and they have no
real anchor. The notebook synthesises a placeholder root at the
province's `representative_point()`:

```
sub_synth_aklan      Aklan      Panay     11.626  122.227
sub_synth_antique    Antique    Panay     11.117  122.146
sub_synth_capiz      Capiz      Panay     11.376  122.645
sub_synth_guimaras   Guimaras   Guimaras  10.580  122.608
```

Each one is tagged `bus_type='substation_synth'`, `is_synthetic=True`,
`data_source='synthetic'`, and given a placeholder 138 kV nominal
voltage. These four buses are *not* connected to the Visayas
transmission graph — they each anchor an isolated 24-bus distribution
mini-grid. Phase 2 will surface those mini-grids as unsupplied
components; filling them in is a Phase 1B-revisit problem (import the
v1 hand-curated CSV) rather than a Phase 1C problem.

### Loads: simple per-bus heuristic

Every distribution bus carries `p_mw=1.5`, `q_mvar=0.726` (PF 0.9 → Q
= P · tan(arccos 0.9) ≈ 0.484 · P). The plan v2 calls for "0.5–2.0 MW
per feeder section" and gestures at population-density × land-use
weighting; the notebook picks the midpoint of that range and applies
it uniformly. Province-level peak load then falls out as
`24 · n_roots · 1.5 MW`, modulo feeders that ran out of polygon space
before placing all six branches.

### Numbers that landed

```
Real transmission substations as roots: 101
Virtual roots created:                    4
Total roots:                            105

Synthesised distribution buses:       2 227
Synthesised distribution lines:       2 227
Synthesised peak load:                3 340 MW
```

Per-province load (top half):

| Province           | Roots | Synth buses | Peak MW |
|--------------------|------:|------------:|--------:|
| Cebu               |    38 |         812 |  1 218  |
| Leyte              |    17 |         364 |    546  |
| Negros Occidental  |    10 |         223 |    335  |
| Bohol              |     9 |         186 |    279  |
| Negros Oriental    |     9 |         170 |    255  |
| Samar              |     7 |         149 |    224  |
| Northern Samar     |     3 |          66 |     99  |
| Southern Leyte     |     3 |          49 |     74  |
| Eastern Samar      |     2 |          48 |     72  |
| Iloilo             |     1 |          24 |     36  |
| Aklan / Antique / Capiz / Guimaras | 1 each | 24 each | 36 each |
| Biliran / Siquijor |     1 |       18/22 |  27/33  |

The 3 340 MW Visayas-wide peak is ~50% over the published 2023
NGCP-Visayas peak of about 2 200 MW. Reasonable order of magnitude
for a uniform 1.5 MW/bus heuristic; tuning is a Phase 2 calibration
exercise. The lopsidedness — Cebu at 1.2 GW vs Iloilo at 36 MW —
mirrors the OSM substation count imbalance and is the symptom worth
remembering, not the cause.

### Connectivity: better, but not because we fixed transmission

```
Combined graph (transmission + distribution): 71 components
Largest component:  881 buses
Next four sizes:    203, 28, 26, 26
Isolated buses:     1
```

Pre-1C the transmission graph had 67 components, 51 of which were
isolated substations OSM had tagged with no incident lines. Phase 1C
gave each of those substations four feeders of six buses, so the
isolated count collapsed from 51 to 1. The component count only went
*up* from 67 to 71 — the four new virtual roots in Aklan / Antique /
Capiz / Guimaras each contribute a fresh disconnected mini-grid. The
underlying transmission fragmentation is unchanged; distribution
synthesis just gave the fragments more buses.

### Schema and output

All assertions in §5 pass: `bus_id` and `line_id` unique, every
`from_bus`/`to_bus` references a real bus, every bus has a province.
The CSV totals are:

```
buses.csv  2 417 rows  (186 transmission OSM + 4 virtual + 2 227 distribution)
lines.csv  2 421 rows  (194 transmission OSM + 2 227 distribution)
```

Voltage / source / synthetic breakdown:

```
bus_type:         distribution 2227   substation 101   tower 85   substation_synth 4
is_synthetic:     True 2316   False 101
data_source:      synthetic 2231   osm 186
line voltages:    13.8 kV 2227   138 kV 92   69 kV 49   230 kV 36
                  350 kV 13   60 kV 4
line-km total:    10 215 km 13.8 kV (distribution)
                   6 466 km 60–350 kV (transmission)
```

The two CSVs are the Phase 1 deliverable. They are ready to be loaded
into PostGIS (the schema columns match `init.sql` exactly) and ready
to be fed into pandapower in Phase 2, where the topology validator
will tell us exactly how many of those 71 components actually need
bridging before a load flow can converge.

---

## Day 16 — v1 hand-curated substation integration

A 53-row [data/buses.csv](data/buses.csv) surfaced in the repo —
NGCP-style names (`04BABATNGN`, `08ILOILO1`, `05CEBU`, …), coordinates
in `(x, y)`, voltage in `v_nom`, and a `bus_type` field that separates
substations from generators and BESS. It is the predecessor v1
artifact: hand-curated, low row count, but covering the structural
gaps OSM never tagged — especially the Panay backbone, the Ormoc
350 kV HVDC south terminal, and named generators (Tongonan, Palinpinon
×2, Therma Visayas, Kepco SPC, Helios, Nabas).

This was integrated in two safe passes. Step 3 (synthesise lines
between the new substations) is deferred until the map is reviewed.

### Step 1 — Name reconciliation
[notebooks/04_name_reconciliation.ipynb](notebooks/04_name_reconciliation.ipynb)

Each v1 entry is matched against the existing
`bus_type ∈ {substation, substation_synth}` set in `buses.csv` via
`geopandas.sjoin_nearest` in UTM 51N, capped at a `MAX_MATCH_KM = 1.0`
tolerance. A first run at 2 km produced one borderline rename
(`sub_osm_2` → "Cebu main substation" at 1 489 m) that was suspicious
enough to revert by tightening the tolerance to 1 km and re-running
the full Phase 1B → 1C → 04 pipeline. Both upstream notebooks are
deterministic, so this is a one-command revert.

```
v1 entries:                                       53
Matched within 1 km:                              27
Unmatched (candidates for Step 2):                26

Match distance distribution (m):
  min 46  /  median 116  /  75% 202  /  max 747
```

The match table has three collision groups — multiple v1 entries
landing on the same OSM bus — which the notebook resolves by keeping
the closest and reporting the rest for Step 2:

| OSM bus                     | v1 candidates              | Kept (dist)          | Pushed to Step 2          |
|-----------------------------|----------------------------|----------------------|---------------------------|
| `sub_bagolibas_substation_48` | Sta. Rita, Sta. Rita tap   | Sta. Rita (46 m)     | Tap (same site, 46 m)     |
| `sub_magdugo_substation_72`   | Toledo BESS, Toledo, Magdugo | Toledo BESS (116 m) | Toledo, Magdugo           |
| `sub_naga_substation_16`      | Colon, Kepco SPC           | Colon (152 m)        | Kepco SPC (714 m, separate plant) |

Net effect: **23 OSM buses got a proper NGCP-style name** (most
visibly the four buses tagged generically as `sub_osm_2`,
`sub_osm_13`, etc., and the two duplicate `sub_national_grid_corporation_of_the_philippines_*`).
A `v1_code` and `v1_bus_type` column were added to `buses.csv` so the
NGCP identifier and the v1 classification stay attached to each
matched row for the Phase 2 generator / HVDC setup.

### Step 2 — Import the 26 unmatched v1 entries as new buses
[notebooks/06_v1_substation_import.ipynb](notebooks/06_v1_substation_import.ipynb)

The unmatched 26 are real facilities OSM simply doesn't have. They
land in `buses.csv` with:

```
bus_id        = 'v1_' + v1_name.lower()         # e.g. v1_08iloilo1
data_source   = 'v1_curated'
is_synthetic  = False                           # real facility, just human-sourced
province      = sjoin_within(psgc_provinces)    # not from v1's island tag
island        = derived from province
bus_type      = v1's bus_type
              # substation: 20, generator: 5, bess: 1
```

**No edges are added.** The new buses appear as labelled dots; the
graph topology is unchanged. This was a deliberate design choice — it
keeps the map improvement reversible and decouples it from the
higher-risk question of *how* to connect them.

Two `island` disagreements between v1's own tag and the spatial join
surfaced — both went to sjoin:

| v1 entry             | v1 island | sjoin island | Why sjoin wins                                  |
|----------------------|-----------|--------------|-------------------------------------------------|
| `04BABATNGN` Babatngon  | Samar     | Leyte        | v1's own description says "Northern Leyte". v1's island tag was wrong. |
| `08BVISTA` Buena Vista  | Panay     | Guimaras     | Coords (10.72N, 122.66E) sit inside the Guimaras polygon; Buena Vista is a known town in Guimaras. v1's `Iloilo` description was geographic shorthand. |

The Buena Vista correction means **Guimaras gained its first real
138 kV transmission substation**, where before it had only the
synthetic root from Phase 1C.

### Aggregate impact

```
Buses before v1 work:     2 422
Buses after Step 2:       2 448      (+26)

By data_source:           osm 186  /  synthetic 2 236  /  v1_curated 26
By bus_type:              substation 121   (101 osm + 20 v1)
                          tower 85         (osm-snapped synthetic-flagged)
                          substation_synth 4
                          generator 5      (all v1_curated)
                          bess 1           (v1_curated Kabankalan)
                          distribution 2 232
```

Per-province substation-class count (substation + synth root +
generator + hvdc + bess):

| Province           | OSM | Synth root | v1 import | Total |
|--------------------|----:|-----------:|----------:|------:|
| **Iloilo**         |   1 |          0 |     **6** |  **7** |
| Cebu               |  38 |          0 |         5 |    43 |
| Leyte              |  17 |          0 |         3 |    20 |
| Negros Occidental  |  10 |          0 |         4 |    14 |
| Negros Oriental    |   9 |          0 |         3 |    12 |
| Bohol              |   9 |          0 |         2 |    11 |
| Samar              |   7 |          0 |         0 |     7 |
| Northern Samar     |   3 |          0 |         0 |     3 |
| Southern Leyte     |   3 |          0 |         0 |     3 |
| Eastern Samar      |   2 |          0 |         0 |     2 |
| Aklan              |   0 |          1 |         1 |     2 |
| Capiz              |   0 |          1 |         1 |     2 |
| Guimaras           |   0 |          1 |         1 |     2 |
| Biliran            |   1 |          0 |         0 |     1 |
| Siquijor           |   1 |          0 |         0 |     1 |
| **Antique**        |   0 |          1 |         0 |     1 |

Iloilo's seven-substation jump from one is the single biggest map
improvement of the integration. Antique is the one province where
neither OSM nor v1 has anything — its only node remains the
`sub_synth_antique` virtual root from Phase 1C.

### Generators and BESS are now properly typed

A side effect that matters for Phase 2: the synthetic generation
metadata pandapower needs is finally present, instead of hiding inside
generic `bus_type='substation'` rows.

```
v1_05therma     Therma Visayas power plant, Cebu          generator
v1_08nabas      Nabas wind farm, Aklan                     generator
v1_04tongona    Tongonan geothermal, Leyte                 generator
v1_06pgpp1      Palinpinon geothermal unit 1, Negros Or.  generator
v1_06pgpp2      Palinpinon geothermal unit 2, Negros Or.  generator
v1_06kbanbess   Kabankalan BESS, Negros Occidental         bess
```

The HVDC node from the matched set is also explicit:
`sub_ormoc_converter_station_105` carries `v1_bus_type='hvdc'` after
Step 1, so Phase 2's load flow setup can treat it as the south-side
import terminal.

### Step 3 — Synthesize transmission lines for the 26 v1 buses
[notebooks/07_v1_line_synthesis.ipynb](notebooks/07_v1_line_synthesis.ipynb)

Step 2 left the 26 v1 buses as labelled but unconnected dots. Step 3
adds 24 transmission lines in two passes:

**Panay MST backbone (9 lines).** Panay had no OSM transmission, so
there is no existing graph to spur into. The 9 v1 Panay/Guimaras
buses plus the one matched OSM bus `sub_osm_4` (Concepcion) are
projected to UTM 51N and a SciPy `minimum_spanning_tree` is run over
the 10×10 distance matrix. That gives a deterministic, plausible tree
topology of 9 edges. Two attribute rules applied to every line:

```python
voltage_kv  = min(from.voltage_kv, to.voltage_kv)   # mixed kV ⇒ lower side
is_submarine = (from.island != to.island)            # island crossing ⇒ XLPE
```

The MST correctly catches the Iloilo Strait crossing
(`v1_08bvista` Guimaras → `v1_08iloilo1` Iloilo, 7.3 km marked
submarine, XLPE impedance applied) and the Bantap 69 kV
sub-transmission tap (1.8 km from Iloilo 1, voltage clamped to 69 kV
rather than 138). The longest edge is Nabas → Panitan at 83.8 km —
plausible given Nabas wind farm's remote location in northern Aklan.

| from        | to           | kV  | km   | submarine |
|-------------|--------------|----:|-----:|:---------:|
| Bantap      | Iloilo 1     |  69 |  1.8 |           |
| Bantap      | Sta. Barbara |  69 | 12.0 |           |
| Buena Vista | Iloilo 1     | 138 |  7.3 | ✓ XLPE    |
| Dingle      | San Jose     | 138 | 10.7 |           |
| San Jose    | Sta. Barbara | 138 | 18.2 |           |
| Barotac     | Dingle       | 138 | 26.2 |           |
| Barotac     | Concepcion   | 138 | 32.3 |           |
| Panitan     | Concepcion   | 138 | 49.2 |           |
| Nabas       | Panitan      | 138 | 83.8 |           |

**Non-Panay spurs (15 lines, 2 unmatched).** For the 17 v1 buses
landing in islands that already have OSM transmission, the rule is:
project to UTM, restrict candidates to existing transmission-eligible
buses (`bus_type ∈ {substation, tower, substation_synth}`,
`data_source ≠ v1_curated`) in the **same island**, pick the nearest
within `SPUR_MAX_KM = 15`, and lay down one line. Same voltage and
submarine rules as Panay.

Median spur length 3.4 km; 11 of 15 are under 8 km. Notable:

- `v1_05cebu` (Cebu main) spurs to `sub_osm_2` at 1.5 km — the same
  bus that almost got renamed in Step 1 before we tightened to 1 km.
  Treating it as a neighbour instead of an alias is a better outcome.
- `v1_04tongona`, `v1_06mabinay`, `v1_06pgpp1`, `v1_06pgpp2`: 0.12 –
  0.56 km spurs. These v1 power-plant buses sit on top of existing
  OSM towers or substations, so the spurs are effectively transformer
  pigtails. Phase 2 may want to merge them entirely.
- `v1_05daanbntay` and `v1_05daanlunsod` both spur to
  `sub_medellin_load_end_substation_23` at identical 5.33 km — v1's
  CSV lists both at the same `(10.466498, 124.006598)`. They are
  almost certainly paired bays at one physical site; a follow-up
  Step 4 should collapse them.

**Two spurs unmatched** because nearest in-island transmission bus is
33.2 km away, well past the cap:

- `v1_06kabankalan` (Kabankalan substation, southern Negros Occ)
- `v1_06kbanbess` (Kabankalan BESS, co-located)

Southern Negros Occidental has no OSM transmission whatsoever. These
two stay as isolated labelled dots until either the cap is raised
(risky — synthesised 33 km lines start to look like fiction) or
real NGCP data fills the gap.

### Aggregate impact on transmission connectivity

```
                          Phase 1B    Step 3   Δ
Transmission components       67        18    −49 (−73%)
Isolated buses (size 1)       51         0    −51
Largest component             79        90    +11
```

Per island:

| Island   | Phase 1B | Step 3 | Notes                                |
|----------|---------:|-------:|--------------------------------------|
| Panay    |    1 (2 buses) | **1 (10 buses)** | Built from MST; backbone now exists. |
| Bohol    |        5 |      1 | Both Bohol spurs hit the existing mesh. |
| Cebu     |       15 |      4 | Five v1 spurs collapsed the fragments. |
| Leyte    |       17 |      4 | Three v1 spurs collapsed the fragments. |
| Negros   |       16 |      5 | Kabankalan pair still isolated.       |
| Samar    |       17 |      9 | No v1 buses landed in Samar — unchanged. |
| Biliran  |        1 |  isolated | Single bus, no incident lines.    |
| Siquijor |        1 |  isolated | Single bus, no incident lines.    |

The 67 → 18 collapse came almost entirely from giving previously
unattached substations one short spur each. Samar is the remaining
fragmented island; its 9 components stem from missing OSM line
geometry rather than missing nodes.

### Output

```
buses.csv     2 448 rows    (unchanged since Step 2)
lines.csv     2 450 rows    (+24 from this pass)
synth_v1_lines.csv  24 rows traceability file for the new edges
```

All 24 new lines carry `data_source='synthetic_v1'`,
`is_synthetic=True`. The line_id prefixes are `line_synth_panay_*` for
the MST and `line_synth_spur_*` for the spurs.

### Step 3b — Hand-connect the Kabankalan pair
[notebooks/08_kabankalan_handconnect.ipynb](notebooks/08_kabankalan_handconnect.ipynb)

Step 3 left two v1-imported Negros Occidental buses isolated because
the nearest existing transmission bus was 33 km away — past the
15 km auto-spur cap. Instead of raising the cap globally (risky:
any subsequent v1 bus could be matched to a far-away neighbour
without justification), the right move was to **hand-encode the
known NGCP topology** for just these two cases.

Kabankalan's real neighbour on the Negros backbone is Mabinay
(`v1_06mabinay`), already imported in Step 2 and connected to the
OSM mesh by a 0.13 km spur to `tower_0048`. So one named line wires
Kabankalan into the existing graph without ever needing the cap to
lift. Kabankalan BESS sits 400 m from the substation — a co-located
pigtail.

```
line_handcoded_kabankalan_mabinay         33.12 km  138 kV overhead
line_handcoded_kabankalan_bess_pigtail     0.39 km  138 kV overhead
```

Both carry the distinct tag `data_source='synthetic_v1_handcoded'`
— different from `synthetic_v1` so the eventual map can render
hand-encoded edges in their own style (three confidence tiers:
`osm` → real geometry, `synthetic_v1` → algorithmic, then
`synthetic_v1_handcoded` → named real-grid).

The transmission-graph effect is small but exactly the right shape.
The two previously-isolated buses (which weren't even being counted,
because they had zero incident edges) joined the largest existing
component:

```
Largest component:        90 → 92 buses
Negros island components: 5 unchanged (the fix targets Kabankalan, not
                                       the four other Negros fragments)
Total transmission components: 18 unchanged
```

`lines.csv` is now 2 452 rows (+2 from Step 3).

---

## Day 17 — Distribution re-calibration for Iloilo
[notebooks/09_iloilo_redistribution.ipynb](notebooks/09_iloilo_redistribution.ipynb)

Phase 1C generated 24 distribution buses for Iloilo because Iloilo
had exactly one transmission substation in OSM (`sub_osm_4`,
Concepcion). After Steps 1–3 added six v1 substations to Iloilo
(Bantap, Barotac, Dingle, Iloilo 1, San Jose, Sta. Barbara), the
distribution layer was sized 7× too small relative to the rest of
the model. Iloilo's synthetic peak load came out at 36 MW against a
published ~250 MW real peak — wrong by a factor of seven.

The fix is a targeted re-run of Phase 1C scoped to Iloilo only. No
other province's distribution is touched, so Cebu / Negros / Leyte
etc. retain their existing feeder geometry exactly.

### Pipeline

1. Identify all Iloilo `bus_type ∈ {substation, substation_synth,
   generator, hvdc, bess}` rows in the current `buses.csv` (7 buses).
2. Drop existing Iloilo distribution buses (24) and their incident
   lines (24).
3. For each Iloilo root, run the **same** Phase 1C `synthesize_feeders_for_root`
   function — verbatim, same parameters (`N_FEEDERS_PER_ROOT=4`,
   `BRANCHES_PER_FEEDER=6`, `LOAD_PER_BUS_MW=1.5`, etc.).
4. Seed is deliberately different from Phase 1C's (`20260512` vs
   `20260511`) so the regenerated buses don't accidentally clash with
   stale IDs and stay deterministic on re-run.
5. Append, validate, save.

### Per-root output

The radial generator places each new bus inside a wedge centered on
a feeder bearing, sampled inside the Iloilo polygon. Roots near the
coast or province boundary lose some branches when the rejection
sampler runs out of tries — the theoretical max is 24 buses per
root, but coastal locations end up shorter.

| Root              | Location        | Buses |
|-------------------|-----------------|------:|
| `sub_osm_4`       | Concepcion      |  24   |
| `v1_08bantap`     | Bantap (69 kV)  |  20   |
| `v1_08barotac`    | Barotac         |  18   |
| `v1_08dingle`     | Dingle          |  24   |
| `v1_08iloilo1`    | Iloilo City     |  16   |
| `v1_08snjose`     | San Jose        |  24   |
| `v1_08stbarbra`   | Sta. Barbara    |  24   |
| **Total**         |                 | **150** |

Iloilo City and Bantap/Barotac are the three coastal-ish roots that
truncate early. The four inland roots all reach the full 24 buses.

### Result

```
Iloilo distribution buses:    24 → 150
Iloilo peak load:             36 MW → 225 MW       (target ~250 MW)
Iloilo subgraph components:   multiple → 1 (158 buses)
```

The 36 → 225 MW jump lands within 10% of the published ~250 MW
Iloilo peak — Phase 1C's `LOAD_PER_BUS_MW = 1.5` constant was
actually well-calibrated all along. The under-sizing in the original
run came purely from having one root where the real grid has seven.

### Aggregate state and the load drift it reveals

```
buses.csv     2 574 rows     (was 2 448, +126 = +150 new − 24 dropped)
lines.csv     2 578 rows     (was 2 452, +126)
```

A side effect worth flagging: total Visayas synthetic peak load
moved from 3 340 MW → **~3 529 MW**, even further over the
~2 200 MW real Visayas peak. Iloilo wasn't responsible for the
overshoot — Cebu is, with 1.2 GW of synthetic load across 38
substation roots × 24 buses × 1.5 MW. A per-province root-count
cap (or population-weighted load assignment) is the right next
calibration move; this Iloilo run was about fixing
under-representation, not over-representation.

---

## Day 18 — Parametrized re-run for the other v1-augmented provinces
[notebooks/10_redistribute_provinces.ipynb](notebooks/10_redistribute_provinces.ipynb)

Day 17 handled Iloilo specifically; eight other provinces also gained
v1 substations in Steps 1–3 but were still running on Phase 1C's
original root sets. Notebook 10 generalises notebook 09 into a
single parametrised pipeline keyed on a `TARGET_PROVINCES` list, so
the same logic that fixed Iloilo can fix the rest.

Default targets (every province with a v1 import, except Iloilo
which is already done): **Aklan, Bohol, Capiz, Cebu, Guimaras,
Leyte, Negros Occidental, Negros Oriental**.

Parameters are identical to Phase 1C and notebook 09. The only
deliberate difference is the seed (`SEED_BASE = 20260513 + i` for
the *i*-th province alphabetically), so the per-province RNG
streams are deterministic and don't collide with notebook 09's
`20260512` or Phase 1C's `20260511`. New distribution lines use the
`line_synth_redist_NNNNN` prefix so they're cleanly distinguishable
from the original Phase 1C output (`line_synth_NNNNN`) and from the
v1 line synthesis (`line_synth_panay_*` / `line_synth_spur_*`).

### A pipeline-fragility scare

The first execution of notebook 10 failed mid-cell on a regex bug
extracting `next_idx` from `line_id`s after the drop step had
removed every plain `line_synth_NNNNN` row in the kept set. While
the patch was trivial — switch to a deterministic `line_synth_redist_NNNNN`
prefix instead of incrementing from the highest existing ID —
something stranger happened between failed and re-run: `buses.csv`
silently reverted to the 186-row Phase 1B state, losing every v1
import and every distribution bus from Phase 1C and the Iloilo
re-run.

Most likely cause: an earlier turn that re-ran `02 → 03 → 04` to
fix the reconciliation tolerance left `buses.csv` in an inconsistent
state, and a subsequent partial pipeline run further trimmed it.
The pipeline isn't a single transaction — each notebook reads
`buses.csv`, transforms it, and writes back. Re-running an upstream
notebook implicitly demands a re-run of every downstream one, and
there is no enforcement.

The fix was mechanical: re-execute the whole chain in order, then
notebook 10 against the restored state.

```bash
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/02_transmission_cleaning.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/03_synthetic_distribution.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/04_name_reconciliation.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/06_v1_substation_import.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/07_v1_line_synthesis.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/08_kabankalan_handconnect.ipynb && \
.venv/bin/jupyter nbconvert --to notebook --execute \
    notebooks/09_iloilo_redistribution.ipynb
```

After the chain: 2 580 buses, 2 584 lines, exactly the Day 17 state
(modulo a 6-bus drift from RNG ordering effects across the
re-execution). Notebook 10 then ran cleanly against that input.

### Per-province before vs after

| Province           | Roots (pre) | Dist before | Dist after |   Δ |  Load before |  Load after |
|--------------------|------------:|------------:|-----------:|----:|-------------:|------------:|
| Aklan              |   2 (1 synth + 1 v1) |          24 |         44 | +20 |         36.0 |        66.0 |
| Bohol              |  11 (9 OSM + 2 v1)  |         186 |        235 | +49 |        279.0 |       352.5 |
| Capiz              |   2 (1 synth + 1 v1) |          24 |         48 | +24 |         36.0 |        72.0 |
| **Cebu**           | **43 (38 OSM + 5 v1)** |         825 |    **941** | **+116** |     1 237.5 | **1 411.5** |
| Guimaras           |   2 (1 synth + 1 v1) |          24 |         46 | +22 |         36.0 |        69.0 |
| Leyte              |  20 (17 OSM + 3 v1) |         367 |        443 | +76 |        550.5 |       664.5 |
| Negros Occidental  |  14 (10 OSM + 4 v1) |         220 |        314 | +94 |        330.0 |       471.0 |
| Negros Oriental    |  12 (9 OSM + 3 v1)  |         173 |        244 | +71 |        259.5 |       366.0 |
| **Total**          |                     |     1 843 |  **2 315** | +472 |              |             |

Every target province now has distribution feeders rooted at every
substation-class node OSM and the v1 import together produced. The
2 315 new distribution buses come from 116 substation-class roots
across the eight provinces, exactly `(43+11+14+12+20+2+2+2) × ~20`
(coastal roots truncate, so the per-root average lands near 20 not
24).

### The load drift, now harder to ignore

```
Phase 1C original (Day 11–15):     3 340 MW
After Iloilo re-run    (Day 17):   3 529 MW
After Day 18 re-run for 8 more:  → 4 254 MW
Real Visayas peak target:         ~2 200 MW
```

The model is now nearly 2× the real Visayas peak load. Cebu alone
contributes 1 411 MW — Cebu's real peak is ~500–600 MW. The
problem is structural: many OSM "substations" in Cebu City are
actually bays of the same physical facility (Naga, Compostela,
Mandaue, Magdugo, Mandugo, Lapu-Lapu Gas Insulated etc. all
cluster within a few km), but the synthesis treats each as a
distinct feeder root. A per-province root cap or a substation
merge pass is the right next calibration move.

### Connectivity gains

```
Total whole-grid components:     71  (unchanged, as expected)
Largest mesh component:        1 206 buses
Next four:                       227, 205, 75, 50
```

The largest mesh ballooned from 158 (post-Iloilo) to **1 206
buses** — almost every Cebu / Negros / Leyte / Bohol substation
now anchors a distribution tree that connects through the
submarine cables we already have. The remaining 70 components are
small isolated synthetic trees (Antique's virtual root and its 24
feeders, Biliran, Siquijor, Eastern Samar fragments, the Samar
clusters Step 3 didn't touch).

### Output

```
buses.csv     3 052 rows   (was 2 580, +472 net = +2 315 new − 1 843 dropped)
lines.csv     3 056 rows   (+472 same)
redistribute_summary.csv   8 rows traceability file
```

---

## Day 19 — Pipeline orchestrator + substation merge

Day 18 surfaced two structural problems: the load drift kept getting
worse with every distribution re-run, and the notebook chain was
silently fragile to partial / out-of-order execution. Day 19
addresses both with one new notebook and one new script.

### `scripts/run_phase1.py` — the orchestrator
[scripts/run_phase1.py](scripts/run_phase1.py)

A 90-line Python wrapper around `jupyter nbconvert --execute` that
runs the nine Phase 1 notebooks in dependency order, prints a
one-line state snapshot after each, and aborts with a useful error
on the first failure. Re-running it is now the canonical "rebuild
Phase 1 from raw OSM" operation:

```
$ python scripts/run_phase1.py

Phase 1 orchestrator — 9 notebooks queued

  [start]  ... existing state
  ▶ run    02_transmission_cleaning.ipynb  (Phase 1B: OSM transmission)
  [   5s]   186 buses (osm=186) /   194 lines
  ▶ run    03_synthetic_distribution.ipynb  (Phase 1C: initial synthetic distribution)
  [   4s]  2422 buses (osm=186, synthetic=2236) /  2426 lines
  ▶ run    04_name_reconciliation.ipynb  (Step 1: match v1 names onto OSM buses)
  ...
  ▶ run    11_substation_merge.ipynb  (Substation merge + redundant-virtual cleanup)
  [   3s]  2396 buses (osm=186, synthetic=2186, v1_curated=24) /  2403 lines
  ▶ run    09_iloilo_redistribution.ipynb  (Day 17: Iloilo distribution re-run)
  ▶ run    10_redistribute_provinces.ipynb  (Day 18: parametrised re-run for 8 provinces)

✓ pipeline complete in 31s
  [final]  2963 buses (osm=186, synthetic=2753, v1_curated=24) /  2970 lines
```

The script supports `--from` and `--to` flags to run only a slice of
the chain — useful while iterating on one step — but the default
runs everything, end to end, in about half a minute. This makes the
Day 18 failure mode (silent state inconsistency from a partial
re-run) effectively impossible: either the full chain ran and the
state is internally consistent, or it didn't.

The orchestrator is intentionally simple: a list of `(notebook,
description)` tuples plus subprocess calls. No DAG library, no
make. The notebook chain is short enough that a hand-curated list
is clearer than a generic dependency engine.

### `notebooks/11_substation_merge.ipynb` — the data cleanup
[notebooks/11_substation_merge.ipynb](notebooks/11_substation_merge.ipynb)

The structural cause of the load drift is that OSM tags adjacent
substation bays — different physical bus sections of one facility,
or paired-redundant feeders — as distinct `power=substation`
features. The synthetic distribution generator then roots 4 × 6
feeders at each one, multiplying load by the number of bays. The
v1 import made this worse in two specific cases (Daan Bantayan /
Daan Lungsod at identical coordinates; Kabankalan / Kabankalan
BESS at 0.4 km).

Notebook 11 runs after Step 3b (so all substation-class buses are
present) and before the distribution re-runs (so the merged root
set is what 09 and 10 see). Two cleanup actions in one pass:

**1. Proximity-based merge.** For each pair of substation-class
buses in the *same province* within `MERGE_KM` metres of each
other, mark one as the keeper and rewrite the other's line
endpoints onto the keeper. Keeper-selection priority:

```
data_source: v1_curated > osm > synthetic
bus_type:    substation > generator/hvdc > bess > substation_synth
name:        named > generic (sub_osm_NN / tower_NNNN)
bus_id:      lexicographic tiebreak (for determinism)
```

**The threshold choice mattered.** A first run at `MERGE_KM = 1.0`
produced three false-positive merges that had to be reverted:

- `Ormoc Solar Farm → Ormoc 350 kV substation` (different facilities,
  one is a generator and one is an HVDC import terminal)
- `Mandaue → Lapu-Lapu Gas Insulated` (one is on mainland Cebu, the
  other is across the strait on Mactan Island — OSM coords had them
  within 940 m but they are functionally separate)
- `CBP → Camputhaw` (both real Cebu substations, plausibly
  different facilities)

Tightening to `MERGE_KM = 0.5` kept the genuine same-site merges
(Daan Bantayan/Lungsod at 0 m; Kabankalan/BESS at 393 m) and
dropped all three false positives. The lesson: at the kilometre
scale, OSM has enough geocoding scatter that 1 km already catches
distinct facilities across narrow straits or shared industrial
zones. Half a kilometre is the right call for *bays of one
facility* — anything farther needs hand evidence.

**2. Redundant virtual-root cleanup.** Phase 1C added four
`substation_synth` virtual roots (Aklan, Antique, Capiz, Guimaras —
the provinces with zero OSM transmission). Step 2 then imported
real v1 substations into three of those provinces. Notebook 11
drops a virtual root if its province now has at least one
`bus_type='substation'` row, plus every bus whose `bus_id` is
prefixed `<virtual_root>_F` (its Phase 1C feeder children). The
distribution re-runs (notebooks 09 and 10) regenerate those
feeders rooted at the v1 substation instead.

A subtle thing: Aklan's only v1 entry is `v1_08nabas`, a *generator*
(Nabas wind farm), not a `bus_type='substation'`. So the test
`real_subs_per_province` does not include Aklan, and
`sub_synth_aklan` survives the cleanup. This is the right call —
a wind-farm step-up isn't structurally a transmission node feeding
distribution, so keeping the synthetic root makes more sense than
hanging Aklan's whole distribution off the wind farm.

### Results of the 0.5 km pass

```
Cluster merges (4)
  v1_05daanlunsod        → v1_05daanbntay    Cebu               (identical coords)
  v1_06kbanbess          → v1_06kabankalan   Negros Occidental  (393 m apart)
Redundant virtual roots (2)
  sub_synth_capiz        dropped — Capiz now has Panitan
  sub_synth_guimaras     dropped — Guimaras now has Buena Vista
```

That is 4 substation-class buses removed plus the two virtual
roots' 50 distribution feeder children = 52 buses gone before the
downstream redistribute. 09 and 10 then regenerate distribution
from the cleaner root set:

```
Stage                   buses    lines    Visayas load
After Step 3b           2 448    2 452     —
After merge (11)        2 396    2 403     (drop+merge applied)
After Iloilo (09)       2 522    2 529    ≈ 225 MW for Iloilo
After all provinces (10) 2 963   2 970     4 126 MW total
```

### Load drift: improved but not solved

| Stage                       | Visayas total |
|-----------------------------|--------------:|
| Phase 1C (Day 11–15)        |     3 340 MW |
| After Iloilo (Day 17)       |     3 529 MW |
| After all-province (Day 18) |     4 254 MW |
| **After merge (Day 19)**    | **4 126 MW** |
| Real Visayas peak (target)  |   ~2 200 MW |

The merge saved ~130 MW, mostly from dropping the redundant virtual
roots. The fundamental cause of the overshoot is unchanged: Cebu
still has 42 substation-class buses generating ~921 distribution
buses × 1.5 MW = 1 382 MW where the real peak is ~500–600 MW. No
proximity-based merge can fix that, because the remaining Cebu
substations are genuinely 1–3 km apart and serve distinct feeders.
The real Day 20 work is **population-weighted load assignment** —
scale each province's distribution-bus load so the province total
matches its published peak demand. That converts an unbounded
multiplier (`n_roots × 24 × 1.5 MW`) into a bounded one
(`load_target_mw / n_dist_buses`).

### Output

```
buses.csv                   2 963 rows
lines.csv                   2 970 rows
substation_merge_log.csv        4 rows traceability file
scripts/run_phase1.py            new — Phase 1 orchestrator
notebooks/11_substation_merge.ipynb  new — the cleanup
```

---

## Day 20 — Population-weighted load assignment

The remaining structural problem after Day 19: Visayas total
synthetic peak load was still 4 126 MW, ~1.88× the real
~2 200 MW. The proximity-based merge couldn't close the gap because
the remaining over-counted substations are genuinely distinct
facilities 1–3 km apart, not bays of one site.

Day 20 takes a different angle: stop using a uniform per-bus
constant (`LOAD_PER_BUS_MW = 1.5` MW) and instead anchor each
province's total to a published peak demand, distributing it
evenly across whatever distribution buses that province happens to
have. One per-province target table, one scaling notebook, one
line added to the orchestrator.

### `backend/data/boundaries/province_peak_targets.csv`
[backend/data/boundaries/province_peak_targets.csv](backend/data/boundaries/province_peak_targets.csv)

A 16-row CSV with columns `province, peak_mw, source_note`. Values
are hand-curated rough estimates: population-weighted base
(~134 W/person across the ~16.4 M Visayas population, summing to
the published ~2 200 MW) with an industrial / commercial
multiplier per province (Cebu pushed up for Cebu City + Mandaue
+ Mactan industrial corridor, Negros Occidental up for sugar
industry + Bacolod, smaller islands taken straight from population).

```
Cebu                720 MW
Negros Occidental   320 MW
Iloilo              250 MW     ← matches the published Iloilo peak we
                                 were already tracking on Day 17
Leyte               200 MW
Negros Oriental     160 MW
Bohol               120 MW
Samar                90 MW
Capiz                80 MW
Aklan                75 MW
Northern Samar       65 MW
Antique              55 MW
Eastern Samar        45 MW
Southern Leyte       40 MW
Guimaras             25 MW
Biliran              22 MW
Siquijor             15 MW
─────────────────────────
Sum               2 282 MW
```

Source note on every row records the rationale. Phase 2 calibration
should pull actual NGCP / DOE per-province load curves; for Phase 1
this is good enough to anchor the model at the right order of
magnitude.

### `notebooks/12_load_assignment.ipynb`
[notebooks/12_load_assignment.ipynb](notebooks/12_load_assignment.ipynb)

Simple by design. For each province *P* with target `T_P` and `n_P`
distribution buses:

```
per_bus_p_mw[P]  = T_P / n_P
per_bus_q_mvar[P] = per_bus_p_mw[P] × tan(arccos(PF))     # PF = 0.9
```

Apply to `bus_type == 'distribution'` rows only — transmission
substations, towers, generators, BESS, and `v1_curated` buses keep
their existing `p_mw` (almost always `NaN` at this stage). Schema
unchanged.

Wired in as the last step of `scripts/run_phase1.py`, so any
upstream change automatically propagates through the redistribution
and lands at the right per-province totals.

### Result

Every one of the 16 provinces lands at **100 % of its target** —
not because the algorithm fudges it, but because the algorithm
*is* `target / count`. The validation is that the total is
within rounding of the target sum.

```
Province              n_dist   before    after   target    pct
Cebu                     922  1383.0    720.0      720    100 %
Negros Occidental        290   435.0    320.0      320    100 %
Iloilo                   150   225.0    250.0      250    100 %
Leyte                    443   664.5    200.0      200    100 %
Negros Oriental          244   366.0    160.0      160    100 %
Bohol                    235   352.5    120.0      120    100 %
Samar                    149   223.5     90.0       90    100 %
Capiz                     24    36.0     80.0       80    100 %
Aklan                     44    66.0     75.0       75    100 %
Northern Samar            66    99.0     65.0       65    100 %
Antique                   24    36.0     55.0       55    100 %
Eastern Samar             48    72.0     45.0       45    100 %
Southern Leyte            49    73.5     40.0       40    100 %
Guimaras                  20    30.0     25.0       25    100 %
Biliran                   18    27.0     22.0       22    100 %
Siquijor                  22    33.0     15.0       15    100 %
                                                          ──────
                                       2 282 MW    2 282
```

### The drift problem, closed out

| Stage                       | Visayas total | vs ~2 200 MW |
|-----------------------------|--------------:|-------------:|
| Phase 1C (Day 11–15)        |     3 340 MW |    1.52×     |
| After Iloilo (Day 17)       |     3 529 MW |    1.60×     |
| After all-province (Day 18) |     4 254 MW |    1.93×     |
| After merge (Day 19)        |     4 126 MW |    1.88×     |
| **After load assignment (Day 20)** | **2 282 MW** | **1.04× ✓** |

The single per-province override fixed a problem that two
distribution re-runs and a substation merge could not.

### What the per-bus loads now tell us

The scaling makes a previously hidden detail visible: Capiz,
Antique, and Aklan now carry **3.3, 2.3, and 1.7 MW per
distribution bus** respectively, vs Cebu at 0.78 MW/bus. This is
the structural signal that those provinces have *too few* synthetic
distribution buses for their published peak — i.e. we under-built
Phase 1C / 10 for the sparser provinces. The flat 1.5 MW/bus
constant masked it because there was a separate per-province total
overshoot.

Phase 2 load flow will surface this concretely: a 3.3 MW load on a
13.8 kV distribution bus is plausible in itself (~138 A line
current), but a single feeder with only 24 buses for a whole
province means each bus represents a much bigger geographic area,
which translates into a longer effective feeder and more line drop.
We will see the consequence in voltage levels rather than load
totals.

### Output

```
backend/data/boundaries/province_peak_targets.csv   16 rows, hand-curated targets
notebooks/12_load_assignment.ipynb                  new — the scaling
scripts/run_phase1.py                               +1 line — wired into pipeline

buses.csv                              2 960 rows (p_mw column rewritten for dist buses)
lines.csv                              2 967 rows (unchanged)
load_assignment_summary.csv               16 rows traceability
```

Full pipeline still runs end-to-end in ~34 seconds from raw OSM.

---

## Patterns worth keeping

A few habits crystallised over the two days that are cheap to keep doing:

- **Assertion-driven notebook cells.** Every step in the boundary
  notebook ends in an `assert` against a known count, a known set, or a
  geometry-validity check. Reruns fail loud, which is exactly what you
  want when the input file silently changes.
- **The alias-table scaffold.** `GADM_TO_PSA = {}` is empty today, but
  the line is there. The next dataset that needs it will not surprise
  anyone.
- **Tolerance-based geographic validation.** ±10% on published island
  area is loose enough to allow boundary-vs-coastline drift and tight
  enough to catch Bohol.
- **Schema as a contract, written first.** `is_synthetic`,
  `data_source`, `is_submarine`, and `cable_type` exist in `init.sql`
  before there is a single row to put in them. Adding them now costs
  four lines; adding them later costs a migration and a careful audit.

---

## Phase closeout

Phase 1 ships. The handoff document — what landed, what's unresolved,
and what Phase 2 needs to know — lives at
[`../closeouts/phase-1-closeout.md`](../closeouts/phase-1-closeout.md).
Read that first; this journal is archival.
