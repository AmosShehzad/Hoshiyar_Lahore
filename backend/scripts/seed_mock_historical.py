"""
seed_mock_historical.py  (Day 2)
================================

Populate weather_historical with REALISTIC MOCK 10-year baselines so the
"X degrees above normal" feature can be demonstrated WITHOUT internet access to
the Open-Meteo archive.

HONESTY
-------
Values here are synthetic but plausible for Lahore's climate (summer normals
roughly 38-42C for daily max). Rows are clearly synthetic (years_used = 0 marks
them as mock so you can tell them apart from real archive data, where
years_used > 0).

For the real submission, run refresh_historical.py to pull genuine Open-Meteo
archive baselines. Never present mock baselines to judges as real climatology.
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

# Approximate summer daily-max "normal" per tehsil at its seasonal peak (deg C).
# Denser / lower-vegetation tehsils run slightly hotter (urban heat island).
PEAK_NORMAL = {
    "lahore_city": 41.5,
    "shalimar": 41.0,
    "model_town": 40.5,
    "lahore_cantonment": 40.0,
    "raiwind": 39.5,
}


def seasonal_normal(peak: float, month: int, day: int) -> float:
    """
    Model a smooth seasonal curve for daily-max temperature that peaks in
    mid-June (around day-of-year 165) and is lower in April and September.
    """
    doy = dt.date(2001, month, day).timetuple().tm_yday
    # Cosine curve peaking near mid-June
    peak_doy = 165
    # amplitude: how far April/Sept dip below the June peak
    amplitude = 7.0
    phase = (doy - peak_doy) / 365.0 * 2 * math.pi
    value = peak - amplitude * (1 - math.cos(phase)) / 2 * 2
    # clamp to something sensible
    return round(max(30.0, min(peak, value)), 1)


def daterange(start_month=4, end_month=9):
    d = dt.date(2001, start_month, 1)
    end = (dt.date(2001, end_month + 1, 1) - dt.timedelta(days=1)
           if end_month < 12 else dt.date(2001, 12, 31))
    while d <= end:
        yield d.month, d.day
        d += dt.timedelta(days=1)


def seed():
    init_db()
    load_towns_from_metadata()
    conn = get_connection()
    towns = conn.execute("SELECT id FROM towns").fetchall()

    for row in towns:
        tid = row["id"]
        peak = PEAK_NORMAL.get(tid, 40.0)
        conn.execute("DELETE FROM weather_historical WHERE town_id = ?", (tid,))
        rows = []
        for month, day in daterange(4, 9):
            normal = seasonal_normal(peak, month, day)
            # years_used = 0 flags this as MOCK (real data uses > 0)
            rows.append((tid, month, day, normal, 0))
        conn.executemany(
            """INSERT OR REPLACE INTO weather_historical
               (town_id, month, day, normal_tmax_c, years_used)
               VALUES (?,?,?,?,?)""",
            rows,
        )
        conn.commit()

    conn.close()
    print("Seeded MOCK historical baselines (Apr-Sep) for all towns.")
    print("These are flagged with years_used = 0. For real baselines run:")
    print("  python backend/scripts/refresh_historical.py")


if __name__ == "__main__":
    seed()
