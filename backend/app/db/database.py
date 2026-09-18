"""
database.py
===========

Thin SQLite helper for HoshiyarLahore.

- Resolves a single DB path (hoshiyar.db at the repo root by default).
- Provides get_connection() with row factory set to sqlite3.Row.
- Provides init_db() to (re)create the schema from schema.sql.
- Provides load_towns_from_metadata() to seed the towns table from the
  committed JSON + GeoJSON so the DB is populated on first run.
"""

from __future__ import annotations

import json
import os
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

DEFAULT_DB_PATH = os.path.join(REPO_ROOT, "hoshiyar.db")
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "schema.sql")
METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")
GEOJSON_PATH = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns.geojson")


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection with Row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create all tables from schema.sql (idempotent)."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = get_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print(f"[db] Schema initialised at {db_path}")
    finally:
        conn.close()


def load_towns_from_metadata(db_path: str = DEFAULT_DB_PATH) -> int:
    """
    Seed the towns table from town_metadata.json + lahore_towns.geojson.
    Returns the number of towns loaded. Safe to run repeatedly (upsert).
    """
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    geometry_by_id: dict[str, str] = {}
    if os.path.exists(GEOJSON_PATH):
        with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
            geojson = json.load(f)
        for feat in geojson.get("features", []):
            tid = feat.get("properties", {}).get("id")
            if tid:
                geometry_by_id[tid] = json.dumps(feat["geometry"])

    conn = get_connection(db_path)
    count = 0
    try:
        for t in metadata["towns"]:
            conn.execute(
                """
                INSERT INTO towns (
                    id, name, name_ur, centroid_lat, centroid_lon,
                    population, area_km2, population_density,
                    vegetation_deficit, elevation_band, geometry_geojson,
                    verified, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    name_ur=excluded.name_ur,
                    centroid_lat=excluded.centroid_lat,
                    centroid_lon=excluded.centroid_lon,
                    population=excluded.population,
                    area_km2=excluded.area_km2,
                    population_density=excluded.population_density,
                    vegetation_deficit=excluded.vegetation_deficit,
                    elevation_band=excluded.elevation_band,
                    geometry_geojson=excluded.geometry_geojson,
                    verified=excluded.verified,
                    notes=excluded.notes
                """,
                (
                    t["id"],
                    t["name"],
                    t.get("name_ur", ""),
                    t["centroid"]["lat"],
                    t["centroid"]["lon"],
                    t.get("population"),
                    t.get("area_km2"),
                    t.get("population_density"),
                    t.get("vegetation_deficit"),
                    t.get("elevation_band"),
                    geometry_by_id.get(t["id"]),
                    1 if t.get("verified") else 0,
                    t.get("notes", ""),
                ),
            )
            count += 1
        conn.commit()
        print(f"[db] Loaded {count} towns into database")
    finally:
        conn.close()
    return count


if __name__ == "__main__":
    init_db()
    load_towns_from_metadata()
