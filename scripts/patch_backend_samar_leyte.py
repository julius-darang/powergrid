#!/usr/bin/env python3
"""Patch backend/data/processed/ with new Samar+Leyte 69 kV buses and lines.

Mirrors what notebooks 06_v1_substation_import and 07_v1_line_synthesis would do
for the newly-added v1 entries in data/buses.csv and data/lines.csv. Run after
hand-editing the v1 source files when re-running the full Jupyter pipeline is
not feasible.

Idempotent: skips buses already present in processed (by v1_code) and lines
whose endpoint pair already exists in processed.
"""
from __future__ import annotations
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V1_BUSES = ROOT / 'data' / 'buses.csv'
V1_LINES = ROOT / 'data' / 'lines.csv'
PROC_BUSES = ROOT / 'backend' / 'data' / 'processed' / 'buses.csv'
PROC_LINES = ROOT / 'backend' / 'data' / 'processed' / 'lines.csv'

PROVINCE = {
    # Northern Samar
    '04ALLEN': 'Northern Samar', '04SANISIDRO': 'Northern Samar',
    '04CATARMAN': 'Northern Samar', '04BOBON': 'Northern Samar',
    '04BOBOLOSAN': 'Northern Samar', '04LOPEDEVEGA': 'Northern Samar',
    '04CAPOOCAN': 'Northern Samar',
    # Samar
    '04SANAGUSTINS': 'Samar', '04CATBALOGAN': 'Samar',
    '04PARANAS69': 'Samar', '04CALBAYOG69': 'Samar', '04STARITA69': 'Samar',
    # Eastern Samar
    '04TAFT': 'Eastern Samar', '04BORONGAN': 'Eastern Samar',
    '04QUINAPONDAN': 'Eastern Samar',
    # Leyte
    '04BABATNGN69': 'Leyte', '04PALO': 'Leyte', '04TOLOSA': 'Leyte',
    '04TUNGA': 'Leyte', '04TALISAYAN': 'Leyte', '04SANAGUSTINL': 'Leyte',
    '04BAYBAY': 'Leyte', '04JAVIER': 'Leyte', '04HILONGOS': 'Leyte',
    '04ISABEL69': 'Leyte', '04TABANGO69': 'Leyte', '04SAMBULAWAN': 'Leyte',
    # Southern Leyte
    '04BONTOC': 'Southern Leyte', '04HIMAYANGAN': 'Southern Leyte',
    '04STBERNARD': 'Southern Leyte', '04MAASIN69': 'Southern Leyte',
    # Biliran
    '04BILIRAN': 'Biliran', '04NAVAL': 'Biliran',
}

# Standard per-km params used by notebook 07 synthetic_v1 lines
LINE_PARAMS = {
    69:  {'r': 0.15,  'x': 0.4,  'max_i': 0.5},
    138: {'r': 0.08,  'x': 0.4,  'max_i': 0.7},
    230: {'r': 0.05,  'x': 0.4,  'max_i': 0.9},
}

# Sambulawan ↔ Biliran crosses the Biliran Strait — submarine cable.
SUBMARINE_PAIRS = {('04SAMBULAWAN', '04BILIRAN'), ('04BILIRAN', '04SAMBULAWAN')}
SUBMARINE_69KV = {'r': 0.18, 'x': 0.14, 'max_i': 0.45, 'cable_type': 'submarine_xlpe'}


def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    v1_buses = {}
    with open(V1_BUSES) as f:
        for r in csv.DictReader(f):
            v1_buses[r['name']] = r
    with open(V1_LINES) as f:
        v1_lines = list(csv.DictReader(f))

    with open(PROC_BUSES) as f:
        reader = csv.DictReader(f)
        proc_buses_fields = reader.fieldnames
        proc_buses = list(reader)
    with open(PROC_LINES) as f:
        reader = csv.DictReader(f)
        proc_lines_fields = reader.fieldnames
        proc_lines = list(reader)

    v1_to_busid = {r['v1_code']: r['bus_id'] for r in proc_buses if r['v1_code']}

    # 1) update existing Babatngon coord to OSM-authoritative
    for r in proc_buses:
        if r['bus_id'] == 'v1_04babatngn':
            old = (r['lat'], r['lon'])
            r['lat'] = '11.3565'
            r['lon'] = '124.9508'
            print(f'UPDATE v1_04babatngn coords: {old} -> (11.3565, 124.9508)')
            break

    # 2) add new v1_curated buses
    new_buses = []
    for v1_name in PROVINCE:
        if v1_name in v1_to_busid:
            print(f'  skip bus {v1_name} (already in processed as {v1_to_busid[v1_name]})')
            continue
        if v1_name not in v1_buses:
            print(f'  WARN: {v1_name} listed in PROVINCE but not in data/buses.csv')
            continue
        v1 = v1_buses[v1_name]
        bus_id = 'v1_' + v1_name.lower()
        new_buses.append({
            'bus_id': bus_id,
            'name': v1['description'].split(',')[0].strip('"'),
            'lat': v1['y'],
            'lon': v1['x'],
            'voltage_kv': f"{float(v1['v_nom']):.1f}",
            'province': PROVINCE[v1_name],
            'island': v1['island'],
            'bus_type': v1['bus_type'],
            'p_mw': '',
            'q_mvar': '',
            'is_synthetic': 'False',
            'data_source': 'v1_curated',
            'v1_code': v1_name,
            'v1_bus_type': v1['bus_type'],
        })
        v1_to_busid[v1_name] = bus_id

    # 3) add new lines (only those touching at least one newly-added bus)
    existing_pairs = {tuple(sorted([l['from_bus'], l['to_bus']])) for l in proc_lines}
    new_keys = set(PROVINCE)
    counters = {}
    new_lines = []
    for vl in v1_lines:
        b0, b1 = vl['bus0'], vl['bus1']
        if b0 not in new_keys and b1 not in new_keys:
            continue
        if b0 not in v1_to_busid or b1 not in v1_to_busid:
            print(f'  SKIP line {vl["name"]}: unresolved endpoint(s) ({b0}, {b1})')
            continue
        from_bus, to_bus = v1_to_busid[b0], v1_to_busid[b1]
        key = tuple(sorted([from_bus, to_bus]))
        if key in existing_pairs:
            print(f'  skip line {vl["name"]}: pair already in processed')
            continue
        existing_pairs.add(key)

        voltage = int(float(vl['s_nom']))
        lon1, lat1 = float(v1_buses[b0]['x']), float(v1_buses[b0]['y'])
        lon2, lat2 = float(v1_buses[b1]['x']), float(v1_buses[b1]['y'])
        length = haversine_km(lon1, lat1, lon2, lat2)
        if length < 0.01:
            length = 0.01  # transformer/colocated ties

        if (b0, b1) in SUBMARINE_PAIRS or (b1, b0) in SUBMARINE_PAIRS:
            params = SUBMARINE_69KV
            is_sub = 'True'
            cable = params['cable_type']
        else:
            params = LINE_PARAMS[voltage]
            is_sub = 'False'
            cable = 'overhead'

        isl0 = v1_buses[b0]['island'].lower()
        isl1 = v1_buses[b1]['island'].lower()
        region = isl0 if isl0 == isl1 else f'{isl0}_{isl1}'
        counters[region] = counters.get(region, 0) + 1
        line_id = f'line_v1_{region}_{counters[region]:02d}'

        new_lines.append({
            'line_id': line_id,
            'from_bus': from_bus,
            'to_bus': to_bus,
            'voltage_kv': f'{float(voltage):.1f}',
            'length_km': str(length),
            'r_ohm_per_km': str(params['r']),
            'x_ohm_per_km': str(params['x']),
            'max_i_ka': str(params['max_i']),
            'is_submarine': is_sub,
            'cable_type': cable,
            'is_synthetic': 'True',
            'data_source': 'synthetic_v1',
        })

    # 4) write back
    proc_buses.extend(new_buses)
    proc_lines.extend(new_lines)
    with open(PROC_BUSES, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=proc_buses_fields)
        w.writeheader()
        w.writerows(proc_buses)
    with open(PROC_LINES, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=proc_lines_fields)
        w.writeheader()
        w.writerows(proc_lines)

    print(f'\n+{len(new_buses)} buses, +{len(new_lines)} lines')
    print(f'Total: {len(proc_buses)} buses, {len(proc_lines)} lines')


if __name__ == '__main__':
    main()
