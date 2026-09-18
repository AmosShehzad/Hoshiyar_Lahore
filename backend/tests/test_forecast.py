"""
Tests for the Day 3 forecast module (forecast risk series + predictive alerts).

Run with:
    python backend/tests/test_forecast.py
"""

import datetime as dt
import os
import sqlite3
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.services.forecast import (  # noqa: E402
    forecast_daily_peaks,
    forecast_risk_series,
    predictive_alerts,
)


def _db_with_forecast():
    """In-memory DB with one tehsil and a rising-temperature forecast."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE towns (
            id TEXT PRIMARY KEY, name TEXT, population INTEGER,
            population_density REAL, vegetation_deficit REAL
        );
        CREATE TABLE weather_forecast (
            id INTEGER PRIMARY KEY AUTOINCREMENT, town_id TEXT,
            forecast_time TEXT, fetched_at TEXT, temperature_c REAL,
            humidity_pct REAL, apparent_temperature_c REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO towns VALUES ('city','Lahore City Tehsil',4123354,19268,0.88)"
    )
    # Build 72 hours starting cool (30C) and rising to hot (48C)
    now = dt.datetime.now().replace(minute=0, second=0, microsecond=0)
    for h in range(72):
        temp = 30.0 + (h / 72.0) * 18.0  # 30 -> 48
        ts = (now + dt.timedelta(hours=h)).isoformat(timespec="minutes")
        conn.execute(
            "INSERT INTO weather_forecast (town_id,forecast_time,fetched_at,"
            "temperature_c,humidity_pct,apparent_temperature_c) VALUES "
            "('city',?,?,?,?,?)",
            (ts, "x", round(temp, 1), 25, round(temp + 2, 1)),
        )
    conn.commit()
    return conn


def test_forecast_series_length():
    conn = _db_with_forecast()
    series = forecast_risk_series(conn, "city", hours=72)
    assert len(series) == 72


def test_forecast_series_rises():
    conn = _db_with_forecast()
    series = forecast_risk_series(conn, "city")
    # Later hours should be hotter/riskier than earlier ones
    assert series[-1].risk_score > series[0].risk_score


def test_forecast_scores_in_range():
    conn = _db_with_forecast()
    series = forecast_risk_series(conn, "city")
    assert all(0 <= p.risk_score <= 100 for p in series)


def test_daily_peaks_returns_one_per_day():
    conn = _db_with_forecast()
    series = forecast_risk_series(conn, "city")
    peaks = forecast_daily_peaks(series)
    # 72 hours spans 3-4 calendar days
    assert 3 <= len(peaks) <= 4
    # Each peak should be the max for its day
    for p in peaks:
        assert "peak_risk_score" in p


def test_predictive_alert_detects_crossing():
    conn = _db_with_forecast()
    alerts = predictive_alerts(conn, threshold="high")
    assert len(alerts) == 1
    a = alerts[0]
    assert a.town_id == "city"
    assert a.hours_until >= 0
    assert a.level in ("high", "critical")


def test_predictive_alert_unknown_town_absent():
    conn = _db_with_forecast()
    # Only 'city' exists; ensure no phantom alerts
    alerts = predictive_alerts(conn, threshold="critical")
    assert all(a.town_id == "city" for a in alerts)


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
    print("Running forecast tests...")
    ok = _run_all()
    sys.exit(0 if ok else 1)
