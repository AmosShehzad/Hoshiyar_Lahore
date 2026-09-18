"""
Tests for the Day 2 heat intelligence module (ranking + historical comparison).

Run with:
    python backend/tests/test_heat_intelligence.py
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.services.heat_intelligence import (  # noqa: E402
    historical_comparison,
    rank_towns,
)


def _memory_db():
    """Build a tiny in-memory DB with the columns the functions need."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE towns (
            id TEXT PRIMARY KEY, name TEXT, name_ur TEXT,
            centroid_lat REAL, centroid_lon REAL,
            population INTEGER, area_km2 REAL, population_density REAL,
            vegetation_deficit REAL, elevation_band TEXT,
            geometry_geojson TEXT, verified INTEGER, notes TEXT
        );
        CREATE TABLE weather_current (
            id INTEGER PRIMARY KEY AUTOINCREMENT, town_id TEXT,
            observed_at TEXT, fetched_at TEXT, temperature_c REAL,
            humidity_pct REAL, apparent_temperature_c REAL, wind_speed_kmh REAL
        );
        CREATE TABLE weather_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT, town_id TEXT,
            forecast_time TEXT, fetched_at TEXT, temperature_c REAL,
            humidity_pct REAL, apparent_temperature_c REAL
        );
        CREATE TABLE weather_historical (
            id INTEGER PRIMARY KEY AUTOINCREMENT, town_id TEXT,
            month INTEGER, day INTEGER, normal_tmax_c REAL, years_used INTEGER
        );
        """
    )
    # Two towns: one dense/hot, one milder
    conn.execute(
        "INSERT INTO towns (id,name,population,population_density,vegetation_deficit) "
        "VALUES ('hot','Hot Town',1000000,38000,0.85)"
    )
    conn.execute(
        "INSERT INTO towns (id,name,population,population_density,vegetation_deficit) "
        "VALUES ('mild','Mild Town',500000,7000,0.45)"
    )
    conn.execute(
        "INSERT INTO weather_current (town_id,observed_at,fetched_at,temperature_c,"
        "humidity_pct,apparent_temperature_c,wind_speed_kmh) "
        "VALUES ('hot','x','x',46,20,49,8)"
    )
    conn.execute(
        "INSERT INTO weather_current (town_id,observed_at,fetched_at,temperature_c,"
        "humidity_pct,apparent_temperature_c,wind_speed_kmh) "
        "VALUES ('mild','x','x',37,35,39,8)"
    )
    conn.commit()
    return conn


def test_ranking_orders_hot_town_first():
    conn = _memory_db()
    ranked = rank_towns(conn)
    assert ranked[0].town_id == "hot"
    assert ranked[0].priority == 1
    assert ranked[-1].town_id == "mild"


def test_ranking_priorities_are_sequential():
    conn = _memory_db()
    ranked = rank_towns(conn)
    assert [r.priority for r in ranked] == list(range(1, len(ranked) + 1))


def test_historical_comparison_no_baseline():
    conn = _memory_db()
    # No historical rows inserted -> should report no baseline gracefully
    comp = historical_comparison(conn, "hot")
    assert comp.normal_max_c is None
    assert "No historical baseline" in comp.summary


def test_historical_comparison_with_baseline():
    import datetime as dt
    conn = _memory_db()
    today = dt.date.today()
    # Insert a baseline for today and a forecast row for today
    conn.execute(
        "INSERT INTO weather_historical (town_id,month,day,normal_tmax_c,years_used) "
        "VALUES ('hot',?,?,?,?)",
        (today.month, today.day, 38.0, 10),
    )
    conn.execute(
        "INSERT INTO weather_forecast (town_id,forecast_time,fetched_at,temperature_c,"
        "humidity_pct,apparent_temperature_c) VALUES ('hot',?,?,?,?,?)",
        (f"{today.isoformat()}T15:00", "x", 44.0, 20, 47),
    )
    conn.commit()
    comp = historical_comparison(conn, "hot")
    assert comp.normal_max_c == 38.0
    assert comp.forecast_max_c == 44.0
    assert comp.anomaly_c == 6.0
    assert comp.is_mock_baseline is False
    assert "above normal" in comp.summary


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    print("Running heat intelligence tests...")
    ok = _run_all()
    sys.exit(0 if ok else 1)
