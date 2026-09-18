"""
situation_report.py
===================

Generates a plain-language "situation report" (SITREP) for a tehsil - a short,
copy-paste-ready operational brief a health official can drop into WhatsApp,
SMS, or an email to their field team.

It assembles data the system already computes:
  - current heat-risk band + feels-like temperature
  - the soonest forecast escalation (from the 72h forecast)
  - estimated exposed population
  - a concrete recommended action

The point is to turn the dashboard's numbers into something a human can *act on*
and *forward* without interpretation. This is the "operational" layer on top of
the analytics.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from backend.app.services.forecast import forecast_risk_series
from backend.app.services.heat_intelligence import historical_comparison
from backend.app.services.risk_engine import calculate_heat_risk


@dataclass
class SituationReport:
    town_id: str
    town_name: str
    generated_at: str
    headline: str
    body: str            # the copy-paste brief (plain text)
    sms_short: str       # a <=160-char version for SMS

    def as_dict(self) -> dict:
        return {
            "town_id": self.town_id,
            "town_name": self.town_name,
            "generated_at": self.generated_at,
            "headline": self.headline,
            "body": self.body,
            "sms_short": self.sms_short,
        }


def _current(conn, town_id: str):
    return conn.execute(
        """SELECT * FROM weather_current WHERE town_id = ?
           ORDER BY fetched_at DESC LIMIT 1""",
        (town_id,),
    ).fetchone()


def _soonest_escalation(conn, town_id: str, current_score: float):
    """
    Find the first forecast hour where the risk band gets WORSE than now.
    Returns (hours_until, band_label, heat_index) or None.
    """
    series = forecast_risk_series(conn, town_id)
    now = dt.datetime.now()
    # thresholds that define a "worse" band boundary
    def band_rank(score):
        if score <= 25: return 0
        if score <= 50: return 1
        if score <= 75: return 2
        return 3
    current_rank = band_rank(current_score)
    for p in series:
        if band_rank(p.risk_score) > current_rank:
            try:
                ft = dt.datetime.strptime(p.time[:16], "%Y-%m-%dT%H:%M")
            except ValueError:
                continue
            hrs = max(0, round((ft - now).total_seconds() / 3600))
            return hrs, p.band["label"], p.heat_index_c
    return None


def _exposure(town_row, score: float) -> int:
    factor = min(1.0, max(0.0, (score - 25) / 75.0))
    return int((town_row["population"] or 0) * factor)


def _action_for(band_label: str, name: str) -> str:
    b = band_label.lower()
    if b == "critical":
        return (f"Deploy cooling centres, ORS supplies and outreach teams to "
                f"{name} now; prioritise elderly and outdoor workers.")
    if b == "high":
        return (f"Pre-position cooling-centre resources for {name} and alert "
                f"local health facilities.")
    if b == "moderate":
        return f"Issue a public heat advisory for {name} and monitor."
    return f"Routine monitoring for {name}."


def build_situation_report(conn, town_id: str) -> SituationReport | None:
    town = conn.execute("SELECT * FROM towns WHERE id = ?", (town_id,)).fetchone()
    if town is None:
        return None

    weather = _current(conn, town_id)
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    if weather is None:
        body = (f"{town['name']}: no current weather data available. "
                f"Run the data refresh before issuing a report.")
        return SituationReport(
            town_id, town["name"], now_str,
            headline=f"{town['name']} — no data",
            body=body, sms_short=body[:160],
        )

    result = calculate_heat_risk(
        temperature_c=weather["temperature_c"],
        humidity_pct=weather["humidity_pct"],
        population_density=town["population_density"] or 0.0,
        vegetation_deficit=town["vegetation_deficit"] or 0.0,
    )
    exposed = _exposure(town, result.score)
    band = result.band["label"]

    # forecast escalation
    escalation = _soonest_escalation(conn, town_id, result.score)
    if escalation:
        hrs, next_band, next_hi = escalation
        when = "within the hour" if hrs == 0 else f"in ~{hrs}h"
        escalation_line = (f"Forecast: expected to reach {next_band} {when} "
                           f"(feels-like {next_hi:.0f}\u00b0C).")
    else:
        escalation_line = "Forecast: no escalation beyond current level in the next 72h."

    # historical context
    hist = historical_comparison(conn, town_id)
    if hist.anomaly_c is not None and hist.normal_max_c is not None:
        sign = "+" if hist.anomaly_c >= 0 else ""
        hist_line = (f"Vs normal: today's forecast high is {sign}{hist.anomaly_c:.0f}"
                     f"\u00b0C vs the 10-year average.")
    else:
        hist_line = ""

    action = _action_for(band, town["name"])

    # Assemble the copy-paste body
    lines = [
        f"HEAT SITREP — {town['name']}  ({now_str})",
        f"Current risk: {band} (score {result.score:.0f}/100), "
        f"feels-like {result.heat_index_c:.0f}\u00b0C.",
        escalation_line,
    ]
    if hist_line:
        lines.append(hist_line)
    lines.append(f"Exposure: ~{exposed:,} residents at risk "
                 f"(of {town['population']:,}).")
    lines.append(f"ACTION: {action}")
    lines.append("— HoshiyarLahore (decision-support, not an official advisory)")
    body = "\n".join(lines)

    headline = f"{town['name']}: {band} heat — {action.split(';')[0]}"

    # SMS short version (compact, <=160 chars, no mid-word truncation)
    exposed_k = f"{exposed // 1000}k" if exposed >= 1000 else str(exposed)
    if escalation:
        hrs, next_band, _ = escalation
        esc = f"->{next_band} ~{hrs}h" if hrs > 0 else f"->{next_band} now"
    else:
        esc = "stable 72h"
    tail = " Act: cooling centres+ORS now." if band.lower() == "critical" else ""
    sms_short = (f"HEAT {band.upper()} {town['name']}: feels "
                 f"{result.heat_index_c:.0f}C, ~{exposed_k} exposed, {esc}.{tail}")
    if len(sms_short) > 160:
        sms_short = sms_short[:157].rsplit(" ", 1)[0] + "..."

    return SituationReport(
        town_id=town_id,
        town_name=town["name"],
        generated_at=now_str,
        headline=headline,
        body=body,
        sms_short=sms_short,
    )
