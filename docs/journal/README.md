# Build journal — index

A working developer log for the Philippine Power Grid Visualization
project. One file per phase. Day-by-day narrative lives here;
each phase's handoff document lives in [`../closeouts/`](../closeouts).

## Layout

```
docs/
  journal/                    ← you are here (day-by-day narrative)
    README.md
    phase-1-data.md           ← Days 1–20, Phase 1 data foundation
    phase-2-loadflow.md       ← Phase 2 topology + load flow
    phase-3-api.md            (stub)
    phase-4-frontend.md       (stub)
    phase-5-polish.md         (stub)
  closeouts/                  ← phase handoff documents (one screen each)
    phase-1-closeout.md
```

## Phase status

| Phase | Journal                                        | Closeout                                            | Status      |
| ----- | ---------------------------------------------- | --------------------------------------------------- | ----------- |
| 1     | [phase-1-data.md](phase-1-data.md)             | [phase-1-closeout.md](../closeouts/phase-1-closeout.md) | **done** (Day 27 recal) |
| 2     | [phase-2-loadflow.md](phase-2-loadflow.md)     | [phase-2-closeout.md](../closeouts/phase-2-closeout.md) | **done**    |
| 3     | [phase-3-api.md](phase-3-api.md)               | —                                                   | scaffolded  |
| 4     | Frontend                                       | —                                                   | not started |
| 5     | Polish                                         | —                                                   | not started |

## Current state in one line

After the Day 27 Phase 1 feeder-impedance recalibration
(`DIST_R/X` 0.40 → 0.10/0.15), NR converges for all three
scenarios with no DC fallback (off-peak `vm_pu_min` 0.903,
evening-peak 0.743). Phase 3 FastAPI scaffold is live and
verified — nine endpoints serving GeoJSON + load-flow JSON
from PostGIS, two pytest sanity tests passing.
`scripts/run_phase1.py` (~39 s) and `scripts/run_phase2.py`
(~23 s) rebuild from raw OSM end-to-end. See
[phase-2-loadflow.md](phase-2-loadflow.md) Day 27 for the
recalibration story and [phase-3-api.md](phase-3-api.md) for
the API scaffold.

## Conventions

- **One file per phase**, opened on day 1 of that phase. Day
  sections (`## Day N — short description`) inside.
- **Closeout at the end of each phase.** One screen, one paragraph
  of "what shipped," then open threads grouped by category. This
  is what the next phase reads — the journal is archival.
- **Open threads belong to the closeout, not the journal tail.**
  Cross-phase references are by file path: "see
  `docs/journal/phase-1-data.md` Day 17," not "see Day 17."
- **Patterns worth keeping** sections at the end of a phase
  journal are fine and useful; they describe habits, not state.
