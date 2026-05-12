-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Buses table
CREATE TABLE buses (
    bus_id TEXT PRIMARY KEY,
    name TEXT,
    geom GEOMETRY(Point, 4326),
    voltage_kv FLOAT,
    province TEXT,
    island TEXT,
    bus_type TEXT,
    p_mw FLOAT,
    q_mvar FLOAT,
    is_synthetic BOOLEAN DEFAULT FALSE,
    data_source TEXT DEFAULT 'osm'
);

-- Lines table
CREATE TABLE lines (
    line_id TEXT PRIMARY KEY,
    from_bus TEXT REFERENCES buses(bus_id),
    to_bus TEXT REFERENCES buses(bus_id),
    geom GEOMETRY(LineString, 4326),
    voltage_kv FLOAT,
    length_km FLOAT,
    r_ohm_per_km FLOAT,
    x_ohm_per_km FLOAT,
    max_i_ka FLOAT,
    is_submarine BOOLEAN DEFAULT FALSE,
    cable_type TEXT DEFAULT 'overhead',
    is_synthetic BOOLEAN DEFAULT FALSE,
    data_source TEXT DEFAULT 'osm'
);

-- Load flow results (per scenario)
CREATE TABLE load_flow_results (
    id SERIAL PRIMARY KEY,
    scenario TEXT,  -- 'morning_peak' | 'evening_peak' | 'off_peak'
    bus_id TEXT REFERENCES buses(bus_id),
    line_id TEXT REFERENCES lines(line_id),
    vm_pu FLOAT,
    va_degree FLOAT,
    loading_percent FLOAT,
    p_from_mw FLOAT,
    p_to_mw FLOAT
);

-- Spatial indexes (critical for query performance)
CREATE INDEX idx_buses_geom ON buses USING GIST(geom);
CREATE INDEX idx_lines_geom ON lines USING GIST(geom);
