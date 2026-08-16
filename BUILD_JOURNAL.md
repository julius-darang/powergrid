# Build Journal

The journal has been split per phase. Start here:

- **Index + phase status:** [`docs/journal/README.md`](docs/journal/README.md)
- **Phase 1 (data foundation, done):** journal
  [`docs/journal/phase-1-data.md`](docs/journal/phase-1-data.md) ·
  closeout [`docs/closeouts/phase-1-closeout.md`](docs/closeouts/phase-1-closeout.md)
- **Phase 2 (load flow, done):**
  [`docs/journal/phase-2-loadflow.md`](docs/journal/phase-2-loadflow.md)
- **Phase 3 (FastAPI + PostGIS, done):**
  [`docs/journal/phase-3-api.md`](docs/journal/phase-3-api.md)
- **Phase 4 (frontend, underway):**
  [`frontend/README.md`](frontend/README.md)

## Current state

Phase 1 produced `backend/data/processed/buses.csv` (2 960 rows)
and `lines.csv` (2 967 rows). Visayas total peak load = 2 282 MW
(1.04× the published ~2 200 MW). Full pipeline runs end-to-end in
~34 s via:

```
python scripts/run_phase1.py
```

For the current state, open threads, and the Phase 4 frontend handoff,
read [`docs/journal/README.md`](docs/journal/README.md) and
[`frontend/README.md`](frontend/README.md). Historical Phase 1 context remains in
[`docs/closeouts/phase-1-closeout.md`](docs/closeouts/phase-1-closeout.md).
