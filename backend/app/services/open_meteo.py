"""
open_meteo.py
=============

Client for the Open-Meteo weather API (https://open-meteo.com/).

Open-Meteo is free for non-commercial use and requires NO API key. We use three
endpoints:

  1. Forecast API   -> current conditions + hourly forecast (next N days)
     https://api.open-meteo.com/v1/forecast
  2. Archive API    -> historical daily data (for 10-year baselines)
     https://archive-api.open-meteo.com/v1/archive

All requests target a single (lat, lon) point = a town centroid.

NOTE ON TESTING
---------------
This module talks to the live Open-Meteo API. If you are running in a sandboxed
environment without outbound internet, these calls will fail. On a normal machine
with internet access they work without any key. Run:

    python -m backend.app.services.open_meteo

to do a quick smoke test against Lahore's centroid.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEZONE = "Asia/Karachi"
REQUEST_TIMEOUT = 30


def _get_with_retry(url: str, params: dict, max_retries: int = 1):
    """
    GET with retry-and-backoff specifically for HTTP 429 (Too Many Requests).

    Open-Meteo's free tier is generous (600/min, 5000/hour, 10000/day - see
    https://open-meteo.com/en/terms) but a burst of near-simultaneous requests
    (e.g. several towns fetched back-to-back at app startup), especially from
    a shared/NAT'd IP on a hosting platform's free tier, can still trip a
    transient 429. One retry catches that kind of brief hiccup.

    max_retries is deliberately small (1, not 3+): observed in production
    that a SUSTAINED 429 (a longer, IP-level rate limit - e.g. a shared
    Render free-tier IP already exhausted by other tenants' unrelated
    traffic, not something this app's own request pattern can fix) does NOT
    clear up within a short retry window, so spending longer just delays the
    response without improving the odds. The failure-cooldown mechanism in
    scheduler.py (WEATHER_FAILURE_COOLDOWN_MINUTES) is what actually handles
    that longer case - by backing off entirely for several minutes after a
    total failure, rather than every visitor's request retrying in vain.
    """
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                if attempt < max_retries:
                    print(f"    429 rate-limited, retrying in {wait:.0f}s "
                          f"(attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait)
                    delay *= 2
                    continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("_get_with_retry: exhausted retries with no response")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CurrentWeather:
    """Current conditions at a point."""
    time: str
    temperature_c: float
    humidity_pct: float
    apparent_temperature_c: float
    wind_speed_kmh: float

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "apparent_temperature_c": self.apparent_temperature_c,
            "wind_speed_kmh": self.wind_speed_kmh,
        }


@dataclass
class HourlyForecast:
    """Hourly forecast series at a point."""
    times: list[str] = field(default_factory=list)
    temperature_c: list[float] = field(default_factory=list)
    humidity_pct: list[float] = field(default_factory=list)
    apparent_temperature_c: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.times)


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_current_and_forecast(
    lat: float,
    lon: float,
    forecast_days: int = 3,
) -> tuple[CurrentWeather, HourlyForecast]:
    """
    Fetch current conditions and an hourly forecast for the next `forecast_days`.

    Returns (CurrentWeather, HourlyForecast).
    Raises requests.RequestException on network errors and ValueError if the
    response is missing expected fields.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "wind_speed_10m",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
        ]),
        "forecast_days": forecast_days,
        "timezone": TIMEZONE,
    }

    resp = _get_with_retry(FORECAST_URL, params)
    data = resp.json()

    if "current" not in data or "hourly" not in data:
        raise ValueError(
            "Open-Meteo response missing 'current' or 'hourly'. "
            f"Got keys: {list(data.keys())}"
        )

    cur = data["current"]
    current = CurrentWeather(
        time=cur.get("time", ""),
        temperature_c=_num(cur.get("temperature_2m")),
        humidity_pct=_num(cur.get("relative_humidity_2m")),
        apparent_temperature_c=_num(cur.get("apparent_temperature")),
        wind_speed_kmh=_num(cur.get("wind_speed_10m")),
    )

    h = data["hourly"]
    hourly = HourlyForecast(
        times=h.get("time", []),
        temperature_c=[_num(v) for v in h.get("temperature_2m", [])],
        humidity_pct=[_num(v) for v in h.get("relative_humidity_2m", [])],
        apparent_temperature_c=[_num(v) for v in h.get("apparent_temperature", [])],
    )

    return current, hourly


def fetch_historical_daily_max(
    lat: float,
    lon: float,
    start_year: int,
    end_year: int,
) -> dict[str, list]:
    """
    Fetch historical DAILY maximum temperature for a range of years.
    Used to build a 10-year "normal" baseline for each calendar day.

    Returns a dict: {"dates": [...], "temp_max_c": [...]}.

    ONE REQUEST for the whole date range, not one per year: Open-Meteo's
    archive API handles a full multi-year range in a single call just fine.
    Looping year-by-year (the original implementation) multiplied request
    count by ~10x for no benefit and made this call a major contributor to
    hitting Open-Meteo's rate limits during startup bursts across several
    towns. See _get_with_retry() for 429 retry/backoff handling.

    On failure, returns {"dates": [], "temp_max_c": [], "error": "<message>"}
    rather than silently empty lists, so a caller can report *why* it failed
    (e.g. a 429 rate limit) instead of guessing "offline".
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": f"{start_year}-01-01",
        "end_date": f"{end_year}-12-31",
        "daily": "temperature_2m_max",
        "timezone": TIMEZONE,
    }
    try:
        resp = _get_with_retry(ARCHIVE_URL, params)
        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        return {"dates": dates, "temp_max_c": [_num(v) for v in tmax]}
    except requests.RequestException as exc:
        print(f"  [archive] {start_year}-{end_year} failed: {exc}")
        return {"dates": [], "temp_max_c": [], "error": str(exc)}


def baseline_for_date(
    historical: dict[str, list],
    month: int,
    day: int,
    window_days: int = 3,
) -> float | None:
    """
    Given historical daily-max data, compute the average max temperature for a
    given calendar date (month/day), averaged across all years and a +/- window.

    This gives us the "10-year normal" to compare today's forecast against.
    Returns None if no matching data.
    """
    dates = historical.get("dates", [])
    tmax = historical.get("temp_max_c", [])
    target = dt.date(2000, month, day)  # arbitrary leap-safe year for day-of-year math

    matched: list[float] = []
    for d_str, t in zip(dates, tmax):
        try:
            d = dt.date.fromisoformat(d_str)
        except (ValueError, TypeError):
            continue
        # compare month/day within window, ignoring year
        this = dt.date(2000, d.month, min(d.day, 28))  # clamp to avoid Feb 29 issues
        delta = abs((this - target).days)
        delta = min(delta, 365 - delta)
        if delta <= window_days and t is not None:
            matched.append(t)

    if not matched:
        return None
    return round(sum(matched) / len(matched), 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num(value: Any) -> float:
    """Coerce a value to float, returning 0.0 for None/invalid."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Smoke test: fetching current + forecast for Lahore centroid...")
    try:
        current, hourly = fetch_current_and_forecast(31.5204, 74.3587, forecast_days=2)
        print("Current:", current.as_dict)
        print(f"Hourly points: {len(hourly)}")
        if len(hourly):
            print("First hour:", hourly.times[0], hourly.temperature_c[0], "C")
    except Exception as exc:  # noqa: BLE001
        print("Smoke test failed (expected if offline):", exc)