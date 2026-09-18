"""
heat_intelligence.py  (Day 2)
=============================

Higher-level heat intelligence built on top of the risk engine:

  1. historical_comparison(...) - compares today's forecast max against the
     town's 10-year "normal" for this calendar date, producing the
     "X degrees above normal" insight.

  2. rank_towns(...) - produces the prioritised list health authorities act on:
     "Priority 1: Shalimar Town (risk 88), Priority 2: ..."

These read from the SQLite tables populated on Day 1-2 (weather_current,
weather_forecast, weather_historical) and reuse risk_engine for scoring.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.app.services.risk_engine import calculate_heat_risk


# ---------------------------------------------------------------------------
# Historical comparison
# ---------------------------------------------------------------------------

@dataclass
class HistoricalComparison:
    town_id: str
    forecast_max_c: float | None
    normal_max_c: float | None
    anomaly_c: float | None          # forecast - normal (+ = hotter than normal)
    is_mock_baseline: bool
    summary: str

    def as_dict(self) -> dict:
        return {
            "town_id": self.town_id,
            "forecast_max_c": self.forecast_max_c,
            "normal_max_c": self.normal_max_c,
            "anomaly_c": self.anomaly_c,
            "is_mock_baseline": self.is_mock_baseline,
            "summary": self.summary,
        }


def _forecast_max_for_today(conn, town_id: str) -> float | None:
    """Highest forecast temperature for the rest of today (local date)."""
    today = dt.date.today().isoformat()
    rows = conn.execute(
        """SELECT temperature_c FROM weather_forecast
           WHERE town_id = ? AND forecast_time LIKE ?""",
        (town_id, f"{today}%"),
    ).fetchall()
    temps = [r["temperature_c"] for r in rows if r["temperature_c"] is not None]
    if not temps:
        # Fall back to the current observation if no forecast rows for today
        cur = conn.execute(
            """SELECT temperature_c FROM weather_current
               WHERE town_id = ? ORDER BY fetched_at DESC LIMIT 1""",
            (town_id,),
        ).fetchone()
        return cur["temperature_c"] if cur else None
    return round(max(temps), 1)


def historical_comparison(conn, town_id: str) -> HistoricalComparison:
    """Compare today's forecast max to the stored 10-year normal for this date."""
    today = dt.date.today()
    forecast_max = _forecast_max_for_today(conn, town_id)

    base = conn.execute(
        """SELECT normal_tmax_c, years_used FROM weather_historical
           WHERE town_id = ? AND month = ? AND day = ?""",
        (town_id, today.month, today.day),
    ).fetchone()

    if base is None:
        return HistoricalComparison(
            town_id, forecast_max, None, None, False,
            "No historical baseline available for this date. "
            "Run refresh_historical.py (or seed_mock_historical.py).",
        )

    normal = base["normal_tmax_c"]
    is_mock = (base["years_used"] == 0)

    if forecast_max is None or normal is None:
        return HistoricalComparison(
            town_id, forecast_max, normal, None, is_mock,
            "Not enough data to compare against normal.",
        )

    anomaly = round(forecast_max - normal, 1)
    if anomaly >= 0:
        direction = "above"
    else:
        direction = "below"
        anomaly = abs(anomaly)

    mock_note = " (baseline is mock data)" if is_mock else ""
    summary = (
        f"Today's forecast high is {forecast_max:.0f}\u00b0C. "
        f"The {base['years_used'] or '~10'}-year average for this date is "
        f"{normal:.0f}\u00b0C \u2014 that is {anomaly:.0f}\u00b0C {direction} "
        f"normal{mock_note}."
    )
    # restore sign for the stored anomaly
    signed_anomaly = round(forecast_max - normal, 1)
    return HistoricalComparison(
        town_id, forecast_max, normal, signed_anomaly, is_mock, summary
    )


# ---------------------------------------------------------------------------
# Town prioritisation ranking
# ---------------------------------------------------------------------------

@dataclass
class RankedTown:
    priority: int
    town_id: str
    town_name: str
    risk_score: float
    risk_band: dict
    heat_index_c: float
    estimated_exposed_population: int

    def as_dict(self) -> dict:
        return {
            "priority": self.priority,
            "town_id": self.town_id,
            "town_name": self.town_name,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "heat_index_c": self.heat_index_c,
            "estimated_exposed_population": self.estimated_exposed_population,
        }


def _current_weather(conn, town_id: str):
    return conn.execute(
        """SELECT * FROM weather_current WHERE town_id = ?
           ORDER BY fetched_at DESC LIMIT 1""",
        (town_id,),
    ).fetchone()


def rank_towns(conn) -> list[RankedTown]:
    """
    Score every town by current heat risk and return them ranked, highest risk
    first. This is the ordered action list for health authorities.
    """
    towns = conn.execute("SELECT * FROM towns").fetchall()
    scored = []

    for t in towns:
        weather = _current_weather(conn, t["id"])
        if weather is None:
            continue
        result = calculate_heat_risk(
            temperature_c=weather["temperature_c"],
            humidity_pct=weather["humidity_pct"],
            population_density=t["population_density"] or 0.0,
            vegetation_deficit=t["vegetation_deficit"] or 0.0,
        )
        exposure_factor = min(1.0, max(0.0, (result.score - 25) / 75.0))
        exposed = int((t["population"] or 0) * exposure_factor)
        scored.append((result, t, exposed))

    # Sort by score descending, then by exposed population descending
    scored.sort(key=lambda x: (x[0].score, x[2]), reverse=True)

    ranked = []
    for i, (result, t, exposed) in enumerate(scored, start=1):
        ranked.append(RankedTown(
            priority=i,
            town_id=t["id"],
            town_name=t["name"],
            risk_score=result.score,
            risk_band=result.band,
            heat_index_c=result.heat_index_c,
            estimated_exposed_population=exposed,
        ))
    return ranked
