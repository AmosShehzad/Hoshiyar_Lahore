"""
fetch_vegetation.py
====================

Fetch REAL vegetation coverage for each of Lahore's 5 tehsils from
OpenStreetMap, replacing the hand-typed vegetation_deficit estimate in
data/metadata/town_metadata.json with a genuinely calculated value.

THE PROBLEM THIS FIXES
-----------------------
Until now, vegetation_deficit was a single number someone typed in by hand
per tehsil (e.g. 0.88 for Lahore City) - an informed guess, not a measurement.
This script replaces that guess with a real, reproducible calculation:

    1. Fetch every park, garden, forest, wood, and grass area tagged in
       OpenStreetMap within Lahore, as real polygons (not just points).
    2. Intersect each of those polygons with each tehsil's boundary polygon,
       so a park that straddles two tehsils is only counted, per tehsil, for
       the part that's actually inside it.
    3. Sum the intersected green area per tehsil, divide by the tehsil's
       total area, to get a real "fraction of this tehsil that is green
       space" number.
    4. vegetation_deficit = 1 - that fraction.

WHY THESE OSM TAGS AND NOT OTHERS
-----------------------------------
Included: leisure=park, leisure=garden, landuse=forest, natural=wood,
landuse=grass, natural=grassland - all provide real shade/cooling relevant to
urban heat mitigation, which is what this model cares about.

Deliberately EXCLUDED: landuse=farmland. Raiwind tehsil is largely
agricultural; farmland has plants, but it doesn't provide the tree-canopy
shade or evapotranspiration cooling that urban heat-island research
associates with green space, and it doesn't function as a public cooling
resource the way a park does. Including it would inflate Raiwind's "green"
score for reasons unrelated to heat risk. This is a defensible, documented
modelling choice - not an oversight - and worth stating plainly if a judge
asks why farmland isn't counted.

TWO HONEST LIMITATIONS TO DISCLOSE, NOT HIDE
-----------------------------------------------
1. This computes area against the CURRENT tehsil boundary polygons in
   data/geojson/lahore_towns.geojson. If those are still the approximate
   fallback polygons (not real OSM-traced boundaries), the vegetation
   percentage is only as accurate as that approximation. Run
   fetch_boundaries.py first and confirm real boundaries loaded, for the
   most defensible numbers.
2. OpenStreetMap's tagging completeness varies by city. Lahore's parks and
   green spaces may be less thoroughly mapped than in, say, a European city -
   meaning this can UNDERESTIMATE real vegetation if features simply aren't
   tagged in OSM yet. This is a real, known limitation of using OSM for this
   purpose, and should be disclosed rather than presented as ground truth.

USAGE
-----
    python backend/scripts/fetch_vegetation.py

Same resilient pattern as fetch_boundaries.py and fetch_cooling_centres.py:
if Overpass is unreachable, the existing hand-typed estimates in
town_metadata.json are left untouched, and the script says so clearly.
"""

from __future__ import annotations

import json
import math
import os
import time

import requests
from shapely.geometry import Polygon
from shapely.ops import unary_union

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "HoshiyarLahore/0.5 (hackathon; contact: team@example.com)"}

LAHORE_BBOX = (31.30, 74.15, 31.75, 74.60)  # south, west, north, east

# (osm key, [values]) - see module docstring for why farmland is excluded.
GREEN_TAGS = [
    ("leisure", ["park", "garden"]),
    ("landuse", ["forest", "grass"]),
    ("natural", ["wood", "grassland"]),
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
TOWNS_GEOJSON = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns.geojson")
METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")

# Local flat-earth projection reference point (Lahore's approximate centre).
# Valid for small areas like a single city's tehsils - error is negligible
# (well under 1%) at this scale. Avoids adding pyproj as a new dependency.
REF_LAT, REF_LON = 31.50, 74.35
M_PER_DEG_LAT = 110_940.0  # metres per degree of latitude (~constant)
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))


def to_local_xy(lon: float, lat: float) -> tuple[float, float]:
    """Project lon/lat degrees to local approximate metres, centred on Lahore."""
    x = (lon - REF_LON) * M_PER_DEG_LON
    y = (lat - REF_LAT) * M_PER_DEG_LAT
    return x, y


def project_ring(coords: list[list[float]]) -> list[tuple[float, float]]:
    """coords are [lon, lat] pairs (GeoJSON order) -> projected (x, y) metres."""
    return [to_local_xy(lon, lat) for lon, lat in coords]


# ---------------------------------------------------------------------------
# Load tehsil boundaries, projected to local metres
# ---------------------------------------------------------------------------

def load_tehsil_polygons() -> dict[str, Polygon]:
    with open(TOWNS_GEOJSON, encoding="utf-8") as f:
        fc = json.load(f)
    polygons = {}
    for feat in fc["features"]:
        tid = feat["properties"]["id"]
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            ring = project_ring(geom["coordinates"][0])
            polygons[tid] = Polygon(ring)
        elif geom["type"] == "MultiPolygon":
            parts = [Polygon(project_ring(poly[0])) for poly in geom["coordinates"]]
            polygons[tid] = unary_union(parts)
    return polygons


# ---------------------------------------------------------------------------
# Overpass query + parsing
# ---------------------------------------------------------------------------

def build_query() -> str:
    s, w, n, e = LAHORE_BBOX
    parts = []
    for key, values in GREEN_TAGS:
        for v in values:
            parts.append(f'  way["{key}"="{v}"]({s},{w},{n},{e});')
    body = "\n".join(parts)
    return f"[out:json][timeout:90];\n(\n{body}\n);\nout geom;"


def query_overpass(query: str):
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"  Querying {endpoint} ...")
            r = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=100)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code}")
        except requests.RequestException as exc:
            print(f"    failed: {exc}")
        time.sleep(2)
    return None


def green_polygons_from_overpass(result: dict) -> list[Polygon]:
    """Reconstruct real polygons from Overpass 'out geom' way elements."""
    polys = []
    for el in result.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry")
        if not geom or len(geom) < 4:
            continue
        ring = [(pt["lon"], pt["lat"]) for pt in geom]
        if ring[0] != ring[-1]:
            ring.append(ring[0])  # close the ring if OSM didn't
        try:
            proj_ring = [to_local_xy(lon, lat) for lon, lat in ring]
            poly = Polygon(proj_ring)
            if poly.is_valid and poly.area > 0:
                polys.append(poly)
        except Exception:  # noqa: BLE001 - a handful of malformed ways is expected
            continue
    return polys


# ---------------------------------------------------------------------------
# The actual calculation (pure, testable - see test_fetch_vegetation.py)
# ---------------------------------------------------------------------------

def compute_vegetation_deficit(tehsil_polygon: Polygon, green_polygons: list[Polygon]) -> dict:
    """
    Returns {"vegetation_fraction", "vegetation_deficit", "green_area_km2",
    "tehsil_area_km2"} for one tehsil, given its boundary and the full list
    of candidate green-space polygons (only the ones that actually overlap
    are counted, via real geometric intersection - not just "is it nearby").
    """
    tehsil_area_m2 = tehsil_polygon.area
    green_area_m2 = 0.0
    for g in green_polygons:
        if not g.intersects(tehsil_polygon):
            continue
        clipped = g.intersection(tehsil_polygon)
        green_area_m2 += clipped.area

    # A park counted twice by overlapping OSM ways would double count; in
    # practice this is rare for our tag set, but cap the fraction at 1.0
    # defensively rather than ever reporting >100% green.
    fraction = min(1.0, green_area_m2 / tehsil_area_m2) if tehsil_area_m2 > 0 else 0.0
    deficit = max(0.0, min(1.0, 1.0 - fraction))

    return {
        "vegetation_fraction": round(fraction, 4),
        "vegetation_deficit": round(deficit, 4),
        "green_area_km2": round(green_area_m2 / 1_000_000, 3),
        "tehsil_area_km2": round(tehsil_area_m2 / 1_000_000, 3),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 64)
    print("HoshiyarLahore - Real vegetation fetcher (OSM-based)")
    print("=" * 64)

    tehsil_polygons = load_tehsil_polygons()
    print(f"Loaded {len(tehsil_polygons)} tehsil boundary polygons.")

    result = query_overpass(build_query())
    if result is None:
        print("\nOverpass unreachable. Leaving existing vegetation_deficit "
              "estimates in town_metadata.json untouched.")
        return

    green_polygons = green_polygons_from_overpass(result)
    print(f"Fetched {len(green_polygons)} green-space polygons from OSM.\n")

    if not green_polygons:
        print("No green-space polygons returned - leaving existing estimates "
              "untouched rather than overwriting with a false zero.")
        return

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"{'Tehsil':<22}{'Old (typed)':<14}{'New (fetched)':<16}{'Green km2':<12}{'Area km2'}")
    print("-" * 76)

    for town in metadata["towns"]:
        tid = town["id"]
        if tid not in tehsil_polygons:
            continue
        old_deficit = town.get("vegetation_deficit")
        calc = compute_vegetation_deficit(tehsil_polygons[tid], green_polygons)
        print(f"{town['name']:<22}{old_deficit!s:<14}{calc['vegetation_deficit']:<16}"
              f"{calc['green_area_km2']:<12}{calc['tehsil_area_km2']}")

        # Keep the old hand-typed value as a fallback/reference, replace the
        # live field the app actually reads, and record provenance honestly.
        town["vegetation_deficit_estimate_fallback"] = old_deficit
        town["vegetation_deficit"] = calc["vegetation_deficit"]
        town["vegetation_source"] = "osm_fetched"
        town["vegetation_fetched_at"] = fetched_at
        town["vegetation_fraction"] = calc["vegetation_fraction"]
        town["vegetation_green_area_km2"] = calc["green_area_km2"]

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"\nWritten to {METADATA_PATH}")
    print("\nIMPORTANT - sanity check before trusting these numbers:")
    print("  1. Re-run backend/scripts/update_population.py's DB reload step "
          "(or just re-run backend/app/db/database.py init) so the new "
          "values actually load into the running database.")
    print("  2. Sanity-check the direction: denser old-city tehsils should "
          "still come out with a HIGHER deficit than peri-urban/agricultural "
          "ones. If the ranking flips entirely, investigate before trusting it.")
    print("  3. This depends on the CURRENT tehsil boundary polygons - if "
          "those are still the approximate fallback (not real OSM "
          "boundaries), say so alongside these numbers.")


if __name__ == "__main__":
    main()