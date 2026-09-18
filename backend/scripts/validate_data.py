"""
validate_data.py  (Day 4)
=========================

Pre-submission data validation for HoshiyarLahore.

Checks that every tehsil has complete, internally-consistent data and that the
pipeline is in a demizable state. Run this before any demo or submission:

    python backend/scripts/validate_data.py

Exit code 0 = all checks passed; 1 = at least one problem found.

It checks:
  - metadata: every tehsil has all required fields, no nulls
  - density consistency: population_density == population / area_km2
  - verified flag: reports which tehsils are still verified=false
  - geometry: every tehsil has a polygon in the active GeoJSON
  - database: towns loaded, weather present, forecast present, historical present
  - freshness: whether weather is mock or real (warns if mock)
"""

from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, REPO_ROOT)

from backend.app.db.database import get_connection  # noqa: E402

METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")
GEOJSON_PATH = os.path.join(REPO_ROOT, "data", "geojson", "lahore_towns.geojson")

REQUIRED_FIELDS = [
    "id", "name", "centroid", "population", "area_km2",
    "population_density", "vegetation_deficit",
]

problems: list[str] = []
warnings: list[str] = []


def check(condition: bool, ok_msg: str, fail_msg: str) -> bool:
    if condition:
        print(f"  \u2713 {ok_msg}")
        return True
    print(f"  \u2717 {fail_msg}")
    problems.append(fail_msg)
    return False


def warn(condition: bool, warn_msg: str) -> None:
    if condition:
        print(f"  ! {warn_msg}")
        warnings.append(warn_msg)


def validate_metadata():
    print("\n[1] Metadata completeness & consistency")
    with open(METADATA_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    towns = meta["towns"]

    check(len(towns) > 0, f"{len(towns)} tehsils found", "no tehsils in metadata")

    for t in towns:
        name = t.get("name", t.get("id", "?"))
        # required fields present and non-null
        for field in REQUIRED_FIELDS:
            if t.get(field) in (None, ""):
                problems.append(f"{name}: missing field '{field}'")
                print(f"  \u2717 {name}: missing '{field}'")

        # density consistency
        pop, area, dens = t.get("population"), t.get("area_km2"), t.get("population_density")
        if all(isinstance(x, (int, float)) for x in (pop, area, dens)) and area:
            calc = round(pop / area)
            if abs(calc - dens) > max(3, dens * 0.02):
                problems.append(
                    f"{name}: density {dens} != population/area ({calc})"
                )
                print(f"  \u2717 {name}: density {dens} != pop/area {calc}")

        # verified flag
        if not t.get("verified"):
            warn(True, f"{name}: verified=false (confirm against PBS)")

    verified_count = sum(1 for t in towns if t.get("verified"))
    check(verified_count == len(towns),
          f"all {len(towns)} tehsils verified against source",
          f"only {verified_count}/{len(towns)} tehsils verified")

    # Vegetation provenance + a basic sanity check on the fetched values.
    # This does NOT replace a human sanity check - see fetch_vegetation.py's
    # own printed reminder - but it catches the most obvious failure mode:
    # a run that silently produced nonsense (e.g. every tehsil reporting the
    # same value, which would suggest the fetch/intersection logic broke).
    fetched = [t for t in towns if t.get("vegetation_source") == "osm_fetched"]
    if fetched:
        print(f"\n  Vegetation: {len(fetched)}/{len(towns)} tehsils using REAL "
              f"OSM-fetched values (see 'vegetation_fetched_at' per tehsil).")
        deficits = [t["vegetation_deficit"] for t in fetched]
        if len(set(deficits)) == 1 and len(fetched) > 1:
            warn(True, "all fetched tehsils show the IDENTICAL vegetation_deficit "
                       "- likely a bug (e.g. the intersection loop isn't varying "
                       "per tehsil), not a real coincidence. Investigate before demo.")
    else:
        warn(True, "vegetation_deficit is still the original hand-typed estimate "
                   "for all tehsils - run fetch_vegetation.py for real values.")

    return towns


def validate_geometry(towns):
    print("\n[2] Geometry coverage")
    if not os.path.exists(GEOJSON_PATH):
        problems.append("active GeoJSON file missing")
        print("  \u2717 lahore_towns.geojson not found")
        return
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        gj = json.load(f)
    ids_with_geom = {feat["properties"]["id"] for feat in gj["features"]}
    for t in towns:
        has = t["id"] in ids_with_geom
        if not has:
            problems.append(f"{t['name']}: no geometry")
            print(f"  \u2717 {t['name']}: no polygon")
    check(all(t["id"] in ids_with_geom for t in towns),
          f"all {len(towns)} tehsils have polygons",
          "some tehsils missing polygons")
    # note the source (real OSM vs fallback) - match on "fallback" appearing
    # anywhere in the source label, not one exact string, so this doesn't
    # silently stop firing if the fallback-generation method's label ever
    # changes (as it did: "approximate_fallback" -> "approximate_fallback_voronoi").
    sources = {feat["properties"].get("source", "?") for feat in gj["features"]}
    fallback_sources = {s for s in sources if "fallback" in s}
    if fallback_sources:
        warn(True, f"geometry uses approximate fallback polygons ({', '.join(sorted(fallback_sources))}) "
                   "(real OSM boundaries pending — see fetch_boundaries.py)")


def validate_database():
    print("\n[3] Database state")
    try:
        conn = get_connection()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"cannot open database: {exc}")
        print(f"  \u2717 cannot open database: {exc}")
        return

    try:
        n_towns = conn.execute("SELECT COUNT(*) c FROM towns").fetchone()["c"]
        n_cur = conn.execute("SELECT COUNT(*) c FROM weather_current").fetchone()["c"]
        n_fc = conn.execute("SELECT COUNT(*) c FROM weather_forecast").fetchone()["c"]
        n_hist = conn.execute("SELECT COUNT(*) c FROM weather_historical").fetchone()["c"]

        check(n_towns > 0, f"{n_towns} towns in DB", "no towns in DB (run database.py)")
        check(n_cur > 0, f"{n_cur} current-weather rows",
              "no current weather (run refresh_weather.py or seed_mock_weather.py)")
        check(n_fc > 0, f"{n_fc} forecast rows",
              "no forecast data (run refresh_weather.py or seed_mock_weather.py)")
        check(n_hist > 0, f"{n_hist} historical baseline rows",
              "no historical baselines (run refresh_historical.py or seed_mock_historical.py)")

        # mock vs real detection
        mock_cur = conn.execute(
            "SELECT COUNT(*) c FROM weather_current WHERE observed_at LIKE 'MOCK%'"
        ).fetchone()["c"]
        if mock_cur > 0:
            warn(True, f"{mock_cur} tehsils using MOCK weather — run refresh_weather.py "
                       f"for the live demo")
        mock_hist = conn.execute(
            "SELECT COUNT(*) c FROM weather_historical WHERE years_used = 0"
        ).fetchone()["c"]
        if mock_hist > 0:
            warn(True, "historical baselines are MOCK (years_used=0) — run "
                       "refresh_historical.py for the live demo")
    finally:
        conn.close()


def main():
    print("=" * 64)
    print("HoshiyarLahore — Data Validation (Day 4)")
    print("=" * 64)

    towns = validate_metadata()
    validate_geometry(towns)
    validate_database()

    print("\n" + "=" * 64)
    if problems:
        print(f"RESULT: {len(problems)} PROBLEM(S) FOUND — fix before submission:")
        for p in problems:
            print(f"  \u2717 {p}")
    else:
        print("RESULT: All hard checks PASSED.")
    if warnings:
        print(f"\n{len(warnings)} warning(s) (not blockers, but review before the live demo):")
        for w in warnings:
            print(f"  ! {w}")
    print("=" * 64)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()