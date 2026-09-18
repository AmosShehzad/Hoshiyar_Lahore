"""
generate_fallback_boundaries.py
==================================

Regenerates data/geojson/lahore_towns_fallback.geojson - the approximate
boundary shapes used whenever fetch_boundaries.py can't get a real OSM
boundary for a tehsil.

WHY THIS EXISTS, AND WHAT WAS WRONG BEFORE
---------------------------------------------
The original fallback shapes were regular hexagons, each grown outward from
its own tehsil's centroid independently, sized to roughly match that
tehsil's census area. The problem: growing each shape independently, with no
awareness of where NEIGHBOURING tehsils sit, means adjacent tehsils overlap
each other significantly - up to ~50% of the smaller polygon's area, in the
original shapes. Real administrative boundaries never overlap; they PARTITION
space between neighbours. Simply making the hexagons "less regular" (more
organic-looking) does not fix this - it was tried and measured, and the
overlap percentages came out essentially identical to the original hexagons,
just with a different (still wrong) shape.

THE FIX: A VORONOI PARTITION
--------------------------------
This script instead computes a Voronoi diagram from the 5 tehsils' real
centroids (already in town_metadata.json). A Voronoi cell is, by
mathematical construction, "every point closer to this centroid than to any
other centroid" - which means Voronoi cells for different centroids NEVER
overlap and together cover the whole region with no gaps. This directly
fixes the overlap problem, structurally, rather than just changing how the
shapes look.

THE HONEST TRADEOFF
-----------------------
A Voronoi cell's area is determined purely by geometric proximity to
neighbouring centroids, not by each tehsil's actual census area - so, unlike
the previous hexagon approach, these shapes will NOT closely match each
tehsil's official area_km2. This is a deliberate choice: a correctly
non-overlapping, contiguous partition is a more visually and structurally
important property for a map than each individual shape's area being
precisely right, especially since the polygon's own geometric area is only
used internally by fetch_vegetation.py's area-ratio calculation (already
documented there as an approximation, not authoritative) - it is NEVER used
for the actual risk score, population, or density figures, which always come
directly from the census metadata regardless of polygon shape.

As always: these are still an APPROXIMATION for demo purposes. Run
fetch_boundaries.py with real internet access to replace them with actual
OSM-traced boundaries wherever possible; this script only produces the
fallback used when that isn't available.

USAGE
-----
    python backend/scripts/generate_fallback_boundaries.py
"""

from __future__ import annotations

import json
import os

from shapely.geometry import MultiPoint, Point, box
from shapely.ops import voronoi_diagram

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns_fallback.geojson")

# Clip the (mathematically infinite) outer Voronoi cells to this envelope -
# the same Lahore bounding box used by fetch_boundaries.py and
# fetch_vegetation.py, for consistency, and tight enough that outer cells
# don't balloon to an unrealistic size while still guaranteeing no overlap.
ENVELOPE = box(74.15, 31.30, 74.60, 31.75)  # west, south, east, north


def main():
    with open(METADATA_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    towns = meta["towns"]

    centroids = [Point(t["centroid"]["lon"], t["centroid"]["lat"]) for t in towns]
    multipoint = MultiPoint(centroids)

    cells = list(voronoi_diagram(multipoint, envelope=ENVELOPE).geoms)

    # voronoi_diagram doesn't preserve input order, so match each resulting
    # cell back to its tehsil by checking which centroid falls inside it.
    features = []
    for t, centroid in zip(towns, centroids):
        cell = next((c for c in cells if c.contains(centroid)), None)
        if cell is None:
            raise RuntimeError(f"no Voronoi cell found containing {t['id']}'s centroid - "
                               f"check the envelope covers all centroids")
        # Clip to the envelope again defensively (cells should already be
        # clipped by voronoi_diagram's envelope param, but this guarantees it).
        cell = cell.intersection(ENVELOPE)
        coords = [[round(x, 5), round(y, 5)] for x, y in cell.exterior.coords]
        features.append({
            "type": "Feature",
            "properties": {
                "id": t["id"],
                "name": t["name"],
                "name_ur": t["name_ur"],
                "source": "approximate_fallback_voronoi",
            },
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(features)} non-overlapping Voronoi-based fallback "
          f"boundaries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()