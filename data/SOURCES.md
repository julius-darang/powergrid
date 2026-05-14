# Data Sources & Provenance — Powergrid

> Provenance for the curated topology in `data/buses.csv` and `data/lines.csv`.
> Follow the source-first rule: unverified values remain explicitly tagged as
> estimates rather than being presented as observed facts.

## Provenance tags

- `sourced` — confirmed against a primary or public reference.
- `pypsa-ph` — inherited from the PyPSA-PH reference model.
- `estimate` — engineering or geographic estimate; not published by NGCP.

## Source registry

| ID | Source | Use |
|---|---|---|
| S1 | NGCP Transmission Development Plan 2025–2050 report (March 11, 2025) | Samar/Leyte 69 kV substations, corridors, voltage levels, and planned topology |
| S2 | OpenStreetMap / OpenInfraMap power features | Substation coordinates, facility identity, and selected topology checks |
| S3 | Existing Powergrid/PyPSA-PH v1 curated dataset | Existing buses, lines, model schema, and inherited network values |

The report used for the Samar/Leyte topology was consulted as a local PDF during
feature preparation. Keep the original source artifact outside Git unless a
redistributable copy and its licensing are explicitly confirmed.

## Samar/Leyte topology addition

The Samar/Leyte feature commit adds 33 curated buses and 36 lines to the v1
source tables. Its provenance is divided by field rather than treating every
value as equally certain:

### `data/buses.csv`

- `name`, `v_nom`, island assignment, and the corridor/site identity are
  `sourced` from S1 where the NGCP plan identifies the site or voltage level.
- Coordinates carrying an OSM way/node/relation reference in `description` are
  `sourced` from S2.
- Municipality-center or approximate coordinates explicitly marked in
  `description` are `estimate` and require later field/OSM facility verification.
- Existing values carried forward from the base model are `pypsa-ph` unless the
  row description records a newer source or correction.
- Co-located voltage-split buses (for example `04PARANAS` / `04PARANAS69`) are a
  deliberate modeling representation of separate voltage yards, not evidence
  that the yards occupy different geographic coordinates.

### `data/lines.csv`

- Endpoint pairs and nominal voltage are `sourced` from S1 when they follow the
  NGCP diagrammed corridor; planned or inferred segments remain `estimate` until
  independently confirmed.
- `length_km` is derived by the patch script from the endpoint coordinates using
  the haversine formula; it is not a published circuit length.
- `r`, `x`, and `max_i` values are `estimate` model parameters inherited from the
  project's synthetic line conventions. NGCP does not publish the per-line
  impedance values used by this model.
- Submarine status and cable type are `sourced` only where the crossing is
  explicitly identified; the Sambulawan–Biliran crossing is modeled as a
  submarine XLPE cable based on the geographic crossing and remains a topology
  assumption pending a primary confirmation.

## Reproducibility

`backend/data/processed/` is derived output. The Samar/Leyte patch is reproducible
from the curated source tables with:

```bash
python scripts/patch_backend_samar_leyte.py
```

The complete Phase 1/2 rebuild remains the authoritative validation path:

```bash
python scripts/run_phase1.py
python scripts/run_phase2.py
```

Do not run the numbered notebooks individually; the project pipeline enforces
ordering and state checks.

## Open verification work

- Replace municipality-center estimates with facility coordinates from OSM,
  OpenInfraMap, NGCP documentation, or field verification.
- Confirm all planned 69 kV corridors against the latest NGCP plan.
- Replace synthetic impedance/current parameters with documented engineering
  values when primary data becomes available.
