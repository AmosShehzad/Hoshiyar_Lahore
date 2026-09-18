"""
fetch_cooling_centres.py
========================

Fetch candidate cooling-centre locations for Lahore from OpenStreetMap via the
Overpass API, and write them to data/geojson/cooling_centres.geojson.

WHAT COUNTS AS A CANDIDATE
--------------------------
Places where a health authority could realistically set up or direct people to
shade/water/AC during a heatwave:
  - hospitals and clinics (amenity=hospital|clinic)
  - parks and public gardens (leisure=park|garden)  -> shade
  - schools/colleges (amenity=school|college)       -> large indoor halls

These are CANDIDATES, not officially designated cooling centres. The tool shows
them so an official can decide where to deploy resources near a high-risk tehsil.

USAGE
-----
    python backend/scripts/fetch_cooling_centres.py

Same resilient pattern as fetch_boundaries.py: if Overpass is unreachable, the
committed fallback (a small hand-picked set) is kept so the app still works.
Always verify fetched points before relying on them.
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Lahore bounding box: south, west, north, east
LAHORE_BBOX = (31.30, 74.15, 31.75, 74.60)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "geojson", "cooling_centres.geojson")
FALLBACK_PATH = os.path.join(
    REPO_ROOT, "data", "geojson", "cooling_centres_fallback.geojson"
)

# category -> (osm key, [values], display type)
QUERIES = [
    ("hospital", "amenity", ["hospital", "clinic"]),
    ("park", "leisure", ["park", "garden"]),
    ("school", "amenity", ["school", "college"]),
]

# Nice request headers - Overpass blocks the default python-requests UA.
HEADERS = {"User-Agent": "HoshiyarLahore/0.4 (hackathon; contact: team@example.com)"}


def build_query() -> str:
    s, w, n, e = LAHORE_BBOX
    parts = []
    for _cat, key, values in QUERIES:
        for v in values:
            parts.append(f'  node["{key}"="{v}"]({s},{w},{n},{e});')
            parts.append(f'  way["{key}"="{v}"]({s},{w},{n},{e});')
    body = "\n".join(parts)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center 200;"


def category_for(tags: dict) -> str | None:
    for cat, key, values in QUERIES:
        if tags.get(key) in values:
            return cat
    return None


def query_overpass(query: str):
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"  Querying {endpoint} ...")
            r = requests.post(endpoint, data={"data": query},
                              headers=HEADERS, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"    HTTP {r.status_code}")
        except requests.RequestException as exc:
            print(f"    failed: {exc}")
        time.sleep(2)
    return None


def main():
    print("=" * 64)
    print("HoshiyarLahore - Cooling-centre candidate fetcher")
    print("=" * 64)

    result = query_overpass(build_query())
    if result is None:
        print("\nOverpass unreachable. Keeping committed fallback file.")
        if not os.path.exists(OUTPUT_PATH) and os.path.exists(FALLBACK_PATH):
            with open(FALLBACK_PATH, encoding="utf-8") as f:
                data = json.load(f)
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"Copied fallback -> {OUTPUT_PATH}")
        return

    features = []
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        cat = category_for(tags)
        if cat is None:
            continue
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": tags.get("name", cat.title()),
                "category": cat,
            },
        })

    if not features:
        print("No candidates returned; keeping fallback.")
        return

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(features)} cooling-centre candidates to:\n  {OUTPUT_PATH}")
    print("Verify a sample on https://geojson.io before relying on them.")


if __name__ == "__main__":
    main()
