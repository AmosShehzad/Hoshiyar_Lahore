-- HoshiyarLahore - SQLite schema
-- ------------------------------------
-- We deliberately use SQLite (not PostgreSQL/PostGIS) because the MVP has only
-- 9 towns. Geometry is stored as GeoJSON text; spatial operations are done in
-- Python (shapely) where needed. This keeps setup trivial for a 3-person team.

-- Towns: one row per Lahore administrative town.
CREATE TABLE IF NOT EXISTS towns (
    id                  TEXT PRIMARY KEY,       -- e.g. "ravi"
    name                TEXT NOT NULL,          -- e.g. "Ravi Town"
    name_ur             TEXT,                   -- Urdu name
    centroid_lat        REAL NOT NULL,
    centroid_lon        REAL NOT NULL,
    population          INTEGER,
    area_km2            REAL,
    population_density  REAL,                   -- people per km2
    vegetation_deficit  REAL,                   -- 0..1 proxy (1 = very built-up)
    elevation_band      TEXT,
    geometry_geojson    TEXT,                   -- GeoJSON geometry as text
    verified            INTEGER DEFAULT 0,      -- 1 if population verified vs PBS
    notes               TEXT
);

-- Current weather snapshot: one row per town per refresh.
CREATE TABLE IF NOT EXISTS weather_current (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    town_id                 TEXT NOT NULL,
    observed_at             TEXT NOT NULL,      -- ISO timestamp from Open-Meteo
    fetched_at              TEXT NOT NULL,      -- when WE fetched it (ISO)
    temperature_c           REAL,
    humidity_pct            REAL,
    apparent_temperature_c  REAL,
    wind_speed_kmh          REAL,
    FOREIGN KEY (town_id) REFERENCES towns(id)
);

-- Hourly forecast: many rows per town (one per forecast hour).
CREATE TABLE IF NOT EXISTS weather_forecast (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    town_id                 TEXT NOT NULL,
    forecast_time           TEXT NOT NULL,      -- ISO timestamp of the forecast hour
    fetched_at              TEXT NOT NULL,
    temperature_c           REAL,
    humidity_pct            REAL,
    apparent_temperature_c  REAL,
    FOREIGN KEY (town_id) REFERENCES towns(id)
);

-- Historical baseline: the 10-year "normal" max temperature per town per
-- calendar date (month-day). Used for "X degrees above normal" context.
CREATE TABLE IF NOT EXISTS weather_historical (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    town_id         TEXT NOT NULL,
    month           INTEGER NOT NULL,           -- 1..12
    day             INTEGER NOT NULL,           -- 1..31
    normal_tmax_c   REAL,                        -- avg historical daily max
    years_used      INTEGER,                     -- how many years contributed
    FOREIGN KEY (town_id) REFERENCES towns(id),
    UNIQUE (town_id, month, day)
);

-- Indexes to keep lookups fast.
CREATE INDEX IF NOT EXISTS idx_current_town   ON weather_current(town_id);
CREATE INDEX IF NOT EXISTS idx_forecast_town  ON weather_forecast(town_id);
CREATE INDEX IF NOT EXISTS idx_forecast_time  ON weather_forecast(forecast_time);
CREATE INDEX IF NOT EXISTS idx_hist_town_date ON weather_historical(town_id, month, day);
