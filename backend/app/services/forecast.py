"""
forecast.py  (Day 3)
====================

72-hour forecast heat-risk for HoshiyarLahore.

Two capabilities:

  1. forecast_risk_series(conn, town_id)
     Applies the risk engine to each hourly forecast point for a tehsil,
     returning a time series of {time, temperature, heat_index, risk_score,
     band} the frontend can plot as a 72-hour timeline.

  2. predictive_alerts(conn)
     Scans every tehsil's forecast and reports the FIRST time each one is
     expected to cross into a dangerous band ("High" or "Critical"), producing
     lead-time warnings such as:
        "Lahore City Tehsil expected to reach CRITICAL heat risk in 36 hours."

Both reuse the same interpretable risk engine used for current conditions, so a
forecasted score is computed exactly the same way as a live one - only the
temperature/humidity inputs differ (they come from the forecast rows).

NOTE: population density and vegetation deficit are static per tehsil, so the
forecast risk varies hour-to-hour purely with the forecasted weather, which is
the honest and intended behaviour.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.app.services.risk_engine import calculate_heat_risk


# ---------------------------------------------------------------------------
# Forecast risk series
# ---------------------------------------------------------------------------

@dataclass
class ForecastPoint:
    time: str
    temperature_c: float
    humidity_pct: float
    heat_index_c: float
    risk_score: float
    band: dict

    def as_dict(self) -> dict:
        return {
            "time": self.time,
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "heat_index_c": self.heat_index_c,
            "risk_score": self.risk_score,
            "band": self.band,
        }


def _town_row(conn, town_id: str):
    return conn.execute(
        "SELECT * FROM towns WHERE id = ?", (town_id,)
    ).fetchone()


def forecast_risk_series(conn, town_id: str, hours: int = 72) -> list[ForecastPoint]:
    """
    Compute the heat-risk score for each of the next `hours` forecast points for
    a tehsil. Returns a list of ForecastPoint ordered by time.
    """
    town = _town_row(conn, town_id)
    if town is None:
        return []

    rows = conn.execute(
        """SELECT forecast_time, temperature_c, humidity_pct
           FROM weather_forecast
           WHERE town_id = ?
           ORDER BY forecast_time
           LIMIT ?""",
        (town_id, hours),
    ).fetchall()

    density = town["population_density"] or 0.0
    veg = town["vegetation_deficit"] or 0.0

    series = []
    for r in rows:
        temp = r["temperature_c"]
        hum = r["humidity_pct"]
        if temp is None or hum is None:
            continue
        result = calculate_heat_risk(
            temperature_c=temp,
            humidity_pct=hum,
            population_density=density,
            vegetation_deficit=veg,
        )
        series.append(ForecastPoint(
            time=r["forecast_time"],
            temperature_c=temp,
            humidity_pct=hum,
            heat_index_c=result.heat_index_c,
            risk_score=result.score,
            band=result.band,
        ))
    return series


def forecast_daily_peaks(series: list[ForecastPoint]) -> list[dict]:
    """
    Collapse an hourly series into per-day peak risk (max score each calendar
    day). Useful for a compact "next 3 days" summary.
    """
    by_day: dict[str, ForecastPoint] = {}
    for p in series:
        day = p.time[:10]  # YYYY-MM-DD
        if day not in by_day or p.risk_score > by_day[day].risk_score:
            by_day[day] = p
    out = []
    for day in sorted(by_day):
        p = by_day[day]
        out.append({
            "date": day,
            "peak_risk_score": p.risk_score,
            "band": p.band,
            "peak_time": p.time,
            "heat_index_c": p.heat_index_c,
        })
    return out


# ---------------------------------------------------------------------------
# Predictive alerts
# ---------------------------------------------------------------------------

@dataclass
class PredictiveAlert:
    town_id: str
    town_name: str
    level: str               # "high" or "critical"
    hours_until: int
    forecast_time: str
    risk_score: float
    heat_index_c: float
    message: str
    recommended_action: str

    def as_dict(self) -> dict:
        return {
            "town_id": self.town_id,
            "town_name": self.town_name,
            "level": self.level,
            "hours_until": self.hours_until,
            "forecast_time": self.forecast_time,
            "risk_score": self.risk_score,
            "heat_index_c": self.heat_index_c,
            "message": self.message,
            "recommended_action": self.recommended_action,
        }


def _parse_time(s: str) -> dt.datetime | None:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def predictive_alerts(conn, threshold: str = "high") -> list[PredictiveAlert]:
    """
    For each tehsil, find the FIRST forecast hour at which it crosses into a
    dangerous band, and report the lead time. `threshold` is "high" (score > 50,
    i.e. High or Critical) or "critical" (score > 75).

    Only future crossings are reported (relative to now). Tehsils already at/above
    the threshold now are reported with hours_until = 0.
    """
    cutoff = 75.0 if threshold == "critical" else 50.0
    now = dt.datetime.now()

    towns = conn.execute("SELECT id, name FROM towns").fetchall()
    alerts: list[PredictiveAlert] = []

    for t in towns:
        series = forecast_risk_series(conn, t["id"])
        for p in series:
            if p.risk_score <= cutoff:
                continue
            ftime = _parse_time(p.time)
            if ftime is None:
                continue
            hours_until = max(0, round((ftime - now).total_seconds() / 3600))
            level = "critical" if p.risk_score > 75 else "high"
            alerts.append(PredictiveAlert(
                town_id=t["id"],
                town_name=t["name"],
                level=level,
                hours_until=hours_until,
                forecast_time=p.time,
                risk_score=p.risk_score,
                heat_index_c=p.heat_index_c,
                message=_predictive_message(t["name"], level, hours_until, p),
                recommended_action=_predictive_action(t["name"], level, hours_until),
            ))
            break  # only the first crossing per tehsil

    # Soonest first, then most severe
    alerts.sort(key=lambda a: (a.hours_until, -a.risk_score))
    return alerts


def _predictive_message(name, level, hours, p) -> str:
    when = "now" if hours == 0 else f"in about {hours} hour" + ("s" if hours != 1 else "")
    lvl = level.upper()
    return (f"{name} expected to reach {lvl} heat risk {when} "
            f"(forecast feels-like {p.heat_index_c:.0f}\u00b0C).")


def _predictive_action(name, level, hours) -> str:
    if hours <= 24:
        return (f"Pre-position cooling-centre resources and outreach teams for "
                f"{name} within the next 24 hours.")
    if hours <= 48:
        return (f"Plan resource allocation for {name}; brief local health "
                f"facilities on the incoming heat.")
    return (f"Add {name} to the 72-hour watch list and monitor the forecast.")
