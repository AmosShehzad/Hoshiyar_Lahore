"""
refresh_weather.py
==================

Fetch current + forecast weather from Open-Meteo for all 9 Lahore towns and
store it in the SQLite database.

USAGE
-----
    python backend/scripts/refresh_weather.py

Run this whenever you want fresh data. On a live machine with internet it takes
a few seconds. In a sandbox without internet it will report failures per town
but will not crash.

This is Member 1's Day 1 afternoon deliverable: a working pipeline
Open-Meteo -> SQLite.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time

# Allow running as a script: add repo root to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.db.database import (  # noqa: E402
    get_connection,
    init_db,
    load_towns_from_metadata,
)
from backend.app.services.open_meteo import (  # noqa: E402
    fetch_current_and_forecast,
)

FORECAST_DAYS = 3


def refresh_all_towns() -> tuple[int, int, str | None]:
    """Returns (towns_updated, towns_failed, last_error). Callers (including
    the auto-refresh scheduler) can tell a real success from a silent total
    failure - refresh_all_towns() never raises even when every fetch fails,
    so the return value is the only reliable signal. last_error is the most
    recent failure's actual message (e.g. "429 ... Too Many Requests"), so a
    status endpoint can report *why* it failed instead of guessing "offline"."""
    now_iso = dt.datetime.now().isoformat(timespec="seconds")

    # Make sure DB + towns exist
    init_db()
    load_towns_from_metadata()

    conn = get_connection()
    towns = conn.execute(
        "SELECT id, name, centroid_lat, centroid_lon FROM towns"
    ).fetchall()

    print(f"Refreshing weather for {len(towns)} towns...")
    ok, failed = 0, 0
    last_error: str | None = None

    for town in towns:
        tid = town["id"]
        lat = town["centroid_lat"]
        lon = town["centroid_lon"]
        try:
            current, hourly = fetch_current_and_forecast(
                lat, lon, forecast_days=FORECAST_DAYS
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [{tid}] FAILED: {exc}")
            failed += 1
            last_error = str(exc)
            time.sleep(0.5)  # brief pause even on failure, before the next town
            continue

        # Clear previous rows for this town (keep the DB small and current)
        conn.execute("DELETE FROM weather_current WHERE town_id = ?", (tid,))
        conn.execute("DELETE FROM weather_forecast WHERE town_id = ?", (tid,))

        # Insert current
        conn.execute(
            """
            INSERT INTO weather_current (
                town_id, observed_at, fetched_at, temperature_c,
                humidity_pct, apparent_temperature_c, wind_speed_kmh
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                tid,
                current.time,
                now_iso,
                current.temperature_c,
                current.humidity_pct,
                current.apparent_temperature_c,
                current.wind_speed_kmh,
            ),
        )

        # Insert forecast hours
        rows = []
        for i in range(len(hourly)):
            rows.append((
                tid,
                hourly.times[i],
                now_iso,
                hourly.temperature_c[i] if i < len(hourly.temperature_c) else None,
                hourly.humidity_pct[i] if i < len(hourly.humidity_pct) else None,
                hourly.apparent_temperature_c[i]
                if i < len(hourly.apparent_temperature_c) else None,
            ))
        conn.executemany(
            """
            INSERT INTO weather_forecast (
                town_id, forecast_time, fetched_at, temperature_c,
                humidity_pct, apparent_temperature_c
            ) VALUES (?,?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()
        print(f"  [{tid}] OK - current {current.temperature_c}C, "
              f"{len(rows)} forecast hours")
        ok += 1
        time.sleep(0.5)  # brief pause between towns - gentle on the API

    conn.close()
    print(f"\nDone. {ok} towns updated, {failed} failed.")
    if failed and ok == 0:
        print("All fetches failed. Are you offline? Open-Meteo needs internet "
              "(no API key required).")
    return ok, failed, last_error


if __name__ == "__main__":
    refresh_all_towns()