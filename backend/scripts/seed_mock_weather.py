"""
seed_mock_weather.py
====================

Populate the database with REALISTIC MOCK weather so the full pipeline
(DB -> risk engine -> API -> frontend) can be demonstrated WITHOUT internet
access to Open-Meteo.

WHEN TO USE
-----------
- During development if Open-Meteo is unreachable (e.g. restricted network).
- To get a deterministic dataset for screenshots / demo rehearsal.

IMPORTANT - HONESTY
-------------------
Data inserted here is clearly marked as mock (observed_at contains "MOCK").
For the ACTUAL hackathon demo you should run refresh_weather.py to pull REAL
Open-Meteo data. Never present mock numbers to judges as real observations.
The values below are plausible for a Lahore summer afternoon but are synthetic.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.db.database import (  # noqa: E402
    get_connection,
    init_db,
    load_towns_from_metadata,
)

# Base afternoon temperature per tehsil (deg C). Denser/lower-veg tehsils run
# hotter due to the urban heat island effect. Illustrative summer values.
BASE_TEMP = {
    "lahore_city": 45.5,
    "shalimar": 45.0,
    "model_town": 43.5,
    "lahore_cantonment": 42.5,
    "raiwind": 41.5,
}
BASE_HUMIDITY = 28.0  # dry pre-monsoon afternoon


def seed():
    init_db()
    load_towns_from_metadata()
    conn = get_connection()

    now = dt.datetime.now()
    fetched = now.isoformat(timespec="seconds")
    towns = conn.execute("SELECT id FROM towns").fetchall()

    for row in towns:
        tid = row["id"]
        base = BASE_TEMP.get(tid, 43.0)

        conn.execute("DELETE FROM weather_current WHERE town_id=?", (tid,))
        conn.execute("DELETE FROM weather_forecast WHERE town_id=?", (tid,))

        # Current (mock) - start a few degrees BELOW the base so the forecast
        # can realistically ramp UP into a heatwave over the next 3 days. This
        # makes the Day 3 predictive lead-time alerts ("reaches Critical in
        # ~36h") meaningful in the offline demo.
        start_offset = -5.0
        conn.execute(
            """INSERT INTO weather_current
               (town_id, observed_at, fetched_at, temperature_c,
                humidity_pct, apparent_temperature_c, wind_speed_kmh)
               VALUES (?,?,?,?,?,?,?)""",
            (tid, f"MOCK {fetched}", fetched, base + start_offset, BASE_HUMIDITY,
             base + start_offset + 3.0, 8.0),
        )

        # 72 hours of forecast: daily sine cycle (peak ~3pm) PLUS a gradual
        # warming trend that builds a heatwave by day 2-3.
        rows = []
        for h in range(72):
            ts = (now + dt.timedelta(hours=h)).replace(minute=0, second=0,
                                                        microsecond=0)
            hour = ts.hour
            # diurnal swing +/- 8C around base
            swing = 8.0 * math.sin((hour - 9) / 24.0 * 2 * math.pi)
            # warming trend: starts at start_offset, climbs ~+2C/day up to ~+1
            trend = start_offset + (h / 72.0) * 6.0
            temp = round(base + trend - 4 + swing, 1)
            hum = round(BASE_HUMIDITY + (55 - BASE_HUMIDITY) *
                        max(0, math.sin((hour - 21) / 24.0 * 2 * math.pi)), 0)
            rows.append((tid, ts.isoformat(timespec="minutes"), fetched,
                         temp, hum, round(temp + 2.5, 1)))
        conn.executemany(
            """INSERT INTO weather_forecast
               (town_id, forecast_time, fetched_at, temperature_c,
                humidity_pct, apparent_temperature_c)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()

    conn.close()
    print("Seeded MOCK weather for all towns (clearly flagged as MOCK).")
    print("For the real demo, run: python backend/scripts/refresh_weather.py")


if __name__ == "__main__":
    seed()
