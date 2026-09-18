"""
update_population.py
====================

Helper for safely updating town populations after verifying them against PBS.

WHAT IT DOES
------------
1. Reads data/metadata/town_metadata.json
2. For every town, recomputes population_density = population / area_km2
   (so you never have to do the division by hand)
3. Reports which towns are still verified=false (i.e. not yet confirmed)
4. Warns about anything suspicious (missing fields, zero area, wildly off density)
5. Writes the file back with corrected densities

HOW TO USE
----------
1. Open data/metadata/town_metadata.json in any text editor.
2. For each town you've verified, update:
     - "population"   -> the real figure from PBS / census23.pbos.gov.pk
     - "area_km2"     -> the real area if you have a better one
     - "verified"     -> change false to true
   (You do NOT need to update population_density by hand - this script does it.)
3. Save the file, then run:
     python backend/scripts/update_population.py
4. Reload the data into the database:
     python -m backend.app.db.database
5. Re-seed or refresh weather so the API recomputes risk with the new numbers:
     python backend/scripts/seed_mock_weather.py     (offline)
       or
     python backend/scripts/refresh_weather.py        (live)

The script is safe to run repeatedly. It only changes population_density
(derived) and never touches your population/area/verified edits.
"""

from __future__ import annotations

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
METADATA_PATH = os.path.join(REPO_ROOT, "data", "metadata", "town_metadata.json")


def main() -> None:
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    towns = data.get("towns", [])
    print(f"Checking {len(towns)} towns...\n")

    unverified = []
    warnings = []
    updated = 0

    for t in towns:
        name = t.get("name", t.get("id", "?"))
        pop = t.get("population")
        area = t.get("area_km2")

        # Recompute density where possible
        if isinstance(pop, (int, float)) and isinstance(area, (int, float)) and area > 0:
            new_density = round(pop / area)
            old_density = t.get("population_density")
            if old_density != new_density:
                t["population_density"] = new_density
                updated += 1
                print(f"  {name}: density {old_density} -> {new_density} "
                      f"(= {pop:,} / {area} km2)")
        else:
            warnings.append(f"{name}: missing/invalid population or area_km2")

        # Sanity check: Lahore tehsil densities range ~2,000-20,000 /km2
        d = t.get("population_density")
        if isinstance(d, (int, float)) and (d < 500 or d > 60000):
            warnings.append(f"{name}: density {d:,}/km2 looks unusual - double-check "
                            f"population and area")

        if not t.get("verified"):
            unverified.append(name)

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nRecomputed density for {updated} town(s).")

    if warnings:
        print("\n WARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    if unverified:
        print(f"\n STILL UNVERIFIED ({len(unverified)}): "
              f"{', '.join(unverified)}")
        print("  These still show 'to be verified' in the app. Set "
              "\"verified\": true once confirmed against PBS.")
    else:
        print("\n All towns marked verified. ")

    print("\nNext steps:")
    print("  python -m backend.app.db.database        # reload towns into DB")
    print("  python backend/scripts/seed_mock_weather.py   # recompute risk (offline)")


if __name__ == "__main__":
    main()
