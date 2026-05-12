"""Standalone validation for the voltage-inheritance pass.

Reads the raw OSM extract + current processed buses, finds untagged
transmission-shaped lines, and reports what would be recovered IF
both endpoints snap to known-voltage transmission buses within
MAX_SNAP_KM. No file writes — just stdout.

Run from project root:
    .venv/bin/python scripts/_scratch_voltage_inheritance.py
"""
from __future__ import annotations
import re
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'backend' / 'data' / 'raw' / 'visayas_power_raw.geojson'
PROC = ROOT / 'backend' / 'data' / 'processed'

MAX_SNAP_KM = 1.5            # max endpoint → bus distance
MIN_LINE_KM = 0.3            # filter trivial untagged geometry
TRANSMISSION_MIN_KV = 33.0   # subtransmission and up


def parse_voltage_kv(v) -> list[int]:
    """Same parser as notebook 05 — returns a list of plausible kV values."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    out = []
    for part in re.split(r'[;,/]', str(v)):
        m = re.search(r'\d+', part)
        if not m:
            continue
        n = int(m.group())
        kv = n / 1000 if n >= 1000 else n
        if 0.4 <= kv <= 1000:
            out.append(int(round(kv)))
    return out


def main() -> None:
    print(f'Reading {RAW.name}...')
    osm = gpd.read_file(RAW)
    print(f'  {len(osm)} raw OSM features')

    # Candidate set: lines/cables, line geometry, unparseable voltage
    lines = osm[osm['power'].isin(['line', 'cable'])].copy()
    lines = lines[lines.geometry.geom_type.isin(['LineString', 'MultiLineString'])]
    lines['vlist'] = lines['voltage'].apply(parse_voltage_kv)
    untagged = lines[lines['vlist'].apply(len) == 0].copy()
    print(f'  {len(lines)} lines/cables total')
    print(f'  {len(untagged)} have unparseable voltage tags (candidate set)')

    # Reproject to UTM 51N for metric distance
    untagged_m = untagged.to_crs(32651)
    untagged_m['length_km'] = untagged_m.geometry.length / 1000
    print(
        f'  → length distribution (km): '
        f'min {untagged_m["length_km"].min():.2f}, '
        f'median {untagged_m["length_km"].median():.2f}, '
        f'max {untagged_m["length_km"].max():.2f}'
    )

    # Drop trivially short candidates (jumpers / artifacts)
    untagged_m = untagged_m[untagged_m['length_km'] >= MIN_LINE_KM].copy()
    print(f'  {len(untagged_m)} candidates after MIN_LINE_KM={MIN_LINE_KM} filter')

    # Bus universe: tagged transmission buses
    buses = pd.read_csv(PROC / 'buses.csv')
    tx = buses[(buses['voltage_kv'] >= TRANSMISSION_MIN_KV)
               & buses['voltage_kv'].notna()
               & buses['bus_type'].isin(['substation', 'tower', 'hvdc'])].copy()
    print(f'  {len(tx)} tagged tx buses (substation/tower/hvdc, ≥{TRANSMISSION_MIN_KV} kV)')
    print(f'    by voltage: {tx["voltage_kv"].value_counts().to_dict()}')

    tx_geom = gpd.GeoDataFrame(
        tx[['bus_id', 'voltage_kv']],
        geometry=gpd.points_from_xy(tx['lon'], tx['lat'], crs='EPSG:4326'),
    ).to_crs(32651)
    tx_sindex = tx_geom.sindex

    # For each candidate: snap both endpoints, classify the match
    records = []
    for idx, row in untagged_m.iterrows():
        geom = row.geometry
        # MultiLineString: take overall (first, last) extreme endpoints
        if geom.geom_type == 'MultiLineString':
            pts = [(seg.coords[0], seg.coords[-1]) for seg in geom.geoms]
            p_start = Point(pts[0][0])
            p_end = Point(pts[-1][1])
        else:
            coords = list(geom.coords)
            p_start = Point(coords[0])
            p_end = Point(coords[-1])

        def nearest(point):
            # query buffer = MAX_SNAP_KM * 1000 m, then min by exact distance
            buf = point.buffer(MAX_SNAP_KM * 1000)
            candidates = tx_geom.iloc[list(tx_sindex.query(buf))]
            if len(candidates) == 0:
                return None, None
            dists = candidates.geometry.distance(point)
            i = dists.idxmin()
            if dists.loc[i] > MAX_SNAP_KM * 1000:
                return None, None
            return tx_geom.loc[i, 'bus_id'], tx_geom.loc[i, 'voltage_kv'], dists.loc[i]

        n1 = nearest(p_start)
        n2 = nearest(p_end)
        if n1[0] is None or n2[0] is None:
            outcome = 'no_match'
            inferred_kv = None
        elif n1[0] == n2[0]:
            outcome = 'self_loop'
            inferred_kv = None
        elif n1[1] == n2[1]:
            outcome = 'matched_same_voltage'
            inferred_kv = float(n1[1])
        else:
            # different voltages — likely an inter-voltage tap; take max
            outcome = 'matched_mixed_voltage'
            inferred_kv = float(max(n1[1], n2[1]))

        records.append({
            'osm_idx': idx,
            'length_km': row['length_km'],
            'from_bus': n1[0],
            'to_bus': n2[0],
            'from_kv': n1[1],
            'to_kv': n2[1],
            'from_dist_m': n1[2] if n1[0] else None,
            'to_dist_m': n2[2] if n2[0] else None,
            'inferred_kv': inferred_kv,
            'outcome': outcome,
        })

    rec = pd.DataFrame(records)
    print()
    print('Outcome distribution:')
    print(rec['outcome'].value_counts().to_string())
    recoverable = rec[rec['inferred_kv'].notna()].copy()
    print(f'\nRecoverable: {len(recoverable)} lines')
    if len(recoverable):
        print(f'  total length: {recoverable["length_km"].sum():.1f} km')
        print('  by inferred voltage:')
        print(recoverable['inferred_kv'].value_counts().sort_index().to_string())
        print('  endpoint-to-bus distance distribution (m):')
        print(
            f'    from: min {recoverable["from_dist_m"].min():.0f}, '
            f'median {recoverable["from_dist_m"].median():.0f}, '
            f'max {recoverable["from_dist_m"].max():.0f}'
        )
        print(
            f'    to:   min {recoverable["to_dist_m"].min():.0f}, '
            f'median {recoverable["to_dist_m"].median():.0f}, '
            f'max {recoverable["to_dist_m"].max():.0f}'
        )

    # Effect on connectivity: transmission subgraph
    lines_df = pd.read_csv(PROC / 'lines.csv')
    tx_bus_ids = set(tx['bus_id'])
    G = nx.Graph()
    G.add_nodes_from(tx_bus_ids)
    for _, ln in lines_df.iterrows():
        if ln['from_bus'] in tx_bus_ids and ln['to_bus'] in tx_bus_ids:
            G.add_edge(ln['from_bus'], ln['to_bus'])
    comps_before = nx.number_connected_components(G)
    print(f'\nTx-subgraph components BEFORE recovery: {comps_before}')

    G2 = G.copy()
    for _, r in recoverable.iterrows():
        G2.add_edge(r['from_bus'], r['to_bus'])
    comps_after = nx.number_connected_components(G2)
    print(f'Tx-subgraph components AFTER recovery:  {comps_after}')
    print(f'Δ components: {comps_before - comps_after}')

    # Per-province effect: which buses are in which province
    bus_prov = dict(zip(buses['bus_id'], buses['province']))
    if len(recoverable):
        recoverable['from_prov'] = recoverable['from_bus'].map(bus_prov)
        recoverable['to_prov'] = recoverable['to_bus'].map(bus_prov)
        print('\nRecovered lines by province (counting each end):')
        prov_counts = pd.concat([recoverable['from_prov'], recoverable['to_prov']]) \
            .value_counts()
        print(prov_counts.to_string())


if __name__ == '__main__':
    main()
