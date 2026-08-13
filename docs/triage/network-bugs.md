# Network bug triage

Visible anomalies surfaced by the Phase 4 map. Each entry: what was seen,
where to look in the data, what was done.

## Conventions

- **ID**: T-### in order of discovery.
- **Location**: province / island and approximate coords if possible.
- **Source**: which CSV row(s) own the bug — `buses.csv:<bus_id>`,
  `lines.csv:<line_id>`, `synth_v1_lines.csv:<line_id>`.
- **Status**: `open`, `fixing`, `fixed (<commit>)`, `deferred (<reason>)`.

## Findings
