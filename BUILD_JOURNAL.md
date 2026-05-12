# Build Journal

The journal has been split per phase. Start here:

- **Index + phase status:** [`docs/journal/README.md`](docs/journal/README.md)
- **Phase 1 (data foundation, done):** journal
  [`docs/journal/phase-1-data.md`](docs/journal/phase-1-data.md) ·
  closeout [`docs/closeouts/phase-1-closeout.md`](docs/closeouts/phase-1-closeout.md)
- **Phase 2 (load flow, not started):**
  [`docs/journal/phase-2-loadflow.md`](docs/journal/phase-2-loadflow.md)

## Current state

Phase 1 produced `backend/data/processed/buses.csv` (2 960 rows)
and `lines.csv` (2 967 rows). Visayas total peak load = 2 282 MW
(1.04× the published ~2 200 MW). Full pipeline runs end-to-end in
~34 s via:

```
python scripts/run_phase1.py
```

For what's done, what's unresolved, and what Phase 2 needs to know,
read [`docs/closeouts/phase-1-closeout.md`](docs/closeouts/phase-1-closeout.md).
