# Philippine Power Grid Visualization Web App
## Project Plan v2 — Julius Darang
### Updated after technical review by VISAYAS POWER GRID

---

## Validation Summary of Review Feedback

| Feedback Point | Verdict | Action Taken |
|---|---|---|
| OSM distribution data gap | ✅ Confirmed risk | Added synthetic topology generator (Phase 1C) |
| Topology verification before runpp | ✅ Critical fix | Added as mandatory gate in Phase 2 |
| PostGIS from the start (not SQLite) | ✅ Accepted | Removed SQLite; PostGIS from Day 1 |
| Submarine cable flag in schema | ✅ Visayas-specific | Added `is_submarine` + impedance override to schema |
| Deck.gl vs Leaflet | ⚠️ Partially accepted | Leaflet for transmission; Deck.gl upgrade path for distribution poles |
| Timeline 7/10 (8 weeks too tight) | ✅ Confirmed | Expanded to 11 weeks; data pipeline given 3 weeks |

---

## Project Overview

A public-facing web application that visualizes the Philippine power grid at two levels:
- **Transmission** — Visayas NGCP backbone (69 kV, 138 kV, 230 kV)
- **Distribution** — Per-province distribution grids (DSA/DU level, synthetic topology where OSM is empty)

Users can switch between grid levels, filter by province or island, inspect load flow results, and export publication-quality maps.

**Data strategy:**
- Transmission → OSM extraction (coverage is adequate for major Visayas lines)
- Distribution → OSM where available; synthetic radial topology generator where OSM is empty
- Load flow → pandapower with 60 Hz, synthetic demand profiles
- Upgrade path → swap in real NGCP/DU data with zero schema changes

---

## Revised Tech Stack

| Layer | Choice | Reason / Change from v1 |
|---|---|---|
| Backend | **Python + FastAPI** | Unchanged |
| Data pipeline | **pandas + GeoPandas + OSMnx** | Unchanged |
| Synthetic topology | **NetworkX + Shapely (Steiner tree approx.)** | NEW — fills empty DU areas |
| Load flow engine | **pandapower (60 Hz)** | Unchanged |
| Topology validator | **pandapower.topology** | NEW — mandatory pre-runpp gate |
| Frontend (base) | **React + Leaflet** | Leaflet for transmission (< 500 elements) |
| Frontend (upgrade) | **Deck.gl (WebGL)** | For distribution poles (thousands of points) |
| Map tiles | **OpenStreetMap via Leaflet** | Unchanged |
| Styling | **Tailwind CSS** | Unchanged |
| Database | **PostgreSQL + PostGIS** | CHANGED — PostGIS from Day 1, no SQLite |
| Deployment | **Docker + Oracle Cloud Always Free** | Unchanged; you already have this set up |
| Export | **Matplotlib + contextily + ReportLab** | Unchanged |

---

## Updated Project Structure

```
power-grid-viz/
│
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── grid.py              # Grid data endpoints
│   │   ├── analysis.py          # Load flow endpoints
│   │   └── export.py            # PNG/PDF export
│   ├── services/
│   │   ├── osm_pipeline.py      # OSM extraction + cleaning
│   │   ├── topology_validator.py  # NEW: pre-runpp connectivity check
│   │   ├── synth_distribution.py  # NEW: synthetic DU topology generator
│   │   ├── grid_builder.py      # pandapower network builder
│   │   ├── load_flow.py         # Load flow runner
│   │   └── exporter.py          # Static map generator
│   ├── models/
│   │   ├── bus.py
│   │   └── line.py
│   ├── db/
│   │   ├── init.sql             # PostGIS schema creation
│   │   └── queries.py           # Spatial query helpers
│   └── data/
│       ├── raw/                 # Raw OSM outputs
│       ├── processed/           # Cleaned + validated GeoJSON
│       ├── synthetic/           # Synthetic load profiles + DU topologies
│       └── boundaries/          # PSGC province shapefiles
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MapView.jsx        # Leaflet map canvas
│   │   │   ├── Sidebar.jsx        # Filters + legend
│   │   │   ├── InfoPanel.jsx      # Click-to-inspect
│   │   │   ├── LayerToggle.jsx    # Transmission / Distribution / Submarine
│   │   │   ├── IslandFilter.jsx   # NEW: filter by island group
│   │   │   └── ExportButton.jsx
│   │   ├── hooks/
│   │   │   ├── useGridData.js
│   │   │   └── useLoadFlow.js
│   │   └── App.jsx
│   └── public/
│
├── notebooks/
│   ├── 01_osm_extraction.ipynb
│   ├── 02_topology_validation.ipynb   # NEW
│   ├── 03_synthetic_distribution.ipynb  # NEW
│   ├── 04_load_flow_validation.ipynb
│   └── 05_osm_coverage_audit.ipynb    # NEW
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Updated CSV Schema

All changes from v1 are marked **[NEW]** or **[CHANGED]**.

### `buses.csv`
```
bus_id, name, lat, lon, voltage_kv, province, island,
type (substation/generator/load),
p_mw, q_mvar,
is_synthetic [NEW],        ← True if generated, not from OSM or real data
data_source [NEW]          ← "osm" | "synthetic" | "real"
```

### `lines.csv`
```
line_id, from_bus, to_bus, voltage_kv, length_km,
r_ohm_per_km, x_ohm_per_km, max_i_ka,
is_submarine [NEW],        ← True for Leyte-Cebu, Cebu-Negros, Negros-Panay, etc.
cable_type [NEW],          ← "overhead" | "submarine_xlpe" | "underground"
is_synthetic [NEW],        ← True if generated
data_source [NEW]          ← "osm" | "synthetic" | "real"
```

### `load_flow_results.csv`
```
bus_id, vm_pu, va_degree, p_mw, q_mvar, loading_percent
line_id, p_from_mw, p_to_mw, loading_percent, i_from_ka
```

**Note on submarine cable impedance:**
Submarine XLPE cables have significantly lower reactance and higher capacitance than overhead lines.
Use these as approximate starting values until real parameters are available:
- `r_ohm_per_km` ≈ 0.0754 (for 630mm² XLPE)
- `x_ohm_per_km` ≈ 0.121
- `max_i_ka` ≈ 0.645
Do NOT use standard overhead line parameters for submarine sections.

---

## Phase 1A — OSM Extraction & Coverage Audit (Week 1)

### Goal: Find out exactly what OSM has before building anything else.

This is the most important step. You need to know the OSM coverage *before* designing the distribution layer.

**Step 1A.1 — Extract Visayas power infrastructure**

```python
import osmnx as ox
import geopandas as gpd

tags = {"power": ["line", "cable", "substation", "tower", "generator"]}
visayas_bbox = (9.0, 123.0, 13.0, 126.5)  # south, west, north, east

gdf = ox.features_from_bbox(*visayas_bbox, tags=tags)
gdf.to_file("data/raw/visayas_power_raw.geojson", driver="GeoJSON")
```

**Step 1A.2 — Coverage audit by island and voltage**

After extraction, immediately run a coverage audit:

```python
# Separate by voltage tag
transmission = gdf[gdf["voltage"].isin(["69000", "138000", "230000"])]
distribution = gdf[gdf["voltage"].isin(["13200", "13800", "34500"])]
unknown_voltage = gdf[gdf["voltage"].isna()]

print(f"Transmission lines found: {len(transmission)}")
print(f"Distribution lines found: {len(distribution)}")
print(f"No voltage tag (needs manual review): {len(unknown_voltage)}")

# Per-island breakdown
# Spatial join to island boundaries
islands = gpd.read_file("data/boundaries/visayas_islands.geojson")
joined = gpd.sjoin(transmission, islands, how="left", predicate="within")
print(joined.groupby("island_name").size())
```

**Expected findings (based on known OSM coverage):**
- Cebu backbone (138 kV) → likely present
- Leyte-Samar backbone → partial coverage
- Submarine interconnections → may appear as `power=cable`
- Distribution (< 35 kV) → sparse to empty for most provinces

**Deliverable:** Coverage audit report. A province-level table showing: OSM coverage score (0–3: empty / partial / good) for transmission and distribution separately. This table drives Phase 1C.

---

## Phase 1B — Transmission Data Cleaning (Weeks 1–2)

### Goal: Clean OSM transmission data into a topologically valid, pandapower-ready network.

**Step 1B.1 — Voltage filtering and geometry repair**

```python
# Keep only transmission voltage levels
tx = gdf[gdf["voltage"].isin(["69000", "138000", "230000"])].copy()

# Repair geometry: explode multilinestrings, remove self-intersections
tx = tx.explode(index_parts=False)
tx["geometry"] = tx["geometry"].buffer(0)  # fixes self-intersections
```

**Step 1B.2 — Node snapping (critical)**

Raw OSM lines often have endpoints that *look* connected but are 5–50 meters apart. Without snapping, pandapower will treat them as disconnected buses.

```python
from shapely.ops import snap, unary_union

SNAP_TOLERANCE = 0.0005  # ~55 meters in decimal degrees

# Extract all line endpoints as candidate bus locations
endpoints = []
for geom in tx.geometry:
    endpoints.append(geom.coords[0])
    endpoints.append(geom.coords[-1])

# Snap endpoints within tolerance to each other
# (use a spatial index for performance)
```

**Step 1B.3 — Substation matching**

```python
substations = gdf[gdf["power"] == "substation"].copy()

# For each line endpoint, find nearest substation
# If within 500m, assign that substation as the bus
# If no substation nearby, create a synthetic tower bus
```

**Step 1B.4 — Province + island assignment**

```python
provinces = gpd.read_file("data/boundaries/psgc_provinces.geojson")
buses_gdf = gpd.GeoDataFrame(buses_df, geometry=gpd.points_from_xy(...))
buses_gdf = gpd.sjoin(buses_gdf, provinces, how="left", predicate="within")
```

**Step 1B.5 — Flag submarine cables**

```python
# OSM tags submarine cables as power=cable (not power=line)
lines_df["is_submarine"] = lines_df["power_tag"] == "cable"

# Apply submarine impedance values
SUBMARINE_R = 0.0754
SUBMARINE_X = 0.121
lines_df.loc[lines_df["is_submarine"], "r_ohm_per_km"] = SUBMARINE_R
lines_df.loc[lines_df["is_submarine"], "x_ohm_per_km"] = SUBMARINE_X
```

**Deliverable:** Clean `buses.csv` and `lines.csv` for Visayas transmission. All nodes snapped, all submarine cables flagged, all buses assigned to a province.

---

## Phase 1C — Synthetic Distribution Topology (Week 3)

### Goal: Generate plausible distribution grid topologies for provinces where OSM has no data.

This is the key addition from the review feedback. Without this, the distribution layer will be blank for most provinces.

**Step 1C.1 — OSM coverage decision per province**

Based on the audit from Phase 1A, classify each province:
- **OSM Good** → use OSM distribution data directly (clean same as transmission)
- **OSM Partial** → use OSM as skeleton, fill gaps synthetically
- **OSM Empty** → full synthetic generation

**Step 1C.2 — Synthetic topology generation**

For empty provinces, generate a radial distribution network using the substation as the root:

```python
import networkx as nx
from shapely.geometry import LineString, Point
import numpy as np

def generate_radial_distribution(substation_point, province_polygon,
                                  n_feeders=4, branches_per_feeder=6,
                                  voltage_kv=13.8):
    """
    Generate a synthetic radial distribution network.
    Uses a simple branching tree from the substation.
    """
    G = nx.Graph()
    buses = []
    lines = []

    # Place feeder endpoints randomly within province polygon
    # using rejection sampling
    def random_point_in_polygon(poly, n=1):
        points = []
        minx, miny, maxx, maxy = poly.bounds
        while len(points) < n:
            p = Point(np.random.uniform(minx, maxx),
                      np.random.uniform(miny, maxy))
            if poly.contains(p):
                points.append(p)
        return points

    # Build branching tree from substation
    root_id = "BUS_SYNTH_ROOT"
    G.add_node(root_id, pos=substation_point, voltage_kv=voltage_kv)

    for f in range(n_feeders):
        feeder_points = random_point_in_polygon(province_polygon, branches_per_feeder)
        prev_id = root_id
        for i, pt in enumerate(feeder_points):
            node_id = f"BUS_SYNTH_F{f}_N{i}"
            G.add_node(node_id, pos=pt, voltage_kv=voltage_kv)
            G.add_edge(prev_id, node_id)
            prev_id = node_id

    return G
```

**Step 1C.3 — Assign synthetic load parameters**

For each synthetic bus, assign loads based on:
- Province population density (PSA data)
- Land use type from OSM (residential, commercial, industrial)
- Peak demand estimate: 0.5–2.0 MW per feeder section

**Step 1C.4 — Mark all synthetic data clearly**

```python
buses_df["is_synthetic"] = True
buses_df["data_source"] = "synthetic"
lines_df["is_synthetic"] = True
lines_df["data_source"] = "synthetic"
```

The frontend will display synthetic elements with a dashed line style and a disclaimer badge, so clients understand the data status.

**Deliverable:** Distribution GeoJSON for all Visayas provinces. Real where OSM has data. Synthetic (clearly labeled) where it doesn't.

---

## Phase 2 — Topology Validation + Load Flow (Week 4)

### Goal: Build a valid pandapower network and run load flow without convergence crashes.

**Step 2.1 — Mandatory topology check (NEW — critical)**

This step was missing in v1. It must run before `pp.runpp()`.

```python
import pandapower as pp
import pandapower.topology as top

net = pp.create_empty_network(f_hz=60)

# ... build network from buses.csv and lines.csv ...

# MANDATORY: Check connectivity before running load flow
unsupplied = top.unsupplied_buses(net)
if len(unsupplied) > 0:
    print(f"WARNING: {len(unsupplied)} buses not connected to slack bus.")
    print(f"Isolated buses: {unsupplied}")
    # Option A: Remove isolated buses and continue
    # Option B: Raise error and fix the topology
    net = top.drop_unsupplied_buses(net)  # remove islands
    
# Also check for islands (disconnected subgraphs)
mg = top.create_nxgraph(net)
components = list(nx.connected_components(mg))
print(f"Connected components: {len(components)}")
# Should be 1 for a connected grid. Visayas may have 2-3 due to island topology.
```

**Note on Visayas island topology:** Leyte-Samar, Cebu, Negros, and Panay are interconnected via submarine cables. The network *should* show 1 connected component if all submarine cables are in the model. If submarine cables are missing from OSM, you'll see 4+ disconnected components. This is expected and not a bug — it means the submarine cable data needs manual addition.

**Step 2.2 — Build pandapower network**

```python
net = pp.create_empty_network(f_hz=60)

# Create buses
bus_index_map = {}
for _, row in buses_df.iterrows():
    idx = pp.create_bus(net, vn_kv=row.voltage_kv, name=row.bus_id,
                        geodata=(row.lat, row.lon))
    bus_index_map[row.bus_id] = idx

# Create slack bus (main interconnection point / equivalent source)
# For Visayas: use Leyte geothermal injection point or Cebu-Naga substation
slack_bus_idx = bus_index_map["BUS_CEBU_NAGA"]  # example
pp.create_ext_grid(net, bus=slack_bus_idx, vm_pu=1.0)

# Create lines
for _, row in lines_df.iterrows():
    pp.create_line_from_parameters(
        net,
        from_bus=bus_index_map[row.from_bus],
        to_bus=bus_index_map[row.to_bus],
        length_km=row.length_km,
        r_ohm_per_km=row.r_ohm_per_km,
        x_ohm_per_km=row.x_ohm_per_km,
        c_nf_per_km=0,  # conservative; update with real data
        max_i_ka=row.max_i_ka,
        name=row.line_id
    )

# Create loads
for _, row in buses_df[buses_df.type == "load"].iterrows():
    pp.create_load(net, bus=bus_index_map[row.bus_id],
                   p_mw=row.p_mw, q_mvar=row.q_mvar)
```

**Step 2.3 — Run load flow**

```python
try:
    pp.runpp(net, algorithm="nr", calculate_voltage_angles=True,
             enforce_q_lims=True, numba=True)
    print("Load flow converged.")
except pp.powerflow.LoadflowNotConverged:
    print("Load flow did not converge. Check topology and slack bus.")
    # Fallback: try with flat start or DC approximation
    pp.rundcpp(net)
```

**Step 2.4 — Export results**

```python
bus_results = net.res_bus.copy()
bus_results["bus_id"] = net.bus["name"].values
bus_results.to_csv("data/processed/load_flow_bus_results.csv", index=False)

line_results = net.res_line.copy()
line_results["line_id"] = net.line["name"].values
line_results.to_csv("data/processed/load_flow_line_results.csv", index=False)
```

**Step 2.5 — Synthetic load profiles (time-series)**

Generate three operating scenarios for the app:
- **Morning peak** (7–9 AM): 85% loading
- **Evening peak** (6–9 PM): 95% loading
- **Off-peak** (2–4 AM): 40% loading

Users can toggle between scenarios in the frontend.

**Deliverable:** Converged load flow results for all three scenarios. Topology validation report. Network connectivity confirmed (or isolated islands documented).

---

## Phase 3 — PostGIS Database Setup (Week 4, parallel)

### Goal: Set up PostGIS from Day 1 for spatial queries.

**Why PostGIS (not SQLite):** Province-based filtering of lines and polygons requires spatial intersection queries. SQLite cannot do this. PostGIS with `ST_Intersects` handles it in milliseconds.

**Step 3.1 — Schema**

```sql
-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Buses table
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

-- Lines table
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

-- Load flow results (per scenario)
CREATE TABLE load_flow_results (
    id SERIAL PRIMARY KEY,
    scenario TEXT,  -- 'morning_peak' | 'evening_peak' | 'off_peak'
    bus_id TEXT REFERENCES buses(bus_id),
    line_id TEXT REFERENCES lines(line_id),
    vm_pu FLOAT,
    va_degree FLOAT,
    loading_percent FLOAT,
    p_from_mw FLOAT,
    p_to_mw FLOAT
);

-- Spatial indexes (critical for query performance)
CREATE INDEX idx_buses_geom ON buses USING GIST(geom);
CREATE INDEX idx_lines_geom ON lines USING GIST(geom);
```

**Step 3.2 — Key spatial queries used by the API**

```sql
-- All buses in a province (province filter endpoint)
SELECT b.* FROM buses b
JOIN provinces p ON ST_Within(b.geom, p.geom)
WHERE p.province_name = 'Cebu';

-- All lines that pass through a province
SELECT l.* FROM lines l
JOIN provinces p ON ST_Intersects(l.geom, p.geom)
WHERE p.province_name = 'Leyte';

-- All elements within a bounding box (viewport query for map)
SELECT * FROM buses
WHERE ST_Within(geom, ST_MakeEnvelope($minlon, $minlat, $maxlon, $maxlat, 4326));
```

**Deliverable:** PostGIS database running in Docker, schema initialized, data loaded, spatial indexes verified.

---

## Phase 4 — Backend API (Weeks 5–6)

### Goal: FastAPI backend serving GeoJSON to the frontend with spatial filtering.

**Core Endpoints:**

```
GET  /api/grid/transmission              → all transmission buses + lines
GET  /api/grid/distribution/{province}   → distribution grid for a province
GET  /api/grid/island/{island_name}      → all grid elements for an island
GET  /api/loadflow/{scenario}            → load flow results (morning/evening/offpeak)
GET  /api/loadflow/{scenario}/{province} → province-filtered load flow
GET  /api/provinces                      → list of provinces with coverage status
GET  /api/scenarios                      → list of available load flow scenarios
POST /api/export/png                     → static PNG export
POST /api/export/pdf                     → PDF report export
```

**Province list endpoint — includes coverage status:**

```json
{
  "provinces": [
    { "name": "Cebu", "island": "Cebu", "osm_coverage": "good", "has_distribution": true },
    { "name": "Samar", "island": "Samar", "osm_coverage": "partial", "has_distribution": true },
    { "name": "Biliran", "island": "Leyte", "osm_coverage": "empty", "has_distribution": true,
      "data_source": "synthetic" }
  ]
}
```

**GeoJSON response — buses:**

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [124.5, 11.2] },
      "properties": {
        "bus_id": "BUS_001",
        "name": "Cebu South Substation",
        "voltage_kv": 138,
        "vm_pu": 0.98,
        "loading_percent": 72.4,
        "province": "Cebu",
        "island": "Cebu",
        "is_synthetic": false,
        "data_source": "osm",
        "scenario": "evening_peak"
      }
    }
  ]
}
```

**GeoJSON response — lines:**

```json
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [[124.5, 11.2], [124.8, 11.4]] },
  "properties": {
    "line_id": "LINE_042",
    "voltage_kv": 138,
    "loading_percent": 81.3,
    "is_submarine": true,
    "cable_type": "submarine_xlpe",
    "from_bus": "BUS_001",
    "to_bus": "BUS_002",
    "is_synthetic": false
  }
}
```

**Deliverable:** All endpoints running locally, documented via FastAPI `/docs`.

---

## Phase 5 — Frontend Map Application (Weeks 7–9)

### Goal: Interactive React + Leaflet app with full filtering and visual encoding.

**Rendering strategy:**
- **Transmission layer** → `react-leaflet` (Leaflet SVG rendering, < 500 elements, fast)
- **Distribution layer** → `react-leaflet` initially; upgrade to **Deck.gl** if province rendering exceeds 2,000 elements and causes lag

**Map Features:**

| Feature | Implementation | Notes |
|---|---|---|
| Base map | Leaflet + OSM tiles | Free, Philippine coverage |
| Transmission buses | Circle markers, colored by voltage | |
| Transmission lines | Polylines, colored by loading % | |
| Submarine cables | Dashed polylines, distinct style | `is_submarine: true` |
| Distribution buses | Smaller circle markers | |
| Distribution lines | Thin polylines | |
| Synthetic data badge | Dashed line style + ⚠️ tooltip | `is_synthetic: true` |
| Province boundaries | GeoJSON polygon overlay | Toggle on/off |
| Island filter | Dropdown: Cebu / Leyte-Samar / Negros / Panay / Bohol | |
| Province filter | Dropdown populated from `/api/provinces` | |
| Scenario selector | Toggle: Morning Peak / Evening Peak / Off-Peak | |
| Click to inspect | Sidebar shows bus/line details + data source | |
| Loading colormap | Green → Yellow → Red → Dark Red | |
| Legend | Fixed bottom-left panel | |
| Export | Button triggers backend export | |

**Color Encoding (unchanged from v1):**

Voltage levels:
- 230 kV → `#e63946`
- 138 kV → `#f4a261`
- 69 kV → `#2a9d8f`
- Distribution < 35 kV → `#457b9d`

Line loading:
- < 50% → `#2d6a4f`
- 50–80% → `#f4a261`
- > 80% → `#e63946`
- > 100% (overloaded) → `#9b2226`

**Synthetic data visual treatment:**
- Lines from synthetic data → dashed stroke (`dashArray: "6 4"`)
- Buses from synthetic data → hollow circle marker
- Tooltip shows: `⚠️ Synthetic data — not from actual grid measurements`

**Deliverable:** Fully functional frontend connected to backend. All filters working. Synthetic data visually distinct from OSM/real data.

---

## Phase 6 — Static Export Feature (Week 9)

### Goal: Styled PNG and PDF export matching the frontend visual encoding.

```python
import matplotlib.pyplot as plt
import geopandas as gpd
import contextily as ctx
from matplotlib.lines import Line2D

def export_grid_map(buses_gdf, lines_gdf, results_df,
                    province=None, scenario="evening_peak",
                    output_format="png"):

    fig, ax = plt.subplots(figsize=(16, 12), dpi=150)

    # Separate real vs synthetic for different styling
    real_lines = lines_gdf[~lines_gdf["is_synthetic"]]
    synth_lines = lines_gdf[lines_gdf["is_synthetic"]]
    submarine = lines_gdf[lines_gdf["is_submarine"]]

    # Draw lines by loading color
    real_lines.plot(ax=ax, column="loading_percent",
                    cmap="RdYlGn_r", vmin=0, vmax=100, linewidth=1.5)

    # Synthetic lines: dashed
    synth_lines.plot(ax=ax, column="loading_percent",
                     cmap="RdYlGn_r", vmin=0, vmax=100,
                     linewidth=1.0, linestyle="dashed", alpha=0.6)

    # Submarine cables: thick dashed blue
    submarine.plot(ax=ax, color="#1a6fb5", linewidth=2.5,
                   linestyle=(0, (8, 4)))

    # Draw buses by voltage
    buses_gdf.plot(ax=ax, column="voltage_kv",
                   categorical=True, cmap="Set1", markersize=40, zorder=5)

    # Add basemap
    ctx.add_basemap(ax, crs=buses_gdf.crs,
                    source=ctx.providers.OpenStreetMap.Mapnik, alpha=0.6)

    # Legend
    legend_elements = [
        Line2D([0], [0], color="#e63946", linewidth=2, label="230 kV"),
        Line2D([0], [0], color="#f4a261", linewidth=2, label="138 kV"),
        Line2D([0], [0], color="#2a9d8f", linewidth=2, label="69 kV"),
        Line2D([0], [0], color="#1a6fb5", linewidth=2,
               linestyle="dashed", label="Submarine Cable"),
        Line2D([0], [0], color="gray", linewidth=1.5,
               linestyle="dashed", alpha=0.6, label="Synthetic (estimated)"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=9)

    title = f"Visayas Power Grid — {scenario.replace('_', ' ').title()}"
    if province:
        title += f" — {province}"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.text(0.01, 0.01,
            "⚠️ Dashed lines indicate synthetic/estimated topology",
            transform=ax.transAxes, fontsize=7, color="gray")

    plt.tight_layout()
    plt.savefig(f"output.{output_format}", dpi=150, bbox_inches="tight")
    return f"output.{output_format}"
```

**Deliverable:** Export endpoint returning styled PNG/PDF with proper legend and synthetic data disclaimer.

---

## Phase 7 — Deployment (Weeks 10–11)

### Goal: Public URL, stable, low-cost hosting.

**Recommended setup (based on your existing Oracle Cloud account):**

```
Oracle Cloud Always Free VM (backend):
  - FastAPI (uvicorn) in Docker
  - PostgreSQL + PostGIS in Docker
  - Nginx reverse proxy

Vercel (frontend):
  - React static build
  - Points to Oracle Cloud backend URL
```

**docker-compose.yml:**

```yaml
services:
  db:
    image: postgis/postgis:15-3.3
    environment:
      POSTGRES_DB: gridviz
      POSTGRES_USER: julius
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports: ["5432:5432"]

  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql://julius:${DB_PASSWORD}@db:5432/gridviz
    ports: ["8000:8000"]
    depends_on: [db]
    volumes:
      - ./backend/data:/app/data

  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on: [backend]

volumes:
  postgres_data:
```

**Deliverable:** Live URL accessible to clients. HTTPS via Let's Encrypt (Certbot + Nginx).

---

## Phase 8 — Real Data Upgrade Path (Future, no timeline)

When real NGCP or DU data becomes available, the upgrade process is:

1. Format to match `buses.csv` / `lines.csv` schema
2. Set `is_synthetic = False`, `data_source = "real"`
3. Run topology validator (Phase 2 script)
4. Re-run load flow
5. Load into PostGIS (replace synthetic records for that province)
6. No frontend or API changes required

The `data_source` column in every table makes this a surgical replacement — real data overwrites synthetic data province by province, not all at once.

---

## Revised Development Milestones

| Week | Milestone | Risk |
|---|---|---|
| 1 | OSMnx extraction + coverage audit complete | Medium — OSM may have poor tagging |
| 2 | Transmission cleaning: buses snapped, submarine flagged | High — most time-consuming step |
| 3 | Synthetic distribution generator working for all provinces | Medium |
| 4 | Topology validated, pandapower load flow converged (3 scenarios) | High — convergence not guaranteed |
| 4 | PostGIS schema up, data loaded, spatial queries verified | Low |
| 5 | FastAPI backend running locally, all endpoints returning GeoJSON | Low |
| 6 | Backend tested, documented via Swagger, edge cases handled | Low |
| 7 | React frontend: map renders transmission layer correctly | Low |
| 8 | Distribution layer, filters, synthetic badges, scenario toggle | Medium |
| 9 | Export feature (PNG + PDF) with full legend | Low |
| 10 | Docker + Oracle Cloud deployment | Medium |
| 11 | Buffer week: bug fixes, performance, client review | — |

**Honest timeline: 10–11 weeks for a solo developer.**
The original 8-week estimate was optimistic. Data cleaning and topology validation alone will take 3 weeks.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| OSM transmission data is incomplete for some islands | High | High | Manual entry for missing major lines using known NGCP SLD |
| Load flow fails to converge | Medium | High | Run topology check first; use DC approximation as fallback |
| Distribution OSM is empty for most provinces | High | Medium | Synthetic generator (Phase 1C) covers this |
| Submarine cable parameters unavailable | Medium | Medium | Use XLPE defaults; flag as estimated |
| Oracle Cloud VM performance too slow for PostGIS | Low | Medium | Add pg indexes; cache GeoJSON responses in Redis |
| Real DU data never becomes available | High | Low | Synthetic data with clear disclaimer is acceptable for portfolio/demo |

---

## Tools & Libraries to Install

```bash
# Backend
pip install fastapi uvicorn pandapower osmnx geopandas shapely pandas \
            contextily matplotlib reportlab psycopg2-binary sqlalchemy \
            networkx asyncpg

# Frontend
npm create vite@latest frontend -- --template react
npm install leaflet react-leaflet tailwindcss axios

# Database
docker pull postgis/postgis:15-3.3

# Optional: Deck.gl for high-density distribution rendering
npm install @deck.gl/react @deck.gl/layers
```

---

## First Action: Run Tonight

```python
import osmnx as ox
import geopandas as gpd

tags = {"power": ["line", "cable", "substation", "tower"]}
visayas_bbox = (9.0, 123.0, 13.0, 126.5)

print("Extracting Visayas power infrastructure from OSM...")
gdf = ox.features_from_bbox(*visayas_bbox, tags=tags)

print(f"Total features: {len(gdf)}")
print(f"Columns: {gdf.columns.tolist()}")
print(f"Power types: {gdf['power'].value_counts()}")
print(f"Voltage tags: {gdf['voltage'].value_counts().head(20)}")

gdf.to_file("visayas_power_raw.geojson", driver="GeoJSON")
print("Saved to visayas_power_raw.geojson")
```

Run this. The output tells you exactly what you're working with and decides whether Phase 1C is a minor or major effort.
