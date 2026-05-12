#!/usr/bin/env python
"""Phase 1 pipeline orchestrator.

The Phase 1 notebooks form a dependency chain: each reads
`buses.csv`/`lines.csv`, modifies it, and writes back. Running them
out of order or partially leaves the on-disk state inconsistent.
Day 18 surfaced this the hard way (notebook 10's first attempt ran
against a clobbered `buses.csv` and silently regenerated half the
state from the wrong baseline).

This script enforces the full chain as a single transaction. Run it
to rebuild Phase 1 from raw OSM + boundaries:

    python scripts/run_phase1.py

To skip notebooks (e.g., while iterating on one step), edit the
`NOTEBOOKS` list below. The order matters and is encoded as a
comment on each entry.
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

# Notebook dependency order. Each entry: (filename, short description).
# Inserting a new step? Update both this list and any cross-notebook
# references in BUILD_JOURNAL.md / dependent notebooks.
NOTEBOOKS = [
    ('02_transmission_cleaning.ipynb', 'Phase 1B: OSM transmission'),
    ('03_synthetic_distribution.ipynb', 'Phase 1C: initial synthetic distribution'),
    ('04_name_reconciliation.ipynb',  'Step 1: match v1 names onto OSM buses'),
    ('06_v1_substation_import.ipynb', 'Step 2: import unmatched v1 substations'),
    ('07_v1_line_synthesis.ipynb',    'Step 3: Panay MST + non-Panay spurs'),
    ('08_kabankalan_handconnect.ipynb', 'Step 3b: hand-coded Kabankalan ↔ Mabinay'),
    ('11_substation_merge.ipynb',     'Substation merge + redundant-virtual cleanup'),
    ('13_voltage_inheritance.ipynb',  'Day 21: voltage inheritance for untagged OSM lines'),
    ('09_iloilo_redistribution.ipynb', 'Day 17: Iloilo distribution re-run'),
    ('10_redistribute_provinces.ipynb', 'Day 18: parametrised re-run for 8 provinces'),
    ('12_load_assignment.ipynb',      'Day 20: population-weighted load assignment'),
]


def state_snapshot(label: str) -> None:
    """Print a one-line summary of `buses.csv` + `lines.csv` state."""
    buses_path = PROC_DIR / 'buses.csv'
    lines_path = PROC_DIR / 'lines.csv'
    if not buses_path.exists():
        print(f'  [{label}] no buses.csv yet')
        return
    b = pd.read_csv(buses_path)
    l = pd.read_csv(lines_path)
    by_src = b['data_source'].value_counts().to_dict() if 'data_source' in b.columns else {}
    src_str = ', '.join(f'{k}={v}' for k, v in sorted(by_src.items()))
    print(f'  [{label}] {len(b):>5} buses ({src_str}) / {len(l):>5} lines')


# Acceptance thresholds for the final-state check. Day 18's silent regression
# (buses.csv reverted to 186 rows mid-pipeline) would have tripped MIN_BUSES.
# Update these floors deliberately when the pipeline structurally changes.
MIN_BUSES = 2900
MIN_LINES = 2900
LOAD_TOLERANCE = 0.05  # ±5% of the province_peak_targets.csv total


def verify_final_state() -> None:
    """Assert end-of-pipeline invariants. Fails loud on silent regressions."""
    buses = pd.read_csv(PROC_DIR / 'buses.csv')
    lines = pd.read_csv(PROC_DIR / 'lines.csv')
    targets = pd.read_csv(
        ROOT / 'backend' / 'data' / 'boundaries' / 'province_peak_targets.csv'
    )

    problems: list[str] = []
    if len(buses) < MIN_BUSES:
        problems.append(f'buses: {len(buses)} < floor {MIN_BUSES}')
    if len(lines) < MIN_LINES:
        problems.append(f'lines: {len(lines)} < floor {MIN_LINES}')

    target_total = float(targets['peak_mw'].sum())
    dist_mask = buses['bus_type'] == 'distribution'
    actual_total = float(buses.loc[dist_mask, 'p_mw'].sum())
    drift = abs(actual_total - target_total) / target_total
    if drift > LOAD_TOLERANCE:
        problems.append(
            f'load: dist total {actual_total:.0f} MW vs target '
            f'{target_total:.0f} MW (drift {drift:.1%} > {LOAD_TOLERANCE:.0%})'
        )

    if problems:
        print()
        print('  ✗ final-state verification FAILED:')
        for p in problems:
            print(f'      - {p}')
        sys.exit(3)
    print(
        f'  ✓ verified: {len(buses)} buses, {len(lines)} lines, '
        f'dist load {actual_total:.0f} MW vs target {target_total:.0f} MW '
        f'(drift {drift:.2%})'
    )


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
    parser.add_argument(
        '--from', dest='from_nb', default=None,
        help='Skip notebooks before this filename (e.g. --from 11_substation_merge.ipynb)',
    )
    parser.add_argument(
        '--to', dest='to_nb', default=None,
        help='Stop after this notebook',
    )
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    print(f'Phase 1 orchestrator — {len(NOTEBOOKS)} notebooks queued')
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
    # Only verify when the full chain ran. Partial runs (--from / --to)
    # legitimately leave intermediate state that does not meet the floor.
    if args.from_nb is None and args.to_nb is None:
        verify_final_state()


if __name__ == '__main__':
    main()
