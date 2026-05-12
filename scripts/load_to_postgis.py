#!/usr/bin/env python
"""Phase 2A.1 — Load Phase 1 / Phase 2 deliverables into PostGIS.

Reads:
- backend/data/processed/buses.csv             → buses
- backend/data/processed/lines.csv             → lines (geom = LINESTRING from
                                                 from_bus → to_bus coordinates)
- backend/data/processed/load_flow_results.csv → load_flow_results

Idempotent: TRUNCATE … CASCADE before insert; safe to re-run.

Also runs Phase 2A.2 GIST-query benchmarks at the end. Each query must
return under 100 ms to satisfy the rubric set in
`power-grid-viz-plan-v2.md` §3.2.

Prereqs: `docker compose up -d db` (PostGIS on localhost:5432) and the
init.sql schema applied at first container start.
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / 'backend' / 'data' / 'processed'

DSN = 'postgresql://powergrid:powergrid@localhost:5432/powergrid'

QUERY_TIMEOUT_MS = 100  # Phase 3 rubric

# Benchmark queries cover the three Phase 3 access patterns:
# 1. Viewport — what the map draws on every pan/zoom.
# 2. Province filter — sidebar "show only Cebu" / API /api/grid/province/{name}.
# 3. KNN — click-to-inspect "what's near this point" on the map.
BENCH_QUERIES = [
    ('viewport_buses_cebu',
     "SELECT bus_id, name, voltage_kv FROM buses "
     "WHERE ST_Within(geom, ST_MakeEnvelope(123.4, 9.4, 124.5, 11.4, 4326));"),
    ('viewport_lines_cebu',
     "SELECT line_id, voltage_kv FROM lines "
     "WHERE ST_Intersects(geom, ST_MakeEnvelope(123.4, 9.4, 124.5, 11.4, 4326));"),
    ('viewport_buses_full_visayas',
     "SELECT bus_id FROM buses "
     "WHERE ST_Within(geom, ST_MakeEnvelope(122.5, 9.0, 126.5, 13.0, 4326));"),
    ('province_filter_buses',
     "SELECT bus_id, name, voltage_kv FROM buses WHERE province = 'Cebu';"),
    ('province_filter_lines_via_buses',
     "SELECT DISTINCT l.line_id, l.voltage_kv FROM lines l "
     "JOIN buses b ON l.from_bus = b.bus_id OR l.to_bus = b.bus_id "
     "WHERE b.province = 'Cebu';"),
    ('knn_nearest_10_buses',
     "SELECT bus_id, name, ST_Distance(geom, ST_SetSRID(ST_MakePoint(124.0, 11.0), 4326)) AS d "
     "FROM buses ORDER BY geom <-> ST_SetSRID(ST_MakePoint(124.0, 11.0), 4326) LIMIT 10;"),
]


def load(cur, verbose: bool) -> dict[str, int]:
    """Ensure schema is current and load all three CSVs. Returns row counts."""
    cur.execute(
        "ALTER TABLE load_flow_results "
        "ADD COLUMN IF NOT EXISTS convergence_mode TEXT;"
    )
    # CASCADE so FK rows in load_flow_results vanish with their referents.
    cur.execute("TRUNCATE buses, lines, load_flow_results RESTART IDENTITY CASCADE;")

    buses = pd.read_csv(PROC / 'buses.csv')
    lines = pd.read_csv(PROC / 'lines.csv')
    results = pd.read_csv(PROC / 'load_flow_results.csv')

    # --- buses ---
    t0 = time.time()
    bus_rows = [
        (
            r.bus_id, r.name,
            float(r.lon), float(r.lat),
            float(r.voltage_kv), r.province, r.island, r.bus_type,
            None if pd.isna(r.p_mw) else float(r.p_mw),
            None if pd.isna(r.q_mvar) else float(r.q_mvar),
            bool(r.is_synthetic), r.data_source,
        )
        for r in buses.itertuples(index=False)
    ]
    execute_values(
        cur,
        "INSERT INTO buses (bus_id, name, geom, voltage_kv, province, island, "
        "bus_type, p_mw, q_mvar, is_synthetic, data_source) VALUES %s",
        bus_rows,
        template="(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), "
                 "%s, %s, %s, %s, %s, %s, %s, %s)",
    )
    if verbose:
        print(f'  buses: {len(bus_rows)} rows in {time.time()-t0:.2f}s')

    # --- lines ---
    # Geom = LINESTRING from from_bus → to_bus. Build WKT inline.
    t0 = time.time()
    bus_coord = buses.set_index('bus_id')[['lon', 'lat']]
    line_rows = []
    for r in lines.itertuples(index=False):
        f = bus_coord.loc[r.from_bus]
        t = bus_coord.loc[r.to_bus]
        wkt = f'LINESTRING({f.lon} {f.lat}, {t.lon} {t.lat})'
        line_rows.append((
            r.line_id, r.from_bus, r.to_bus, wkt,
            float(r.voltage_kv), float(r.length_km),
            float(r.r_ohm_per_km), float(r.x_ohm_per_km),
            float(r.max_i_ka),
            bool(r.is_submarine), r.cable_type,
            bool(r.is_synthetic), r.data_source,
        ))
    execute_values(
        cur,
        "INSERT INTO lines (line_id, from_bus, to_bus, geom, voltage_kv, length_km, "
        "r_ohm_per_km, x_ohm_per_km, max_i_ka, is_submarine, cable_type, "
        "is_synthetic, data_source) VALUES %s",
        line_rows,
        template="(%s, %s, %s, ST_GeomFromText(%s, 4326), "
                 "%s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )
    if verbose:
        print(f'  lines: {len(line_rows)} rows in {time.time()-t0:.2f}s')

    # --- load_flow_results ---
    t0 = time.time()
    result_rows = [
        (
            r.scenario,
            None if pd.isna(r.bus_id) else r.bus_id,
            None if pd.isna(r.line_id) else r.line_id,
            None if pd.isna(r.vm_pu) else float(r.vm_pu),
            None if pd.isna(r.va_degree) else float(r.va_degree),
            None if pd.isna(r.loading_percent) else float(r.loading_percent),
            None if pd.isna(r.p_from_mw) else float(r.p_from_mw),
            None if pd.isna(r.p_to_mw) else float(r.p_to_mw),
            r.convergence_mode,
        )
        for r in results.itertuples(index=False)
    ]
    execute_values(
        cur,
        "INSERT INTO load_flow_results (scenario, bus_id, line_id, vm_pu, "
        "va_degree, loading_percent, p_from_mw, p_to_mw, convergence_mode) "
        "VALUES %s",
        result_rows,
    )
    if verbose:
        print(f'  results: {len(result_rows)} rows in {time.time()-t0:.2f}s')

    cur.execute("ANALYZE buses; ANALYZE lines; ANALYZE load_flow_results;")
    return {'buses': len(buses), 'lines': len(lines), 'load_flow_results': len(results)}


def benchmark(cur, runs: int = 5) -> list[dict]:
    """Run each benchmark query `runs` times; return per-query median ms."""
    rows = []
    for name, sql in BENCH_QUERIES:
        # Warm-up to populate caches — measurement starts after.
        cur.execute(sql)
        _ = cur.fetchall()

        times_ms = []
        for _ in range(runs):
            t0 = time.perf_counter()
            cur.execute(sql)
            out = cur.fetchall()
            times_ms.append((time.perf_counter() - t0) * 1000)
        rows.append({
            'query': name,
            'rows_returned': len(out),
            'min_ms': round(min(times_ms), 2),
            'median_ms': round(sorted(times_ms)[len(times_ms) // 2], 2),
            'max_ms': round(max(times_ms), 2),
            'under_100ms': max(times_ms) < QUERY_TIMEOUT_MS,
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true',
                        help='Skip load; just verify counts and run benchmarks')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    try:
        conn = psycopg2.connect(DSN)
    except psycopg2.OperationalError as e:
        print(f'✗ cannot connect to {DSN}: {e}')
        print('  Start the DB with:  docker compose up -d db')
        sys.exit(2)

    with conn:
        with conn.cursor() as cur:
            if not args.verify_only:
                print('Loading CSVs → PostGIS …')
                counts = load(cur, verbose=args.verbose)
                # Verify what we wrote.
                problems = []
                for tbl, expected in counts.items():
                    cur.execute(f'SELECT COUNT(*) FROM {tbl}')
                    got = cur.fetchone()[0]
                    if got != expected:
                        problems.append(f'{tbl}: {got} rows, expected {expected}')
                    print(f'  {tbl:<20} {got:>5} rows')
                if problems:
                    print('\n✗ load verification failed:')
                    for p in problems:
                        print(f'    - {p}')
                    sys.exit(3)

            print('\nGIST query benchmarks (Phase 3 rubric: < 100 ms each)')
            results = benchmark(cur, runs=5)
            print()
            print(f'{"query":<35} {"rows":>5}  {"min_ms":>7}  {"med_ms":>7}  {"max_ms":>7}  ok?')
            for r in results:
                ok = '✓' if r['under_100ms'] else '✗'
                print(f'{r["query"]:<35} {r["rows_returned"]:>5}  '
                      f'{r["min_ms"]:>7.2f}  {r["median_ms"]:>7.2f}  '
                      f'{r["max_ms"]:>7.2f}  {ok}')
            failed = [r for r in results if not r['under_100ms']]
            if failed:
                print(f'\n✗ {len(failed)} queries exceeded {QUERY_TIMEOUT_MS} ms — see above')
                sys.exit(4)
            print(f'\n✓ all {len(results)} queries under {QUERY_TIMEOUT_MS} ms')


if __name__ == '__main__':
    main()
