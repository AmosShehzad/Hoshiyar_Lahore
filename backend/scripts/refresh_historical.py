"""
refresh_historical.py  (Day 2)
==============================

Build the 10-year "normal" baseline for each town and store it in the
weather_historical table.

For each town centroid we:
  1. Pull ~10 years of daily maximum temperature from the Open-Meteo archive.
  2. For each calendar date in the summer window (Apr-Sep by default), compute
     the average historical daily max across those years (with a +/- day window).
  3. Store (town_id, month, day, normal_tmax_c, years_used) rows.

The risk engine / API then uses these to say:
    "Today's forecast max is 44C. The 10-year average for this date is 39C.
     That is 5C above normal."

USAGE
-----
    python backend/scripts/refresh_historical.py
    python backend/scripts/refresh_historical.py --years 10 --start-month 4 --end-month 9

NOTES
-----
- The archive API can be slow. Fetching 10 years x 9 towns takes a few minutes.
- Requires internet (no API key). If offline, use seed_mock_historical.py instead.
- Safe to re-run: it clears and rebuilds each town's baseline rows.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.db.database import (  # noqa: E402
    get_connection,
    init_db,
    load_towns_from_metadata,
)
from backend.app.services.open_meteo import (  # noqa: E402
    baseline_for_date,
    fetch_historical_daily_max,
)


def daterange_month_days(start_month: int, end_month: int):
    """Yield (month, day) pairs for the given inclusive month range."""
    year = 2001  # non-leap reference year
    d = dt.date(year, start_month, 1)
    # last day of end_month
    if end_month == 12:
        end = dt.date(year, 12, 31)
    else:
        end = dt.date(year, end_month + 1, 1) - dt.timedelta(days=1)
    while d <= end:
        yield d.month, d.day
        d += dt.timedelta(days=1)


def refresh_historical(years: int, start_month: int, end_month: int) -> tuple[int, int, str | None]:
    """Returns (towns_updated, towns_failed, last_error). Like
    refresh_all_towns(), this never raises even on total failure, so the
    return value is the only reliable success signal for callers such as the
    auto-refresh scheduler. last_error is the most recent failure's actual
    message, so a status endpoint can report why, not just that it failed."""
    init_db()
    load_towns_from_metadata()

    current_year = dt.date.today().year
    end_year = current_year - 1
    start_year = end_year - years + 1

    conn = get_connection()
    towns = conn.execute(
        "SELECT id, name, centroid_lat, centroid_lon FROM towns"
    ).fetchall()

    print(f"Building {years}-year baselines ({start_year}-{end_year}) "
          f"for months {start_month}-{end_month}...")

    ok, failed = 0, 0
    last_error: str | None = None
    for town in towns:
        tid = town["id"]
        print(f"\n[{tid}] fetching archive {start_year}-{end_year} ...")
        historical = fetch_historical_daily_max(
            town["centroid_lat"], town["centroid_lon"], start_year, end_year
        )
        n_points = len(historical.get("dates", []))
        if n_points == 0:
            err = historical.get("error", "no archive data returned")
            print(f"  [{tid}] failed: {err}. Skipping.")
            last_error = err
            failed += 1
            time.sleep(0.5)
            continue

        # Rebuild this town's baseline rows
        conn.execute("DELETE FROM weather_historical WHERE town_id = ?", (tid,))

        rows = []
        for month, day in daterange_month_days(start_month, end_month):
            normal = baseline_for_date(historical, month, day, window_days=3)
            if normal is not None:
                rows.append((tid, month, day, normal, years))

        conn.executemany(
            """INSERT OR REPLACE INTO weather_historical
               (town_id, month, day, normal_tmax_c, years_used)
               VALUES (?,?,?,?,?)""",
            rows,
        )
        conn.commit()
        print(f"  [{tid}] stored {len(rows)} daily baselines "
              f"(from {n_points} archive days)")
        ok += 1
        time.sleep(0.5)  # brief pause between towns - gentle on the API

    conn.close()
    print("\nHistorical baselines complete.")
    if failed and ok == 0:
        print("All fetches failed. Are you offline? The archive API needs "
              "internet (no API key required).")
    return ok, failed, last_error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build historical heat baselines.")
    parser.add_argument("--years", type=int, default=10,
                        help="Number of years of history (default 10)")
    parser.add_argument("--start-month", type=int, default=4,
                        help="First month to build baselines for (default 4 = April)")
    parser.add_argument("--end-month", type=int, default=9,
                        help="Last month to build baselines for (default 9 = September)")
    args = parser.parse_args()
    refresh_historical(args.years, args.start_month, args.end_month)