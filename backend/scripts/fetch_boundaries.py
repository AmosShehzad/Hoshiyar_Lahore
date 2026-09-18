"""
fetch_boundaries.py
===================

Fetch REAL administrative boundaries for Lahore's 5 tehsils from
OpenStreetMap via the Overpass API, and write them to
data/geojson/lahore_towns.geojson.

WHAT CHANGED FROM THE EARLIER VERSION OF THIS SCRIPT
-------------------------------------------------------
The previous version of this script had two real bugs that likely explain
why real boundaries never successfully loaded, even when Overpass had data:

1. It never actually filtered by admin_level despite claiming to - it only
   matched on name, so a name match against the WRONG kind of feature (e.g.
   a small neighbourhood, not the tehsil) could silently win.
2. It stitched a relation's boundary way-segments together by just
   concatenating them in whatever order Overpass happened to return them -
   real administrative boundaries are usually built from many separate way
   segments that must be joined end-to-end (like puzzle pieces) to form a
   clean ring. Naive concatenation produces a jumbled, self-crossing shape,
   not a clean tehsil outline.

This version fixes both: it filters by admin_level (tries 6, 7, and 8, since
Pakistan's admin_level usage for tehsil-equivalent boundaries isn't fully
standardised across OSM data), and it uses shapely's linemerge() - built
specifically to join line segments wherever their endpoints match - instead
of naive concatenation. It also sanity-checks each candidate polygon's area
against the tehsil's known official census area before accepting it, so a
wrong-feature name match doesn't silently get accepted just because a name
matched.

USAGE
-----
    python backend/scripts/fetch_boundaries.py

If Overpass is unreachable, or no candidate for a tehsil passes the
sanity check, that tehsil's entry keeps the fallback approximate polygon so
the rest of the system keeps working.

IMPORTANT - THIS STILL NEEDS A HUMAN TO LOOK AT IT
-----------------------------------------------------
Automated sanity checks catch the most obvious failures (wrong feature, no
data, wildly wrong size) but cannot fully confirm a polygon's shape is right.
After running this, open the output file on https://geojson.io and visually
confirm each tehsil's outline looks like a real, sensible administrative
boundary - not a jumbled or truncated shape - before relying on it for a
demo or submission.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

import requests
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.ops import linemerge, unary_union

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "HoshiyarLahore/0.6 (hackathon; contact: team@example.com)"}

# The 5 official tehsils of Lahore (2023 census). OSM naming varies, so we
# provide several possible name spellings per tehsil.
TOWN_NAME_CANDIDATES = {
    "lahore_city": ["Lahore City Tehsil", "Lahore City", "Tehsil Lahore City"],
    "shalimar": ["Shalimar Tehsil", "Shalamar Tehsil", "Shalimar Town"],
    "model_town": ["Model Town Tehsil", "Model Town", "Tehsil Model Town"],
    "lahore_cantonment": ["Lahore Cantonment Tehsil", "Lahore Cantonment",
                          "Lahore Cantt", "Cantonment Tehsil"],
    "raiwind": ["Raiwind Tehsil", "Raiwind", "Tehsil Raiwind", "Raiwand Tehsil"],
}

# Try several admin_level values - Pakistan's tehsil-equivalent boundaries
# aren't 100% consistently tagged at one specific level across all of OSM.
ADMIN_LEVELS_TO_TRY = [6, 7, 8]

LAHORE_BBOX = (31.30, 74.15, 31.75, 74.60)  # south, west, north, east

# How far a candidate polygon's area may differ from the official census
# area before we reject it as probably the wrong feature. Generous on
# purpose (boundary definitions can legitimately differ a bit) but still
# catches "matched a completely different, wrong-sized feature."
MAX_AREA_RATIO_ERROR = 0.6  # accept between 40% and 160% of expected area

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns.geojson")
FALLBACK_PATH = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns_fallback.geojson")
METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")

# Same local flat-earth projection used by fetch_vegetation.py, for
# consistent, dependency-free area calculation (see that file for why).
REF_LAT, REF_LON = 31.50, 74.35
M_PER_DEG_LAT = 110_940.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))


def to_local_xy(lon: float, lat: float) -> tuple[float, float]:
    x = (lon - REF_LON) * M_PER_DEG_LON
    y = (lat - REF_LAT) * M_PER_DEG_LAT
    return x, y


# ---------------------------------------------------------------------------
# Overpass query
# ---------------------------------------------------------------------------

def build_query(names: list[str], admin_level: int) -> str:
    s, w, n, e = LAHORE_BBOX
    name_filters = "".join(
        f'  relation["boundary"="administrative"]["admin_level"="{admin_level}"]'
        f'["name"~"{name}",i]({s},{w},{n},{e});\n'
        for name in names
    )
    # (._;>;) = the matched relation(s) PLUS everything they recurse down to
    # (member ways and nodes). out geom embeds full lat/lon geometry
    # directly onto way elements, so no separate node-ID cross-referencing
    # is needed - this alone removes a major source of assembly bugs.
    return f"[out:json][timeout:90];\n(\n{name_filters});\n(._;>;);\nout geom;"


def query_overpass(query: str):
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"    Querying {endpoint} ...")
            resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=100)
            if resp.status_code == 200:
                return resp.json()
            print(f"      HTTP {resp.status_code}")
        except requests.RequestException as exc:
            print(f"      failed: {exc}")
        time.sleep(2)
    return None


# ---------------------------------------------------------------------------
# Proper geometry assembly - real ring-stitching, not naive concatenation
# ---------------------------------------------------------------------------

def build_polygon_from_relation(osm_json: dict):
    """
    Take an Overpass response (relation + its recursively-fetched way
    members, each with embedded geometry from 'out geom') and build a
    correct polygon by properly merging the way segments end-to-end.

    Returns None if no usable relation/geometry was found.
    """
    relations = [e for e in osm_json.get("elements", []) if e.get("type") == "relation"]
    ways = {e["id"]: e for e in osm_json.get("elements", []) if e.get("type") == "way"}
    if not relations:
        return None

    # If multiple relations matched (e.g. several fuzzy name hits), try each
    # and let the caller's area sanity-check decide which one (if any) to
    # keep - we return the first one that assembles into a valid polygon.
    for relation in relations:
        outer_way_ids = [
            m["ref"] for m in relation.get("members", [])
            if m.get("type") == "way" and m.get("role") in ("outer", "")
        ]
        if not outer_way_ids:
            continue

        segments = []
        for wid in outer_way_ids:
            way = ways.get(wid)
            if not way or not way.get("geometry"):
                continue
            coords = [(pt["lon"], pt["lat"]) for pt in way["geometry"]]
            if len(coords) >= 2:
                segments.append(LineString(coords))

        if not segments:
            continue

        # THE ACTUAL FIX: linemerge() joins line segments wherever their
        # endpoints coincide, producing continuous lines - unlike naively
        # concatenating segments in arbitrary order, which produces a
        # jumbled, self-crossing mess.
        merged = linemerge(segments)

        rings = []
        # linemerge returns either a single LineString (if everything joined
        # into one continuous line) or a MultiLineString (if there are
        # multiple disjoint pieces, e.g. the boundary has a gap or the
        # tehsil genuinely has a disconnected exclave).
        candidates = [merged] if isinstance(merged, LineString) else list(merged.geoms)
        for line in candidates:
            coords = list(line.coords)
            if len(coords) < 4:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])  # close the ring
            try:
                poly = Polygon(coords)
                if poly.is_valid and poly.area > 0:
                    rings.append(poly)
                elif not poly.is_valid:
                    # A self-intersecting ring can sometimes be repaired with
                    # a zero-width buffer - a standard shapely idiom - rather
                    # than discarding a mostly-correct shape outright.
                    fixed = poly.buffer(0)
                    if fixed.is_valid and fixed.area > 0:
                        rings.append(fixed)
            except Exception:  # noqa: BLE001
                continue

        if rings:
            return unary_union(rings) if len(rings) > 1 else rings[0]

    return None


def polygon_area_km2(geom) -> float:
    """Project to local metres (see fetch_vegetation.py) and compute area."""
    if geom.geom_type == "Polygon":
        polys = [geom]
    elif geom.geom_type == "MultiPolygon":
        polys = list(geom.geoms)
    else:
        return 0.0
    total_m2 = 0.0
    for p in polys:
        ring = [to_local_xy(lon, lat) for lon, lat in p.exterior.coords]
        total_m2 += Polygon(ring).area
    return total_m2 / 1_000_000


def shapely_to_geojson_coords(geom):
    """Convert a shapely Polygon/MultiPolygon back to GeoJSON coordinates,
    preserving the original lon/lat (NOT the projected local metres)."""
    if geom.geom_type == "Polygon":
        return "Polygon", [list(geom.exterior.coords)]
    else:  # MultiPolygon
        return "MultiPolygon", [[list(p.exterior.coords)] for p in geom.geoms]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_metadata():
    with open(METADATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_fallback_features() -> dict:
    if not os.path.exists(FALLBACK_PATH):
        return {}
    with open(FALLBACK_PATH, encoding="utf-8") as f:
        fc = json.load(f)
    return {feat["properties"]["id"]: feat for feat in fc["features"]}


def main():
    print("=" * 70)
    print("HoshiyarLahore - Boundary Fetcher (real ring-stitching)")
    print("=" * 70)

    metadata = load_metadata()
    town_meta = {t["id"]: t for t in metadata["towns"]}
    fallback_features = load_fallback_features()

    features = []

    for town_id, names in TOWN_NAME_CANDIDATES.items():
        meta = town_meta.get(town_id, {})
        expected_area = meta.get("area_km2")
        print(f"\n{meta.get('name', town_id)} (expecting ~{expected_area} km^2):")

        best_geom = None
        best_area = None

        for level in ADMIN_LEVELS_TO_TRY:
            query = build_query(names, level)
            result = query_overpass(query)
            if result is None:
                continue
            geom = build_polygon_from_relation(result)
            if geom is None:
                print(f"  admin_level={level}: no assemblable polygon")
                continue
            area = polygon_area_km2(geom)
            print(f"  admin_level={level}: assembled polygon, area={area:.1f} km^2")

            if expected_area:
                ratio = area / expected_area if expected_area else 0
                if not (1 - MAX_AREA_RATIO_ERROR <= ratio <= 1 + MAX_AREA_RATIO_ERROR):
                    print(f"    REJECTED: area is {ratio:.1f}x expected - "
                          f"probably the wrong feature, not this tehsil")
                    continue

            # Prefer whichever admin_level's result is closest to the
            # expected census area, across all levels tried.
            if best_area is None or (
                expected_area and abs(area - expected_area) < abs(best_area - expected_area)
            ):
                best_geom, best_area = geom, area

            time.sleep(1)  # be polite to Overpass between attempts

        if best_geom is not None:
            geom_type, coords = shapely_to_geojson_coords(best_geom)
            features.append({
                "type": "Feature",
                "properties": {
                    "id": town_id,
                    "name": meta.get("name", town_id),
                    "name_ur": meta.get("name_ur", ""),
                    "source": "openstreetmap",
                    "fetched_area_km2": round(best_area, 2),
                },
                "geometry": {"type": geom_type, "coordinates": coords},
            })
            print(f"  ACCEPTED: real OSM boundary, area {best_area:.1f} km^2")
        else:
            fb = fallback_features.get(town_id)
            if fb:
                features.append(fb)
                print("  Using fallback approximate polygon (no acceptable OSM match).")
            else:
                print("  WARNING: no OSM match AND no fallback available for this tehsil.")

    if not features:
        print("\nERROR: no boundaries obtained at all, and no fallback available. Aborting.")
        sys.exit(1)

    geojson = {"type": "FeatureCollection", "features": features}
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    real_count = sum(1 for f in features if f["properties"].get("source") == "openstreetmap")
    print(f"\nWrote {len(features)} tehsil boundaries to {OUTPUT_PATH}")
    print(f"  {real_count}/{len(features)} are real OSM boundaries; "
          f"{len(features) - real_count} fell back to the approximate shape.")
    print("\nNEXT STEP (do not skip): open the file on https://geojson.io and")
    print("visually confirm every tehsil's outline actually looks right before")
    print("relying on it for a demo.")


if __name__ == "__main__":
    main()