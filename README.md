# HoshiyarLahore

### Heatwave Early Warning for Health Authorities

**Smart City Hackathon 2026 · Theme: City Intelligence**

**Live demo:** _add your deployed Vercel URL here once live_

> *Hoshiyar* (ہوشیار) — "alert, watchful, prepared." An early-warning system that
> tells Lahore's health authorities where dangerous heat will hit first, and why.

Tehsil-level heat-risk intelligence for Lahore. HoshiyarLahore fuses live weather,
population, and land-cover data into an explainable heat-risk score for each of
Lahore's 5 administrative tehsils (2023 census) — so health authorities can
pre-position cooling centres, ORS supplies, and outreach teams in the right areas
*before* a heatwave arrives.

> **Test sentence:** When Punjab Health Department officials face a forecasted
> heatwave in Lahore, HoshiyarLahore tells them which specific towns will exceed
> dangerous heat thresholds, how many vulnerable people live in each, and why —
> so they can pre-position cooling centres, ORS supplies, and outreach teams in
> the right neighbourhoods 48–72 hours before the heat arrives.

---

## What's in this repository (Day 1 + Day 2 build)

This runs end-to-end today.

**Day 1 foundation:**
- ✅ 5 Lahore tehsils as a GeoJSON layer (with an OSM fetch script + fallback)
- ✅ Live weather integration with Open-Meteo (no API key required)
- ✅ SQLite database + schema + seed pipeline
- ✅ Interpretable heat-risk engine (Rothfusz heat index + weighted composite + attribution)
- ✅ FastAPI backend with `/api/towns`, `/api/towns/{id}`, `/api/alerts`, `/api/overview`
- ✅ Next.js + Leaflet dashboard (map, town detail panel, alerts, overview strip)
- ✅ A zero-setup `preview.html` you can open in a browser right now

**Day 2 additions:**
- ✅ Historical baseline pipeline — 10-year Open-Meteo archive fetcher + storage
- ✅ "X degrees above normal" comparison in each town's detail
- ✅ Town prioritisation ranking — the ordered "deploy resources here first" list
- ✅ New `/api/ranking` endpoint + historical block on `/api/towns/{id}`
- ✅ Dashboard: Alerts / Priority-ranking tabs + "Compared to normal" card
- ✅ Offline mock seeders for both weather and historical baselines

**Day 3 additions:**
- ✅ 72-hour forecast heat-risk — every hour scored with the same interpretable engine
- ✅ Predictive lead-time alerts — "Lahore City expected to reach Critical in ~13h"
- ✅ New `/api/towns/{id}/forecast` + `/api/predictive-alerts` endpoints
- ✅ Dashboard: forecast timeline (daily peaks + hourly bars) in the town panel
- ✅ Dashboard: "Forecast" tab with predictive lead-time warnings

**Day 4 additions:**
- ✅ Data validation script (`validate_data.py`) — pre-submission safety check
- ✅ Loading + error states (actionable full-screen error when backend is down)
- ✅ Mobile-responsive layout, verified at phone width
- ✅ Weight validation documented (model differentiates by density + vegetation)

**Pre-deployment additions:**
- ✅ Cooling-centre locations — toggleable map layer of hospitals, parks, venues
  (`/api/cooling-centres`), completing the "where to deploy" decision loop.
  Currently a curated list of 15 well-known Lahore landmarks (`source:
  curated_fallback` in the data), not a live OSM query — see the honesty note
  below on why Raiwind tehsil currently has none.
- ✅ Situation reports — copy-paste operational brief + SMS per tehsil
  (`/api/towns/{id}/sitrep`), assembled from risk + forecast + exposure + action
- ✅ **Auto-refresh (background)** — a scheduler inside the backend keeps weather
  (hourly) and historical baselines (daily) current automatically, no manual
  script-running needed. `GET /api/status` reports freshness honestly (including
  when a refresh fails); `POST /api/refresh` forces an immediate update.
  Requires a persistent backend process (Render/Railway
  Web Service) — will not auto-refresh on serverless hosting.
- ✅ Next.js production build verified; 49 passing tests
- ✅ **What-if scenario simulator** — drag temperature/humidity sliders in the
  town panel and watch the risk score, gauge, and attribution update live,
  computed client-side (`frontend/src/lib/riskEngine.js`, a verified JS port
  of the backend risk engine — matches exactly in ~80% of cases, never differs
  by more than 0.1/100, risk band always correct)
- ✅ **Visual identity** — a warm "instrument panel" look: Space Grotesk +
  IBM Plex Sans + IBM Plex Mono type system, a radial gauge dial as the
  signature risk-score display, and a bronze/ember accent palette distinct
  from the risk-band colors. (Two alternate themes — a light navy "civil GIS
  dashboard" look and a dark navy variant — were built and tried; the team
  settled back on this original warm bronze/charcoal identity.) Fonts load
  via a runtime `<link>` tag (not build-time fetch) so the build never
  depends on network access.

**Post-deployment fixes & additions:**
- ✅ **Map tiles fixed** — switched from CARTO's dark basemap (which started
  requiring a paid-tier API key after this project was built) to plain
  OpenStreetMap tiles, which have never required a key, with a CSS filter
  recoloring the tiles to match the dark theme (the map itself is still real,
  unaltered OSM data — only the on-screen color is changed)
- ✅ **"429 Too Many Requests" fixed** — the historical baseline fetch now
  makes 1 request per tehsil instead of 10 (one per year), the weather and
  historical startup jobs are staggered 45 seconds apart instead of bursting
  together, and all Open-Meteo requests retry with exponential backoff on a
  429 instead of giving up immediately. `/api/status` now reports the real
  HTTP error instead of a generic "offline" guess.
- ✅ **Manual "Refresh Temperatures" button** — the primary way the dashboard
  gets fresh live data right now. Calls `POST /api/refresh` on click, shows a
  loading state, and reports success or an honest failure reason (e.g. "rate
  limited, try again shortly") rather than a generic error. The automatic
  *request-triggered* refresh (silently refreshing on every visit if data is
  stale) was built and tested (`backend/app/scheduler.py`'s
  `ensure_fresh_weather()`, still covered by
  `backend/tests/test_request_triggered_refresh.py`) but is **not currently
  wired into any endpoint** — it was deliberately disabled in favour of the
  manual button for more predictable demo behaviour. Re-enabling it later is
  a two-line change (import it and add `Depends(ensure_fresh_weather)` back
  to the read endpoints in `backend/app/main.py`), documented in a comment
  right there in the file.
- ✅ **Real vegetation data fetching** — `backend/scripts/fetch_vegetation.py`
  calculates real vegetation coverage per tehsil from actual OpenStreetMap
  park/forest/grass polygons, intersected with each tehsil's boundary
  (genuine geometry, not a satellite measurement, and not a hand-typed
  guess). Not yet run against live data in this build — `vegetation_deficit`
  is currently still the original hand-typed estimate; see the honesty note
  below.
- ✅ **Real boundary-fetching fix** — `backend/scripts/fetch_boundaries.py`
  had two real bugs fixed: it never actually filtered OSM results by
  `admin_level`, and it stitched a boundary's way-segments together by naive
  concatenation instead of properly joining them end-to-end, which silently
  produced invalid, jumbled shapes even when OpenStreetMap had good data.
  Now uses `shapely.linemerge()` for correct ring assembly, with an area
  sanity-check against the census figures before accepting a match — proven
  correct with synthetic tests (`backend/scripts/test_fetch_boundaries.py`),
  since Overpass isn't reachable in this dev environment to test against
  live data directly.
- ✅ **Non-overlapping fallback boundaries, built and available (not currently
  active)** — `backend/scripts/generate_fallback_boundaries.py` generates
  approximate tehsil shapes from a Voronoi partition of the real centroids,
  which structurally guarantees zero overlap between neighbours (verified:
  0% overlap across all 5 tehsils). The team compared this against the
  original hexagon-based fallback shapes and preferred the original hexagons
  for visual clarity, so **the active fallback is currently the original
  hexagons** (which do overlap somewhat) — the Voronoi generator remains in
  the codebase as an available alternative.

Later days add: live deployment data, demo video, pitch deck.

---

## Quick start

### Option A — Instant preview (no setup)

Open **`preview.html`** in any modern browser. It shows the full dashboard using
a snapshot of mock data. (The interactive map needs internet to load tiles; the
risk data, alerts, and detail panel work offline.)

### Option B — Run the real stack

**1. Backend**

```bash
cd hoshiyar-lahore
python -m pip install -r backend/requirements.txt

# Initialise DB and load towns
python -m backend.app.db.database

# Get weather. EITHER real (needs internet, no API key):
python backend/scripts/refresh_weather.py
# OR mock (works offline, clearly flagged as mock):
python backend/scripts/seed_mock_weather.py

# Day 2: historical baselines. EITHER real (needs internet, slow ~minutes):
python backend/scripts/refresh_historical.py
# OR mock (works offline, flagged with years_used=0):
python backend/scripts/seed_mock_historical.py

# Start the API - this ALSO starts the hourly/daily background auto-refresh
# scheduler. Use the "Refresh Temperatures" button on the dashboard, or
# POST /api/refresh, to force an immediate live-weather fetch on demand.
uvicorn backend.app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API docs.

**2. Frontend**

```bash
cd frontend
npm install
# point the frontend at your backend (defaults to localhost:8000)
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm run dev
```

Visit http://localhost:3000.

### Optional — Improve the underlying map/land data

```bash
# Real tehsil boundaries from OpenStreetMap (falls back to approximate
# polygons per-tehsil if no good match is found; verify results yourself —
# see the honesty note below)
python backend/scripts/fetch_boundaries.py

# Real vegetation coverage per tehsil from OpenStreetMap park/forest data
python backend/scripts/fetch_vegetation.py

# Regenerate the approximate fallback shapes as a non-overlapping Voronoi
# partition instead of the current hexagons (optional alternative; not
# currently the active fallback - see above)
python backend/scripts/generate_fallback_boundaries.py
```

`fetch_boundaries.py` overwrites `data/geojson/lahore_towns.geojson`.
**Verify the output on https://geojson.io before relying on it** — automated
sanity checks catch the most obvious failures, not every possible one.

---

## Repository structure

```
hoshiyar-lahore/
├── README.md
├── preview.html                       # zero-setup dashboard preview (offline-capable)
├── .github/
│   └── workflows/
│       └── keep-alive.yml             # pings the backend every 10 min so Render's
│                                       # free tier doesn't sleep
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                    # FastAPI app + all endpoints
│   │   ├── scheduler.py               # background auto-refresh (hourly/daily) +
│   │   │                              # request-triggered "refresh if stale" (built,
│   │   │                              # tested, currently NOT wired into endpoints)
│   │   ├── db/
│   │   │   ├── schema.sql             # SQLite schema
│   │   │   └── database.py            # DB helpers + town seeding
│   │   └── services/
│   │       ├── open_meteo.py          # Open-Meteo client (weather + archive),
│   │       │                          # incl. 429 retry/backoff
│   │       ├── heat_index.py          # Rothfusz heat index
│   │       ├── risk_engine.py         # weighted composite risk + attribution
│   │       ├── heat_intelligence.py   # ranking + historical comparison
│   │       ├── forecast.py            # 72h forecast risk + predictive alerts
│   │       └── situation_report.py    # operational brief + SMS generator
│   ├── scripts/
│   │   ├── fetch_boundaries.py        # real OSM boundary fetcher (proper
│   │   │                              # linemerge-based ring-stitching + admin_level
│   │   │                              # filtering + census-area sanity check)
│   │   ├── generate_fallback_boundaries.py  # Voronoi-based non-overlapping
│   │   │                              # fallback shapes (alternative, not active)
│   │   ├── test_fetch_boundaries.py   # synthetic geometry tests for the above
│   │   ├── fetch_cooling_centres.py   # OSM Overpass cooling-centre fetcher
│   │   ├── fetch_vegetation.py        # real OSM-based vegetation coverage per tehsil
│   │   ├── test_fetch_vegetation.py   # synthetic geometry tests for the above
│   │   ├── refresh_weather.py         # Open-Meteo current+forecast -> SQLite
│   │   ├── refresh_historical.py      # 10-yr archive -> SQLite (1 req/tehsil)
│   │   ├── seed_mock_weather.py       # offline mock weather
│   │   ├── seed_mock_historical.py    # offline mock baselines
│   │   ├── update_population.py       # verify/update town populations safely
│   │   └── validate_data.py           # pre-submission data validation
│   └── tests/                          # 49 tests total (across this dir + the
│       │                              # two scripts/test_*.py files above)
│       ├── test_risk_engine.py
│       ├── test_heat_intelligence.py
│       ├── test_forecast.py
│       ├── test_situation_report.py
│       └── test_request_triggered_refresh.py  # tests the scheduler logic directly;
│                                      # not currently wired into live endpoints
├── data/
│   ├── geojson/
│   │   ├── lahore_towns.geojson              # active boundaries (hexagon fallback by default)
│   │   ├── lahore_towns_fallback.geojson     # approximate hexagon polygons
│   │   ├── cooling_centres.geojson           # active cooling-centre candidates
│   │   └── cooling_centres_fallback.geojson  # curated real-landmark fallback
│   └── metadata/
│       └── town_metadata.json         # population, density, veg deficit, etc.
└── frontend/
    ├── package.json
    ├── next.config.js / tailwind.config.js / postcss.config.js
    └── src/
        ├── pages/
        │   ├── index.js               # main dashboard page
        │   ├── _app.js
        │   └── _document.js           # loads Google Fonts via runtime <link>
        ├── components/
        │   ├── RiskMap.js             # Leaflet map (OSM tiles + dark CSS filter)
        │   ├── RiskGauge.js           # signature radial score dial
        │   ├── TownPanel.js           # tehsil detail panel
        │   ├── WhatIfSlider.js        # client-side scenario simulator
        │   ├── ForecastTimeline.js    # 72h forecast chart
        │   ├── SituationReport.js     # copy-paste brief + SMS
        │   ├── RefreshButton.js       # manual "Refresh Temperatures" trigger
        │   ├── AlertsPanel.js
        │   ├── PredictiveAlertsPanel.js
        │   └── RankingPanel.js
        ├── lib/
        │   ├── api.js                 # backend API client
        │   └── riskEngine.js          # JS port of the risk engine (for the slider)
        └── styles/globals.css
```

---

## How the risk score works (short version)

Each town gets a **0–100 heat-risk score** = a weighted blend of four factors:

| Factor | Weight |
|---|---|
| Feels-like temperature (heat index) | 40% |
| Air temperature | 25% |
| Population density | 20% |
| Low vegetation / built-up density | 15% |

The model is **interpretable, not a black box** — every score decomposes into
the exact contribution of each factor, so a health officer can see *why* a town
is flagged.

---

## Data & honesty note

Population, area, and density are **official 2023 census figures** for Lahore's 5
tehsils (`verified: true` in `data/metadata/town_metadata.json`), and are
internally consistent (density = population / area).

`vegetation_deficit` **can** be a real, fetched value —
`backend/scripts/fetch_vegetation.py` calculates it from actual OpenStreetMap
park/forest/grass polygons intersected with each tehsil's boundary (a genuine
geometric calculation from real map data, not a satellite NDVI measurement,
and not a hand-typed guess). **In this build it has not been run against live
data yet**, so `vegetation_deficit` is currently still the original
hand-typed estimate for all 5 tehsils — check `town_metadata.json`'s
`vegetation_source` field (`"osm_fetched"` vs absent) to see which is active
before presenting these numbers as measured.

Tehsil boundaries are currently the **original approximate hexagon shapes**
(not real OSM-traced boundaries, and not the improved Voronoi shapes either —
see the additions list above for why). `fetch_boundaries.py` had a real,
fixed bug in its geometry assembly; running it now with internet access has
a much better chance of producing real boundaries than before, but hasn't
been done in this build — **verify any fetched boundary on geojson.io before
trusting it.**

Cooling-centre candidates are a **curated list of 15 well-known Lahore
landmarks**, not a live query — this is why Raiwind tehsil currently shows
none: the list was built around famous, central hospitals/parks/universities,
and Raiwind, being the rural/agricultural edge of the district, has none of
them. This is a known, disclosed gap, not a bug — a live OpenStreetMap fetch
(the code for this exists in `fetch_cooling_centres.py`) would find smaller
local clinics and schools there too.

Mock weather and mock baselines are always clearly labelled — run
`refresh_weather.py` / `refresh_historical.py` for live data before the demo.

This tool is a decision-support prototype, **not an official government
advisory**.

---

## Team

- **Amir Ali Asif — Data & Geospatial:** boundaries, Open-Meteo, SQLite, data pipeline
- **Amos Shehzad — Risk Engine & AI:** heat index, scoring, attribution, alerts
- **Hussain Raza — Full Stack & UI:** FastAPI, Next.js, Leaflet, deployment

## License

Prepared for the Smart City Hackathon 2026.