"""
Tests for the heat index and risk engine.

Run with:
    python -m pytest backend/tests/ -v
or without pytest:
    python backend/tests/test_risk_engine.py
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.services.heat_index import heat_index_celsius, heat_index_category
from backend.app.services.risk_engine import (
    WEIGHTS,
    calculate_heat_risk,
    risk_band,
)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_heat_index_hot_humid_exceeds_air_temp():
    # In hot, humid conditions the heat index should be higher than air temp
    hi = heat_index_celsius(35, 60)
    assert hi > 35


def test_heat_index_mild_returns_near_air_temp():
    # Below 27C, heat index ~= air temperature
    hi = heat_index_celsius(22, 40)
    assert abs(hi - 22) < 5


def test_heat_index_category_bands():
    assert heat_index_category(20)["level"] == "none"
    assert heat_index_category(30)["level"] == "caution"
    assert heat_index_category(38)["level"] == "extreme_caution"
    assert heat_index_category(48)["level"] == "danger"
    assert heat_index_category(60)["level"] == "extreme_danger"


def test_risk_band_thresholds():
    assert risk_band(10)["level"] == "low"
    assert risk_band(40)["level"] == "moderate"
    assert risk_band(65)["level"] == "high"
    assert risk_band(90)["level"] == "critical"


def test_score_in_range():
    r = calculate_heat_risk(45, 20, 30000, 0.8)
    assert 0 <= r.score <= 100


def test_contributions_sum_to_score():
    r = calculate_heat_risk(44, 25, 25000, 0.7)
    assert abs(sum(r.contributions.values()) - r.score) < 0.5


def test_attribution_sums_to_100():
    r = calculate_heat_risk(44, 25, 25000, 0.7)
    total = sum(r.attribution_pct.values())
    # allow small rounding error
    assert abs(total - 100.0) < 1.0


def test_same_weather_higher_density_higher_score():
    # Core value proposition: identical weather, denser town = higher risk
    low_density = calculate_heat_risk(45, 20, 8000, 0.6)
    high_density = calculate_heat_risk(45, 20, 38000, 0.6)
    assert high_density.score > low_density.score


def test_same_weather_lower_vegetation_higher_score():
    greener = calculate_heat_risk(45, 20, 20000, 0.4)
    barren = calculate_heat_risk(45, 20, 20000, 0.9)
    assert barren.score > greener.score


def test_hotter_weather_higher_score():
    mild = calculate_heat_risk(36, 30, 20000, 0.7)
    extreme = calculate_heat_risk(47, 30, 20000, 0.7)
    assert extreme.score > mild.score


def _run_all():
    """Minimal runner so tests work even without pytest installed."""
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    print("Running risk engine tests...")
    ok = _run_all()
    sys.exit(0 if ok else 1)
