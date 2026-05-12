# Phase 2 — Topology validation + load flow

> Day-by-day narrative for Phase 2. Starts from the Phase 1
> handoff in [`../closeouts/phase-1-closeout.md`](../closeouts/phase-1-closeout.md).
> Closeout document lives at `../closeouts/phase-2-closeout.md`
> (to be written at the end of Phase 2).

## Inputs from Phase 1

- `backend/data/processed/buses.csv` (2 960 rows)
- `backend/data/processed/lines.csv` (2 967 rows)
- `backend/db/init.sql` — PostGIS schema, live but empty

## Goals

Per `power-grid-viz-plan-v2.md` Phase 2:

1. **Topology validation gate.** NetworkX connected-components
   check on the cleaned graph. Document remaining gaps from the
   Phase 1 closeout (Samar, Antique, Biliran/Siquijor, HVDC
   north end).
2. **Load flow.** pandapower Newton-Raphson on the assembled
   network. Add external-grid bus at Ormoc HVDC south to provide
   an import path.
3. **Voltage / loading audit.** Surface the under-bussed sparse
   provinces (Capiz, Antique, Aklan) called out in the Phase 1
   closeout.

## Days

<!-- Day sections go here as work lands. -->
