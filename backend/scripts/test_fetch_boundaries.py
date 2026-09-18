"""
Tests for fetch_boundaries.py's polygon-assembly logic.

Overpass is unreachable from this test environment, so these can't verify
against real Lahore data - instead they prove the RING-STITCHING FIX itself
is correct, using a synthetic relation whose way segments are deliberately
given in SCRAMBLED order (mimicking how Overpass actually returns members -
not in any particular walking order around the boundary). This is exactly
the situation that broke the old naive-concatenation approach.

Run with:
    python backend/scripts/test_fetch_boundaries.py
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.scripts.fetch_boundaries import (  # noqa: E402
    build_polygon_from_relation,
    polygon_area_km2,
    to_local_xy,
)


def _square_way_geometry(lon0, lat0, lon1, lat1):
    return [{"lon": lon0, "lat": lat0}, {"lon": lon1, "lat": lat1}]


def test_scrambled_way_segments_stitch_into_a_correct_square():
    """
    A simple square boundary, split into 4 way segments (one per side), but
    given to the function in a SCRAMBLED, non-walking order - exactly what
    Overpass returns in practice. The old naive-concatenation code would
    have produced a self-crossing mess from this input; linemerge() must
    correctly reassemble the proper square regardless of input order.
    """
    lon0, lat0 = 74.30, 31.50
    lon1, lat1 = 74.31, 31.51

    top = _square_way_geometry(lon0, lat1, lon1, lat1)
    bottom = _square_way_geometry(lon0, lat0, lon1, lat0)
    right = _square_way_geometry(lon1, lat0, lon1, lat1)
    left = _square_way_geometry(lon0, lat0, lon0, lat1)

    osm_json = {
        "elements": [
            {
                "type": "relation",
                "id": 1,
                "members": [
                    {"type": "way", "ref": 101, "role": "outer"},  # top
                    {"type": "way", "ref": 102, "role": "outer"},  # bottom
                    {"type": "way", "ref": 103, "role": "outer"},  # right
                    {"type": "way", "ref": 104, "role": "outer"},  # left
                ],
            },
            {"type": "way", "id": 101, "geometry": top},
            {"type": "way", "id": 102, "geometry": bottom},
            {"type": "way", "id": 103, "geometry": right},
            {"type": "way", "id": 104, "geometry": left},
        ]
    }

    geom = build_polygon_from_relation(osm_json)
    assert geom is not None, "expected a valid polygon, got None"
    assert geom.is_valid, "assembled polygon must be valid (non-self-crossing)"

    area_km2 = polygon_area_km2(geom)
    x0, y0 = to_local_xy(lon0, lat0)
    x1, y1 = to_local_xy(lon1, lat1)
    expected_km2 = abs((x1 - x0) * (y1 - y0)) / 1_000_000
    assert abs(area_km2 - expected_km2) / expected_km2 < 0.01, (
        f"stitched polygon area {area_km2:.4f} km^2 doesn't match the "
        f"expected {expected_km2:.4f} km^2 - ring assembly is wrong"
    )


def test_no_relation_returns_none():
    osm_json = {"elements": [{"type": "way", "id": 1, "geometry": []}]}
    assert build_polygon_from_relation(osm_json) is None


def test_relation_with_no_matching_ways_returns_none():
    osm_json = {
        "elements": [
            {"type": "relation", "id": 1, "members": [
                {"type": "way", "ref": 999, "role": "outer"},
            ]},
        ]
    }
    assert build_polygon_from_relation(osm_json) is None


def test_degenerate_way_with_too_few_points_is_skipped_not_crashed():
    osm_json = {
        "elements": [
            {"type": "relation", "id": 1, "members": [
                {"type": "way", "ref": 1, "role": "outer"},
            ]},
            {"type": "way", "id": 1, "geometry": [{"lon": 74.3, "lat": 31.5}]},
        ]
    }
    assert build_polygon_from_relation(osm_json) is None


def test_polygon_area_km2_handles_multipolygon():
    from shapely.geometry import Polygon, MultiPolygon

    lon0, lat0 = 74.30, 31.50
    lon1, lat1 = 74.31, 31.51
    x0, y0 = to_local_xy(lon0, lat0)
    x1, y1 = to_local_xy(lon1, lat1)
    single_km2 = abs((x1 - x0) * (y1 - y0)) / 1_000_000

    square = Polygon([(lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1)])
    lon2, lat2, lon3, lat3 = 74.40, 31.60, 74.41, 31.61
    square2 = Polygon([(lon2, lat2), (lon3, lat2), (lon3, lat3), (lon2, lat3)])

    mp = MultiPolygon([square, square2])
    total = polygon_area_km2(mp)
    assert abs(total - 2 * single_km2) / (2 * single_km2) < 0.05, (total, single_km2)


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
    print("Testing fetch_boundaries.py ring-stitching logic (synthetic data)...")
    ok = _run_all()
    sys.exit(0 if ok else 1)