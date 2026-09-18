"""
heat_index.py
=============

Heat index ("feels like" temperature) using the Rothfusz regression equation,
the same formula used by the US National Weather Service (NWS).

The Rothfusz equation is defined in Fahrenheit. We accept Celsius inputs,
convert internally, and return Celsius.

Reference: Lans P. Rothfusz, "The Heat Index Equation" (NWS, 1990).
This is a published, non-proprietary meteorological formula.

WHY WE USE THIS (and not a black-box model)
--------------------------------------------
The heat index is a transparent, internationally recognised formula. A health
official can verify exactly how "feels-like 47C" was derived. This supports our
project's core principle: explainable, auditable risk over opaque prediction.
"""

from __future__ import annotations


def c_to_f(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0


def f_to_c(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * 5.0 / 9.0


def heat_index_celsius(temp_c: float, humidity_pct: float) -> float:
    """
    Compute the heat index in Celsius from air temperature (C) and relative
    humidity (%), using the NWS Rothfusz regression with the standard
    low-humidity and high-humidity adjustments.

    For temperatures below ~27C (80F) the heat index is approximately equal to
    the air temperature, so we return the air temperature in that regime (this
    matches NWS practice).
    """
    t = c_to_f(temp_c)
    rh = max(0.0, min(100.0, humidity_pct))

    # Simple formula for cooler conditions (NWS uses this below 80F)
    if t < 80.0:
        hi = 0.5 * (t + 61.0 + ((t - 68.0) * 1.2) + (rh * 0.094))
        # Average with air temp per NWS guidance
        hi = (hi + t) / 2.0
        return round(f_to_c(hi), 1)

    # Rothfusz regression (valid roughly for t >= 80F)
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * rh
        - 0.22475541 * t * rh
        - 0.00683783 * t * t
        - 0.05481717 * rh * rh
        + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh
        - 0.00000199 * t * t * rh * rh
    )

    # Low-humidity adjustment
    if rh < 13.0 and 80.0 <= t <= 112.0:
        adjustment = ((13.0 - rh) / 4.0) * ((17.0 - abs(t - 95.0)) / 17.0) ** 0.5
        hi -= adjustment

    # High-humidity adjustment
    if rh > 85.0 and 80.0 <= t <= 87.0:
        adjustment = ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
        hi += adjustment

    return round(f_to_c(hi), 1)


def heat_index_category(hi_c: float) -> dict:
    """
    Map a heat index (Celsius) to an NWS-style caution category.
    Thresholds are the NWS heat index categories converted to Celsius.
    """
    if hi_c < 27:
        return {"level": "none", "label": "No risk", "color": "#6FBF73"}
    if hi_c < 32:
        return {"level": "caution", "label": "Caution", "color": "#E8B339"}
    if hi_c < 41:
        return {"level": "extreme_caution", "label": "Extreme Caution", "color": "#E0793A"}
    if hi_c < 54:
        return {"level": "danger", "label": "Danger", "color": "#D34B4B"}
    return {"level": "extreme_danger", "label": "Extreme Danger", "color": "#8C4A6B"}


if __name__ == "__main__":
    # Quick sanity checks against known-ish values
    samples = [
        (40, 40),  # hot & moderately humid
        (44, 25),  # very hot, dry (typical Lahore May)
        (35, 60),  # hot & humid (monsoon)
        (30, 50),
        (25, 40),
    ]
    print("temp_C  RH%   ->  HeatIndex_C   category")
    for t, rh in samples:
        hi = heat_index_celsius(t, rh)
        cat = heat_index_category(hi)
        print(f"  {t:>4}   {rh:>3}   ->    {hi:>6}      {cat['label']}")
