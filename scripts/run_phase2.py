#!/usr/bin/env python
"""Phase 2 pipeline orchestrator.

Phase 2 consumes Phase 1's CSV deliverables and produces:
- `backend/data/processed/topology_audit.csv` — connected-components audit
- `backend/data/processed/bus_component_map.csv` — bus → component_id
- `backend/data/processed/pp_network.json` — assembled pandapower network
- `backend/data/processed/bus_index_map.csv` — bus_id ↔ pp_index map
- `backend/data/processed/load_flow_results.csv` — long-format results
- `backend/data/processed/load_flow_summary.csv` — per-scenario summary

Run end-to-end:

    python scripts/run_phase2.py

The PostGIS loader (2A.1) is intentionally not part of this chain —
it requires a container runtime that wasn't available when Phase 2
ran. Add it as a separate step once Docker / OrbStack is installed.
"""
from __future__ import annotations
import argparse
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NB_DIR = ROOT / 'notebooks'
PROC_DIR = ROOT / 'backend' / 'data' / 'processed'
JUPYTER = ROOT / '.venv' / 'bin' / 'jupyter'

NOTEBOOKS = [
    ('12_topology_audit.ipynb',    '2A.3: NetworkX connected components'),
    ('13_pandapower_build.ipynb',  '2B:   pandapower network + transformers + gens + slack'),
    ('14_loadflow.ipynb',          '2C:   three-scenario load flow (NR + DC fallback)'),
    ('15_loadflow_audit.ipynb',    '2D:   per-province voltage and loading audit'),
]

# Acceptance floors. Each scenario contributes (in_service_buses + in_service_lines)
# = 1230 + 1294 = 2524 rows. Three scenarios → ~7572 rows.
MIN_AUDIT_COMPONENTS = 1            # at least one component or something is very wrong
MIN_RESULT_ROWS = 7000              # leaves headroom if Phase 1 row counts shift
EXPECTED_SCENARIOS = {'off_peak', 'morning_peak', 'evening_peak'}


def state_snapshot(label: str) -> None:
    audit_p = PROC_DIR / 'topology_audit.csv'
    results_p = PROC_DIR / 'load_flow_results.csv'
    parts = []
    if audit_p.exists():
        a = pd.read_csv(audit_p)
        parts.append(f'audit {len(a):>3} comps')
    if results_p.exists():
        r = pd.read_csv(results_p)
        parts.append(f'results {len(r):>5} rows')
    summary = ', '.join(parts) if parts else 'no outputs yet'
    print(f'  [{label}] {summary}')


def verify_final_state() -> None:
    problems: list[str] = []

    audit_p = PROC_DIR / 'topology_audit.csv'
    if not audit_p.exists():
        problems.append('topology_audit.csv missing')
    else:
        a = pd.read_csv(audit_p)
        if len(a) < MIN_AUDIT_COMPONENTS:
            problems.append(f'audit: {len(a)} components < floor {MIN_AUDIT_COMPONENTS}')

    results_p = PROC_DIR / 'load_flow_results.csv'
    if not results_p.exists():
        problems.append('load_flow_results.csv missing')
    else:
        r = pd.read_csv(results_p)
        if len(r) < MIN_RESULT_ROWS:
            problems.append(f'results: {len(r)} rows < floor {MIN_RESULT_ROWS}')
        seen = set(r['scenario'].unique())
        if seen != EXPECTED_SCENARIOS:
            problems.append(f'scenarios: got {sorted(seen)}, want {sorted(EXPECTED_SCENARIOS)}')
        nan_vm = int(r.loc[(r['bus_id'].notna()) & (r['convergence_mode'] == 'nr'),
                           'vm_pu'].isna().sum())
        if nan_vm > 0:
            problems.append(f'{nan_vm} NR bus rows have NaN vm_pu (should be numeric)')

    net_p = PROC_DIR / 'pp_network.json'
    if not net_p.exists():
        problems.append('pp_network.json missing')

    if problems:
        print()
        print('  ✗ Phase 2 verification FAILED:')
        for p in problems:
            print(f'      - {p}')
        sys.exit(3)

    print(f'  ✓ verified: {len(a)} components, {len(r)} result rows, '
          f'{len(seen)} scenarios')


def run_notebook(nb_path: Path, verbose: bool = False) -> float:
    cmd = [
        str(JUPYTER), 'nbconvert',
        '--to', 'notebook',
        '--execute',
        str(nb_path),
        '--output', nb_path.name,
    ]
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    dt = time.time() - t0
    if result.returncode != 0:
        print(f'  ✗ failed after {dt:.1f}s')
        print('--- stderr (last 2 KB) ---')
        print(result.stderr[-2000:])
        sys.exit(1)
    if verbose:
        print(result.stderr.strip())
    return dt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from', dest='from_nb', default=None,
                        help='Skip notebooks before this filename')
    parser.add_argument('--to', dest='to_nb', default=None,
                        help='Stop after this notebook')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    print(f'Phase 2 orchestrator — {len(NOTEBOOKS)} notebooks queued')
    print()
    state_snapshot('start')

    started = args.from_nb is None
    total_t0 = time.time()
    for nb, desc in NOTEBOOKS:
        if not started:
            if nb == args.from_nb:
                started = True
            else:
                print(f'  ⊝ skip   {nb}  ({desc})')
                continue
        path = NB_DIR / nb
        if not path.exists():
            print(f'  ✗ missing {nb}')
            sys.exit(2)
        print(f'  ▶ run    {nb}  ({desc})')
        dt = run_notebook(path, verbose=args.verbose)
        state_snapshot(f'{dt:>4.0f}s')
        if args.to_nb and nb == args.to_nb:
            print(f'\nStopped after {nb} as requested.')
            break

    print()
    print(f'✓ pipeline complete in {time.time() - total_t0:.0f}s')
    state_snapshot('final')
    if args.from_nb is None and args.to_nb is None:
        verify_final_state()


if __name__ == '__main__':
    main()
