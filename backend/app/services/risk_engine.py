"""
risk_engine.py
==============

The heat risk scoring engine for HoshiyarLahore.

DESIGN PRINCIPLE
----------------
This is an INTERPRETABLE, weighted composite model - NOT a black box. Every
score can be decomposed into the exact contribution of each factor. This is a
deliberate choice: health authorities must be able to see WHY a town is flagged
before they act on it. (See docs/METHODOLOGY.md.)

THE SCORE
---------
Heat Risk Score is a 0-100 number combining four normalised sub-factors:

    Factor                     Weight   Rationale
    -----------------------    ------   -----------------------------------
    Heat index severity         40%     How dangerous the "feels-like" temp is
    Forecast max temperature    25%     Absolute air temperature stress
    Population density          20%     More people exposed = higher impact
    Vegetation deficit          15%     Built-up, low-green areas trap heat

Each sub-factor is normalised to 0-100 using documented thresholds, then
combined with the weights above. The weights are an initial, defensible MVP
configuration - NOT a universally established scientific constant. They can be
tuned as historical outcome data becomes available.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.heat_index import heat_index_celsius

# ---------------------------------------------------------------------------
# Weights (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "heat_index": 0.40,
    "temperature": 0.25,
    "population_density": 0.20,
    "vegetation_deficit": 0.15,
}

# ---------------------------------------------------------------------------
# Normalisation thresholds
# ---------------------------------------------------------------------------
# Each function maps a raw value to 0..100. These anchor points are chosen from
# heat-health literature and Lahore's climate (summer highs regularly 40-48C).

def _norm_heat_index(hi_c: float) -> float:
    """
    Normalise heat index (C) to 0..100.
    Anchors: 27C -> 0 (no risk), 54C+ -> 100 (extreme danger).
    Linear in between.
    """
    lo, hi = 27.0, 54.0
    return _clamp((hi_c - lo) / (hi - lo) * 100.0)


def _norm_temperature(temp_c: float) -> float:
    """
    Normalise air temperature (C) to 0..100.
    Anchors: 30C -> 0, 50C -> 100.
    """
    lo, hi = 30.0, 50.0
    return _clamp((temp_c - lo) / (hi - lo) * 100.0)


def _norm_density(people_per_km2: float) -> float:
    """
    Normalise population density to 0..100.
    Anchors: 2,000/km2 -> 0, 40,000/km2 -> 100.
    Lahore town densities range widely; dense old-city areas approach 40k.
    """
    lo, hi = 2000.0, 40000.0
    return _clamp((people_per_km2 - lo) / (hi - lo) * 100.0)


def _norm_vegetation_deficit(deficit: float) -> float:
    """
    Vegetation deficit is already a 0..1 proxy (1 = very built-up/low green).
    Map directly to 0..100.
    """
    return _clamp(deficit * 100.0)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Severity banding
# ---------------------------------------------------------------------------

def risk_band(score: float) -> dict:
    """Map a 0..100 risk score to a level, label, and color."""
    if score <= 25:
        return {"level": "low", "label": "Low", "color": "#6FBF73"}
    if score <= 50:
        return {"level": "moderate", "label": "Moderate", "color": "#E8B339"}
    if score <= 75:
        return {"level": "high", "label": "High", "color": "#E0793A"}
    return {"level": "critical", "label": "Critical", "color": "#D34B4B"}


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------

@dataclass
class HeatRiskResult:
    score: float
    band: dict
    heat_index_c: float
    contributions: dict          # factor -> points contributed (sum ~= score)
    attribution_pct: dict        # factor -> % of total score
    inputs: dict                 # echo of raw inputs used

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "band": self.band,
            "heat_index_c": self.heat_index_c,
            "contributions": self.contributions,
            "attribution_pct": self.attribution_pct,
            "inputs": self.inputs,
        }


def calculate_heat_risk(
    temperature_c: float,
    humidity_pct: float,
    population_density: float,
    vegetation_deficit: float,
) -> HeatRiskResult:
    """
    Compute the heat risk score (0..100) for a single town/observation, along
    with a full attribution breakdown.

    Returns a HeatRiskResult. The `contributions` dict tells you how many of the
    final points came from each factor; `attribution_pct` expresses the same as
    percentages (useful for the "why is this area at risk?" explanation).
    """
    hi_c = heat_index_celsius(temperature_c, humidity_pct)

    # Normalised sub-scores (each 0..100)
    n_hi = _norm_heat_index(hi_c)
    n_temp = _norm_temperature(temperature_c)
    n_density = _norm_density(population_density)
    n_veg = _norm_vegetation_deficit(vegetation_deficit)

    # Weighted contributions (each in "points" out of 100 total)
    contributions = {
        "heat_index": round(n_hi * WEIGHTS["heat_index"], 1),
        "temperature": round(n_temp * WEIGHTS["temperature"], 1),
        "population_density": round(n_density * WEIGHTS["population_density"], 1),
        "vegetation_deficit": round(n_veg * WEIGHTS["vegetation_deficit"], 1),
    }

    score = round(sum(contributions.values()), 1)

    # Attribution as percentage of the total score (guard divide-by-zero)
    total = sum(contributions.values())
    if total > 0:
        attribution_pct = {
            k: round(v / total * 100.0, 1) for k, v in contributions.items()
        }
    else:
        attribution_pct = {k: 0.0 for k in contributions}

    return HeatRiskResult(
        score=score,
        band=risk_band(score),
        heat_index_c=hi_c,
        contributions=contributions,
        attribution_pct=attribution_pct,
        inputs={
            "temperature_c": temperature_c,
            "humidity_pct": humidity_pct,
            "population_density": population_density,
            "vegetation_deficit": vegetation_deficit,
        },
    )


# Human-readable factor labels for the frontend / explanations
FACTOR_LABELS = {
    "heat_index": "Feels-like temperature (heat index)",
    "temperature": "Air temperature",
    "population_density": "Population density",
    "vegetation_deficit": "Low vegetation / built-up density",
}


def explain(result: HeatRiskResult, town_name: str = "This area") -> str:
    """
    Produce a plain-English explanation of why a town has its score, using the
    top contributing factors. This is the text a health officer reads.
    """
    band = result.band["label"].lower()
    # Sort factors by contribution, descending
    ranked = sorted(
        result.attribution_pct.items(), key=lambda kv: kv[1], reverse=True
    )
    top = ranked[:3]
    parts = [f"{FACTOR_LABELS[k]} ({pct:.0f}%)" for k, pct in top if pct > 0]
    drivers = ", ".join(parts)
    return (
        f"{town_name} has a {band} heat risk score of {result.score:.0f}/100. "
        f"The main drivers are: {drivers}. "
        f"The current feels-like temperature is about {result.heat_index_c:.0f}\u00b0C."
    )


if __name__ == "__main__":
    # Demonstration with three contrasting towns
    print("Heat risk demonstration\n" + "=" * 60)
    scenarios = [
        ("Dense old city, very hot dry day", 45, 20, 38000, 0.88),
        ("Greener planned area, same weather", 45, 20, 20000, 0.55),
        ("Peri-urban, milder", 38, 35, 7000, 0.45),
    ]
    for name, t, rh, dens, veg in scenarios:
        r = calculate_heat_risk(t, rh, dens, veg)
        print(f"\n{name}")
        print(f"  temp={t}C rh={rh}% density={dens} veg_deficit={veg}")
        print(f"  Heat index: {r.heat_index_c}C")
        print(f"  SCORE: {r.score}/100 ({r.band['label']})")
        print(f"  Contributions: {r.contributions}")
        print(f"  Attribution %: {r.attribution_pct}")
        print("  " + explain(r, name))
