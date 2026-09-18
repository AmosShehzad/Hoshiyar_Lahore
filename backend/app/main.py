"""
main.py
=======

FastAPI application for HoshiyarLahore.

Endpoints
---------
GET /                       Health / info
GET /api/towns              All towns with current heat risk + geometry
GET /api/towns/{town_id}    Single town detail (risk, weather, attribution,
                            + Day 2 historical comparison)
GET /api/alerts             Active alerts derived from current risk scores
GET /api/overview           Lahore-wide summary
GET /api/ranking            (Day 2) Prioritised town action list for authorities

Run locally:
    uvicorn backend.app.main:app --reload --port 8000

Then open http://localhost:8000/docs for interactive API docs.

NOTE: Forecast-risk endpoints (/api/towns/{id}/forecast) are added on Day 3
per the build plan.
"""

from __future__ import annotations

import datetime as dt
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.database import get_connection
from backend.app.services.risk_engine import calculate_heat_risk, explain
from backend.app.services.heat_intelligence import (
    historical_comparison,
    rank_towns,
)
from backend.app.services.forecast import (
    forecast_risk_series,
    forecast_daily_peaks,
    predictive_alerts,
)
from backend.app.services.situation_report import build_situation_report
from backend.app.scheduler import (
    start_scheduler,
    stop_scheduler,
    refresh_status,
    trigger_refresh_now,
)
# Note: ensure_fresh_weather (request-triggered auto-refresh) is NOT wired in
# right now - superseded by a manual "Refresh Temperatures" button on the
# frontend (POST /api/refresh below) for more predictable, judge-demo-friendly
# control. The mechanism is still fully implemented and tested in
# scheduler.py, ready to re-enable (import it and add
# `Depends(ensure_fresh_weather)` back to the read endpoints) once the
# backend runs on a paid, always-on tier where its tradeoffs make more sense.

app = FastAPI(
    title="HoshiyarLahore API",
    description="Heatwave Early Warning for Lahore - tehsil-level heat risk.",
    version="0.5.0",
)

# Path to the data/geojson directory (main.py is at backend/app/main.py)
REPO_ROOT_DATA = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "geojson")
)

# CORS: allow the Next.js dev server and deployed frontend to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production; fine for a hackathon MVP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup():
    """Start the auto-refresh background scheduler (see backend/app/scheduler.py).
    Requires the backend to run as a persistent process - see that module's
    docstring for the deployment implication (Render/Railway, not serverless)."""
    start_scheduler()


@app.on_event("shutdown")
def _on_shutdown():
    stop_scheduler()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_weather_for(conn, town_id: str):
    """Return the most recent current-weather row for a town, or None."""
    return conn.execute(
        """SELECT * FROM weather_current
           WHERE town_id = ?
           ORDER BY fetched_at DESC LIMIT 1""",
        (town_id,),
    ).fetchone()


def _town_risk(conn, town_row) -> dict:
    """Compute the current heat-risk result for a town row (or None weather)."""
    weather = _current_weather_for(conn, town_row["id"])
    if weather is None:
        return {
            "id": town_row["id"],
            "name": town_row["name"],
            "name_ur": town_row["name_ur"],
            "population": town_row["population"],
            "has_weather": False,
            "message": "No weather data. Run refresh_weather.py or seed_mock_weather.py.",
        }

    result = calculate_heat_risk(
        temperature_c=weather["temperature_c"],
        humidity_pct=weather["humidity_pct"],
        population_density=town_row["population_density"] or 0.0,
        vegetation_deficit=town_row["vegetation_deficit"] or 0.0,
    )

    # Estimate exposed population: population scaled by how far into "high" the
    # score is. This is a simple, honest exposure proxy (documented as such).
    exposure_factor = min(1.0, max(0.0, (result.score - 25) / 75.0))
    exposed = int((town_row["population"] or 0) * exposure_factor)

    return {
        "id": town_row["id"],
        "name": town_row["name"],
        "name_ur": town_row["name_ur"],
        "population": town_row["population"],
        "population_density": town_row["population_density"],
        "vegetation_deficit": town_row["vegetation_deficit"],
        "has_weather": True,
        "observed_at": weather["observed_at"],
        "temperature_c": weather["temperature_c"],
        "humidity_pct": weather["humidity_pct"],
        "heat_index_c": result.heat_index_c,
        "risk_score": result.score,
        "risk_band": result.band,
        "attribution_pct": result.attribution_pct,
        "contributions": result.contributions,
        "estimated_exposed_population": exposed,
        "explanation": explain(result, town_row["name"]),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "app": "HoshiyarLahore API",
        "version": app.version,
        "endpoints": ["/api/towns", "/api/towns/{id}", "/api/towns/{id}/forecast",
                      "/api/towns/{id}/sitrep", "/api/alerts",
                      "/api/predictive-alerts", "/api/ranking",
                      "/api/cooling-centres", "/api/overview",
                      "/api/status", "/api/refresh"],
        "docs": "/docs",
    }


@app.get("/api/towns")
def list_towns():
    """All towns with current heat risk and geometry (for the map)."""
    conn = get_connection()
    try:
        towns = conn.execute("SELECT * FROM towns ORDER BY name").fetchall()
        features = []
        for t in towns:
            risk = _town_risk(conn, t)
            geometry = json.loads(t["geometry_geojson"]) if t["geometry_geojson"] else None
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": risk,
            })
        return {"type": "FeatureCollection", "features": features}
    finally:
        conn.close()


@app.get("/api/towns/{town_id}")
def town_detail(town_id: str):
    """Full detail for a single town."""
    conn = get_connection()
    try:
        t = conn.execute("SELECT * FROM towns WHERE id = ?", (town_id,)).fetchone()
        if t is None:
            raise HTTPException(status_code=404, detail=f"Town '{town_id}' not found")
        risk = _town_risk(conn, t)
        risk["area_km2"] = t["area_km2"]
        risk["notes"] = t["notes"]
        risk["verified"] = bool(t["verified"])
        risk["geometry"] = json.loads(t["geometry_geojson"]) if t["geometry_geojson"] else None
        # Day 2: historical comparison ("X degrees above normal")
        risk["historical"] = historical_comparison(conn, town_id).as_dict()
        return risk
    finally:
        conn.close()


@app.get("/api/towns/{town_id}/forecast")
def town_forecast(town_id: str, hours: int = 72):
    """
    (Day 3) 72-hour hourly heat-risk forecast for a tehsil, plus a per-day peak
    summary. Each hour carries its own risk score and band so the frontend can
    plot a timeline.
    """
    conn = get_connection()
    try:
        t = conn.execute("SELECT id, name FROM towns WHERE id = ?", (town_id,)).fetchone()
        if t is None:
            raise HTTPException(status_code=404, detail=f"Town '{town_id}' not found")
        series = forecast_risk_series(conn, town_id, hours=hours)
        if not series:
            return {
                "town_id": town_id,
                "town_name": t["name"],
                "has_forecast": False,
                "message": "No forecast data. Run refresh_weather.py or seed_mock_weather.py.",
                "hourly": [],
                "daily_peaks": [],
            }
        return {
            "town_id": town_id,
            "town_name": t["name"],
            "has_forecast": True,
            "hours": len(series),
            "hourly": [p.as_dict() for p in series],
            "daily_peaks": forecast_daily_peaks(series),
        }
    finally:
        conn.close()


@app.get("/api/towns/{town_id}/sitrep")
def town_sitrep(town_id: str):
    """
    Operational situation report for a tehsil - a copy-paste-ready brief for
    health officials (WhatsApp/SMS/email), assembled from current risk, forecast
    escalation, exposure, and a recommended action.
    """
    conn = get_connection()
    try:
        report = build_situation_report(conn, town_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"Town '{town_id}' not found")
        return report.as_dict()
    finally:
        conn.close()


@app.get("/api/predictive-alerts")
def predictive_alerts_endpoint(threshold: str = "high"):
    """
    (Day 3) Lead-time warnings: for each tehsil, the first forecast hour it is
    expected to cross into a dangerous band, e.g. "Lahore City expected to reach
    CRITICAL heat risk in 36 hours." threshold = "high" (>50) or "critical" (>75).
    """
    conn = get_connection()
    try:
        alerts = predictive_alerts(conn, threshold=threshold)
        return {
            "count": len(alerts),
            "threshold": threshold,
            "generated_for": "Punjab Health Department / district health officers",
            "alerts": [a.as_dict() for a in alerts],
        }
    finally:
        conn.close()


@app.get("/api/alerts")
def alerts():
    """
    Active alerts derived from current risk scores.
    Alert levels (Day 1 rules):
        Critical : risk_score > 75
        Warning  : risk_score > 60
        Advisory : risk_score > 45
    """
    conn = get_connection()
    try:
        towns = conn.execute("SELECT * FROM towns").fetchall()
        active = []
        for t in towns:
            risk = _town_risk(conn, t)
            if not risk.get("has_weather"):
                continue
            score = risk["risk_score"]
            level = None
            if score > 75:
                level = "critical"
            elif score > 60:
                level = "warning"
            elif score > 45:
                level = "advisory"
            if level:
                active.append({
                    "town_id": t["id"],
                    "town_name": t["name"],
                    "level": level,
                    "risk_score": score,
                    "heat_index_c": risk["heat_index_c"],
                    "estimated_exposed_population": risk["estimated_exposed_population"],
                    "message": _alert_message(level, t["name"], risk),
                    "recommended_action": _recommended_action(level, t["name"]),
                })
        # Sort by score, highest first
        active.sort(key=lambda a: a["risk_score"], reverse=True)
        return {"count": len(active), "alerts": active}
    finally:
        conn.close()


@app.get("/api/ranking")
def ranking():
    """
    (Day 2) Prioritised town action list for health authorities: every town
    scored and ordered highest-risk first, so officials know where to deploy
    resources in order.
    """
    conn = get_connection()
    try:
        ranked = rank_towns(conn)
        return {
            "count": len(ranked),
            "generated_for": "Punjab Health Department / district health officers",
            "ranking": [r.as_dict() for r in ranked],
        }
    finally:
        conn.close()


@app.get("/api/cooling-centres")
def cooling_centres():
    """
    Candidate cooling-centre locations (hospitals, parks, large venues) as a
    GeoJSON FeatureCollection, for overlaying on the map near high-risk tehsils.
    These are candidates for placement, not officially designated centres.
    """
    path = os.path.join(REPO_ROOT_DATA, "cooling_centres.geojson")
    if not os.path.exists(path):
        return {"type": "FeatureCollection", "features": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # strip private _meta if present
    data.pop("_meta", None)
    return data


@app.get("/api/status")
def status():
    """
    Data freshness and auto-refresh status - lets the dashboard show honestly
    how current the data is (e.g. "updated 12 minutes ago") and whether it's
    live Open-Meteo data or offline mock/seed data.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT fetched_at, observed_at FROM weather_current
               ORDER BY fetched_at DESC LIMIT 1"""
        ).fetchone()
        hist = conn.execute(
            "SELECT MAX(years_used) AS y FROM weather_historical"
        ).fetchone()

        is_mock_weather = bool(cur and str(cur["observed_at"]).startswith("MOCK"))
        is_mock_historical = bool(hist and (hist["y"] or 0) == 0)

        weather_age_minutes = None
        if cur and cur["fetched_at"]:
            try:
                fetched = dt.datetime.fromisoformat(cur["fetched_at"])
                weather_age_minutes = round(
                    (dt.datetime.now() - fetched).total_seconds() / 60, 1
                )
            except ValueError:
                pass

        return {
            "weather_fetched_at": cur["fetched_at"] if cur else None,
            "weather_age_minutes": weather_age_minutes,
            "is_mock_weather": is_mock_weather,
            "is_mock_historical": is_mock_historical,
            "scheduler": refresh_status(),
        }
    finally:
        conn.close()


@app.post("/api/refresh")
def force_refresh():
    """
    Manually trigger an immediate weather refresh (does not wait for the
    scheduled interval). Useful for a demo moment ('watch it update live') or
    right before recording/presenting. Fetches live Open-Meteo data - requires
    internet access; may take a few seconds.
    """
    return trigger_refresh_now()


@app.get("/api/overview")
def overview():
    """Lahore-wide summary for the dashboard header."""
    conn = get_connection()
    try:
        towns = conn.execute("SELECT * FROM towns").fetchall()
        risks = [_town_risk(conn, t) for t in towns]
        with_weather = [r for r in risks if r.get("has_weather")]

        if not with_weather:
            return {
                "has_weather": False,
                "message": "No weather data loaded. Run a refresh/seed script.",
                "town_count": len(towns),
            }

        band_counts = {"low": 0, "moderate": 0, "high": 0, "critical": 0}
        for r in with_weather:
            band_counts[r["risk_band"]["level"]] += 1

        avg_score = round(
            sum(r["risk_score"] for r in with_weather) / len(with_weather), 1
        )
        total_exposed = sum(r["estimated_exposed_population"] for r in with_weather)

        return {
            "has_weather": True,
            "city": "Lahore",
            "town_count": len(towns),
            "average_risk_score": avg_score,
            "average_risk_band": _band_for_score(avg_score),
            "band_counts": band_counts,
            "high_or_critical_towns": band_counts["high"] + band_counts["critical"],
            "total_estimated_exposed": total_exposed,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Alert text helpers
# ---------------------------------------------------------------------------

def _alert_message(level: str, town_name: str, risk: dict) -> str:
    hi = risk["heat_index_c"]
    if level == "critical":
        return (f"CRITICAL heat risk in {town_name}. Feels-like {hi:.0f}\u00b0C. "
                f"Vulnerable residents at serious risk.")
    if level == "warning":
        return (f"Heat WARNING for {town_name}. Feels-like {hi:.0f}\u00b0C. "
                f"Elevated risk for vulnerable groups.")
    return (f"Heat ADVISORY for {town_name}. Feels-like {hi:.0f}\u00b0C. "
            f"Monitor conditions.")


def _recommended_action(level: str, town_name: str) -> str:
    if level == "critical":
        return (f"Prioritise {town_name} for cooling centres, ORS supplies, and "
                f"outreach to elderly and outdoor workers now.")
    if level == "warning":
        return (f"Pre-position cooling-centre resources for {town_name} and alert "
                f"local health facilities.")
    return f"Issue public heat advisory for {town_name}; monitor over next 24h."


def _band_for_score(score: float) -> dict:
    from backend.app.services.risk_engine import risk_band
    return risk_band(score)