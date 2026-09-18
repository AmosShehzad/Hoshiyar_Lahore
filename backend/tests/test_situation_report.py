"""
Tests for the situation report module.

Run with:
    python backend/tests/test_situation_report.py
"""

import datetime as dt
import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.services.situation_report import build_situation_report  # noqa: E402


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE towns (id TEXT PRIMARY KEY, name TEXT, name_ur TEXT,
            population INTEGER, population_density REAL, vegetation_deficit REAL);
        CREATE TABLE weather_current (id INTEGER PRIMARY KEY AUTOINCREMENT,
            town_id TEXT, observed_at TEXT, fetched_at TEXT, temperature_c REAL,
            humidity_pct REAL, apparent_temperature_c REAL, wind_speed_kmh REAL);
        CREATE TABLE weather_forecast (id INTEGER PRIMARY KEY AUTOINCREMENT,
            town_id TEXT, forecast_time TEXT, fetched_at TEXT, temperature_c REAL,
            humidity_pct REAL, apparent_temperature_c REAL);
        CREATE TABLE weather_historical (id INTEGER PRIMARY KEY AUTOINCREMENT,
            town_id TEXT, month INTEGER, day INTEGER, normal_tmax_c REAL, years_used INTEGER);
        """
    )
    conn.execute("INSERT INTO towns VALUES ('city','Lahore City Tehsil','x',4123354,19268,0.88)")
    conn.execute("INSERT INTO weather_current (town_id,observed_at,fetched_at,"
                 "temperature_c,humidity_pct,apparent_temperature_c,wind_speed_kmh) "
                 "VALUES ('city','x','x',44,25,48,8)")
    # rising forecast
    now = dt.datetime.now().replace(minute=0, second=0, microsecond=0)
    for h in range(72):
        temp = 40 + (h / 72.0) * 8
        conn.execute("INSERT INTO weather_forecast (town_id,forecast_time,fetched_at,"
                     "temperature_c,humidity_pct,apparent_temperature_c) VALUES ('city',?,?,?,?,?)",
                     ((now + dt.timedelta(hours=h)).isoformat(timespec="minutes"),
                      "x", round(temp, 1), 25, round(temp + 2, 1)))
    conn.commit()
    return conn


def test_report_builds():
    conn = _db()
    r = build_situation_report(conn, "city")
    assert r is not None
    assert r.town_name == "Lahore City Tehsil"


def test_report_body_has_key_sections():
    conn = _db()
    r = build_situation_report(conn, "city")
    for token in ["HEAT SITREP", "Current risk", "Exposure", "ACTION"]:
        assert token in r.body, f"missing '{token}'"


def test_sms_within_limit():
    conn = _db()
    r = build_situation_report(conn, "city")
    assert len(r.sms_short) <= 160


def test_unknown_town_returns_none():
    conn = _db()
    assert build_situation_report(conn, "nope") is None


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    print("Running situation report tests...")
    sys.exit(0 if _run_all() else 1)
