# Philippine Power Grid Visualization

A public web app that visualises the Philippine power grid in two
layers — the Visayas transmission backbone (69 / 138 / 230 kV) and
per-province distribution — with a `pandapower` load-flow model
running underneath. Real NGCP topology is not public, so the build
combines OSM, a hand-curated v1 dataset of 53 NGCP substations, and
synthetic infill where neither source is sufficient. Synthetic rows
are flagged so they can be swapped out when real data arrives.

The forward-looking plan is [`power-grid-viz-plan-v2.md`](power-grid-viz-plan-v2.md).
What has actually shipped is in [`docs/journal/README.md`](docs/journal/README.md);
the Phase 1 handoff is at [`docs/closeouts/phase-1-closeout.md`](docs/closeouts/phase-1-closeout.md).

## Status

**Phase 1 (data foundation) — done.**
`backend/data/processed/buses.csv` (2 960 rows) and `lines.csv`
(2 967 rows). Visayas total peak load = 2 282 MW, within 4 % of the
published ~2 200 MW. Full pipeline runs end-to-end in ~34 s.

Phase 2 (topology validation + load flow) — not started.

## Prerequisites

- Python 3.11+
- Docker (for the PostGIS container)
- `osmnx` system deps (GDAL etc.) — on macOS, `brew install gdal` if
  the pip wheel install fails

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostGIS (schema is live but empty after Phase 1)
docker compose up -d db
```

## Rebuilding Phase 1

The pipeline is enforced as a single transaction by an orchestrator
script — running notebooks individually risks the kind of silent
state drift that Day 18 surfaced. To rebuild from raw OSM + boundary
data:

```bash
python scripts/run_phase1.py
```

This runs notebooks 02 → 03 → 04 → 06 → 07 → 08 → 11 → 09 → 10 → 12
in dependency order, prints a state snapshot after each step, and
asserts final-state invariants (row-count floors + per-province load
total within ±5 % of `province_peak_targets.csv`).

Setup notebooks `00`, `01`, `05` are *not* part of the pipeline —
they produce upstream inputs (boundary GeoJSON, raw OSM extract,
coverage audit) and were each run once.

To iterate on a single notebook without re-running the full chain:

```bash
python scripts/run_phase1.py --from 10_redistribute_provinces.ipynb --to 12_load_assignment.ipynb
```

(Skipping the verification at the end is deliberate when `--from` /
`--to` are passed — partial runs legitimately leave intermediate
state that does not meet the final-state floor.)

## Where things live

```
backend/
  data/
    raw/          OSM extract (visayas_power_raw.geojson)
    boundaries/   GADM PHL geopackage, PSGC reference, dissolved islands,
                  per-province peak targets
    processed/    The Phase 1 deliverable: buses.csv, lines.csv,
                  plus per-step summary CSVs
  db/init.sql     PostGIS schema (live but empty)
  services/       Empty — Phase 2 promotion target
  routers/        Empty
  models/         Empty

notebooks/        01–12 (00 = boundary prep, 01 = OSM extract,
                  05 = coverage audit; 02, 03, 04, 06, 07, 08, 11,
                  09, 10, 12 are the orchestrated chain)
scripts/
  run_phase1.py   The orchestrator — only entry point for rebuilding

docs/
  journal/        Per-phase developer journal
  closeouts/      Per-phase handoff documents (one screen each)

data/             Upstream v1 dataset of 53 NGCP substations
                  (buses.csv, lines.csv, admin_regions.csv)
```

## Acknowledgements / data sources

- OpenStreetMap — transmission lines and substations via `osmnx`
- GADM 4.1 (Philippines) — provincial boundaries
- PSA PSGC — official province codes
- A hand-curated v1 dataset of 53 NGCP substations from the OP

See [`docs/journal/phase-1-data.md`](docs/journal/phase-1-data.md)
for the full development narrative.
