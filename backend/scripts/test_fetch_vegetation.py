"""
Tests for fetch_vegetation.py's core geometry math.

Overpass (the live OSM data source) is unreachable from this test
environment, so these tests can't verify against real Lahore data - instead
they prove the AREA-INTERSECTION LOGIC ITSELF is correct using synthetic
polygons with hand-calculable expected answers. If this logic is right, it
will be right on real data too; if it's wrong, real data would just be
wrong in a way that's harder to notice.

Run with:
    python backend/scripts/test_fetch_vegetation.py
"""

import math
import os
import sys

from shapely.geometry import Polygon

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.scripts.fetch_vegetation import (  # noqa: E402
    compute_vegetation_deficit,
    to_local_xy,
    REF_LAT,
    REF_LON,
    M_PER_DEG_LAT,
    M_PER_DEG_LON,
)


def square(x0, y0, side):
    return Polygon([(x0, y0), (x0 + side, y0), (x0 + side, y0 + side), (x0, y0 + side)])


def test_no_green_space_gives_full_deficit():
    tehsil = square(0, 0, 10_000)  # 10km x 10km = 100 km^2
    result = compute_vegetation_deficit(tehsil, [])
    assert result["vegetation_fraction"] == 0.0
    assert result["vegetation_deficit"] == 1.0
    assert result["tehsil_area_km2"] == 100.0


def test_park_covering_exactly_a_quarter():
    tehsil = square(0, 0, 10_000)  # 100 km^2 total
    park = square(0, 0, 5_000)     # 25 km^2, fully inside, in one corner
    result = compute_vegetation_deficit(tehsil, [park])
    assert result["vegetation_fraction"] == 0.25, result
    assert result["vegetation_deficit"] == 0.75, result
    assert result["green_area_km2"] == 25.0, result


def test_park_entirely_outside_tehsil_contributes_nothing():
    tehsil = square(0, 0, 10_000)
    far_away_park = square(100_000, 100_000, 5_000)  # nowhere near the tehsil
    result = compute_vegetation_deficit(tehsil, [far_away_park])
    assert result["vegetation_fraction"] == 0.0, result
    assert result["vegetation_deficit"] == 1.0, result


def test_park_straddling_the_boundary_only_counts_the_overlapping_part():
    """
    A park that's half inside, half outside the tehsil must only contribute
    its INSIDE half - not its full area. This is the core correctness
    property of using real intersection instead of a naive point-in-polygon
    or "nearby" heuristic.
    """
    tehsil = square(0, 0, 10_000)  # 0..10000 in both x and y
    # A 4000x4000 park straddling the right edge: half inside (x: 8000-10000),
    # half outside (x: 10000-12000).
    straddling_park = square(8_000, 0, 4_000)
    result = compute_vegetation_deficit(tehsil, [straddling_park])
    # Only the inside half (2000 x 4000 = 8,000,000 m^2 = 8 km^2) should count,
    # not the full park (4000 x 4000 = 16 km^2).
    assert result["green_area_km2"] == 8.0, result
    assert abs(result["vegetation_fraction"] - 0.08) < 0.0001, result


def test_multiple_parks_sum_correctly():
    tehsil = square(0, 0, 10_000)  # 100 km^2
    park_a = square(0, 0, 3_000)      # 9 km^2
    park_b = square(5_000, 5_000, 2_000)  # 4 km^2, elsewhere, no overlap with A
    result = compute_vegetation_deficit(tehsil, [park_a, park_b])
    assert result["green_area_km2"] == 13.0, result
    assert abs(result["vegetation_fraction"] - 0.13) < 0.0001, result


def test_green_area_cannot_exceed_full_tehsil_even_if_park_is_bigger():
    tehsil = square(0, 0, 10_000)  # 100 km^2
    huge_park = square(-5_000, -5_000, 20_000)  # fully covers and extends past
    result = compute_vegetation_deficit(tehsil, [huge_park])
    assert result["vegetation_fraction"] == 1.0, result
    assert result["vegetation_deficit"] == 0.0, result


def test_local_projection_gives_sensible_real_world_scale():
    """
    Sanity-check the lon/lat -> local metres projection against the standard
    111.32 km/degree approximation, at Lahore's own reference point. A 0.01
    degree step in longitude at Lahore's latitude should be roughly
    111,320 * cos(31.5 deg) * 0.01 metres - about 949m - not, say, 1110m
    (which would mean the latitude-correction term was forgotten).
    """
    x0, y0 = to_local_xy(REF_LON, REF_LAT)
    x1, y1 = to_local_xy(REF_LON + 0.01, REF_LAT)
    dx = x1 - x0
    expected_dx = 111_320.0 * math.cos(math.radians(REF_LAT)) * 0.01
    assert abs(dx - expected_dx) < 0.01, (dx, expected_dx)

    # A 0.01 degree step in latitude should be ~1109.4m, with no
    # longitude-style cosine correction (latitude lines are evenly spaced).
    x2, y2 = to_local_xy(REF_LON, REF_LAT + 0.01)
    dy = y2 - y0
    assert abs(dy - 1109.4) < 0.5, dy


def test_parses_a_realistic_overpass_response():
    """
    Verifies green_polygons_from_overpass() correctly reconstructs a real
    polygon from the exact JSON shape Overpass's 'out geom' actually returns
    for a way - not a made-up simplified shape.
    """
    from backend.scripts.fetch_vegetation import green_polygons_from_overpass

    mock_response = {
        "elements": [
            {
                "type": "way",
                "id": 123456,
                "tags": {"leisure": "park", "name": "Jilani Park"},
                "geometry": [
                    {"lat": 31.560, "lon": 74.330},
                    {"lat": 31.560, "lon": 74.335},
                    {"lat": 31.565, "lon": 74.335},
                    {"lat": 31.565, "lon": 74.330},
                    {"lat": 31.560, "lon": 74.330},  # closed ring, as OSM sends it
                ],
            },
            {
                # A degenerate way (too few points) - must be skipped, not crash.
                "type": "way",
                "id": 999,
                "tags": {"landuse": "grass"},
                "geometry": [{"lat": 31.5, "lon": 74.3}],
            },
            {
                # A node (not a way) mixed into results - must be ignored.
                "type": "node",
                "id": 1,
                "lat": 31.5,
                "lon": 74.3,
            },
        ]
    }
    polys = green_polygons_from_overpass(mock_response)
    assert len(polys) == 1, f"expected exactly 1 valid polygon, got {len(polys)}"
    assert polys[0].area > 0


def _run_all():
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
    print("Testing fetch_vegetation.py geometry logic (synthetic data)...")
    ok = _run_all()
    sys.exit(0 if ok else 1)