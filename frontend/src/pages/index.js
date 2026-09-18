import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api } from "@/lib/api";
import TownPanel from "@/components/TownPanel";
import AlertsPanel from "@/components/AlertsPanel";
import PredictiveAlertsPanel from "@/components/PredictiveAlertsPanel";
import RankingPanel from "@/components/RankingPanel";
import RefreshButton from "@/components/RefreshButton";

// Leaflet must be loaded client-side only (no SSR).
const RiskMap = dynamic(() => import("@/components/RiskMap"), { ssr: false });

const BAND_COLOR = {
  low: "#6FBF73",
  moderate: "#E8B339",
  high: "#E0793A",
  critical: "#D34B4B",
};

export default function Home() {
  const [geojson, setGeojson] = useState(null);
  const [overview, setOverview] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [predictive, setPredictive] = useState([]);
  const [ranking, setRanking] = useState([]);
  const [coolingCentres, setCoolingCentres] = useState(null);
  const [showCentres, setShowCentres] = useState(false);
  const [dataStatus, setDataStatus] = useState(null);
  const [tab, setTab] = useState("alerts"); // "alerts" | "forecast" | "ranking"
  const [selectedId, setSelectedId] = useState(null);
  const [selectedTown, setSelectedTown] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Reusable: loads all dashboard data. Called on mount, and again after the
  // "Refresh Temperatures" button successfully fetches live data - in that
  // second case we skip the full-page spinner (showFullPageLoading=false)
  // since the button already shows its own loading state and the page
  // shouldn't blank out under the user while they're looking at it.
  async function loadDashboardData({ showFullPageLoading } = {}) {
    if (showFullPageLoading) setLoading(true);
    try {
      const [towns, ov, al, rk, pa] = await Promise.all([
        api.towns(),
        api.overview(),
        api.alerts(),
        api.ranking(),
        api.predictiveAlerts("critical"),
      ]);
      setGeojson(towns);
      setOverview(ov);
      setAlerts(al.alerts || []);
      setRanking(rk.ranking || []);
      setPredictive(pa.alerts || []);
      setError(null);
      // Non-critical fetches that shouldn't block the dashboard
      api.coolingCentres().then(setCoolingCentres).catch(() => {});
      api.status().then(setDataStatus).catch(() => {});
    } catch (e) {
      setError(e.message);
    } finally {
      if (showFullPageLoading) setLoading(false);
    }
  }

  // Initial load
  useEffect(() => {
    loadDashboardData({ showFullPageLoading: true });
  }, []);

  // Load town detail when selection changes
  useEffect(() => {
    if (!selectedId) {
      setSelectedTown(null);
      return;
    }
    api.town(selectedId).then(setSelectedTown).catch((e) => setError(e.message));
  }, [selectedId]);

  return (
    <div className="min-h-screen flex flex-col bg-base">
      {/* Header */}
      <header className="border-b border-line px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Wordmark />
          <div>
            <h1 className="font-display text-lg font-semibold tracking-tight text-ink leading-none">
              Hoshiyar<span className="text-muted font-normal">Lahore</span>
            </h1>
            <p className="text-[11px] text-muted mt-1">
              Heatwave Early Warning for Health Authorities
            </p>
          </div>
        </div>
        <div className="flex items-start gap-4">
          <div className="text-xs text-muted text-right">
            <div className="tracking-wide">City Intelligence · 2023 Census</div>
            {dataStatus && <FreshnessBadge status={dataStatus} />}
          </div>
          <RefreshButton
            onRefreshed={() => loadDashboardData({ showFullPageLoading: false })}
          />
        </div>
      </header>

      {/* Loading state (initial fetch) */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="inline-block w-8 h-8 border-2 border-line border-t-brand rounded-full animate-spin mb-3" />
            <p className="text-sm text-muted">Loading Lahore heat-risk data…</p>
          </div>
        </div>
      )}

      {/* Full-screen error state (backend unreachable on first load) */}
      {!loading && error && !overview && (
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="max-w-md text-center">
            <div className="text-critical text-sm font-semibold mb-2">
              Can't reach the HoshiyarLahore API
            </div>
            <p className="text-sm text-muted mb-4">
              The dashboard loads live data from the backend, which isn't
              responding ({error}).
            </p>
            <div className="text-left text-xs text-muted bg-panel border border-line rounded-xl p-4 space-y-1">
              <p className="text-ink font-semibold mb-1">Start the backend:</p>
              <p className="font-mono">uvicorn backend.app.main:app --port 8000</p>
              <p className="mt-2 text-ink font-semibold mb-1">Load data if empty:</p>
              <p className="font-mono">python backend/scripts/seed_mock_weather.py</p>
              <p className="font-mono">python backend/scripts/seed_mock_historical.py</p>
            </div>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 text-sm border border-line rounded-full px-4 py-2 hover:border-brand-dim transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Non-blocking error banner (data loaded but a later call failed) */}
      {!loading && error && overview && (
        <div className="bg-critical/10 border-b border-critical/40 px-6 py-2 text-sm text-critical">
          Some data failed to refresh ({error}). Showing the most recent
          available.
        </div>
      )}

      {/* Dashboard (only once loaded) */}
      {!loading && overview && (
      <>
      {/* Overview strip */}
      {overview && overview.has_weather && (
        <div className="border-b border-line px-6 py-3 grid grid-cols-2 md:grid-cols-5 gap-3">
          <Metric
            label="Lahore avg risk"
            value={overview.average_risk_score}
            color={BAND_COLOR[overview.average_risk_band?.level]}
          />
          <Metric label="High/Critical tehsils" value={overview.high_or_critical_towns} />
          <Metric label="Critical" value={overview.band_counts.critical} color={BAND_COLOR.critical} />
          <Metric label="Active alerts" value={alerts.length} />
          <Metric
            label="Est. exposed"
            value={Number(overview.total_estimated_exposed).toLocaleString()}
          />
        </div>
      )}

      {/* Main grid */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_380px]">
        {/* Map + alerts column */}
        <div className="flex flex-col">
          <div className="flex-1 min-h-[420px] relative">
            <RiskMap
              geojson={geojson}
              selectedId={selectedId}
              onSelect={setSelectedId}
              coolingCentres={coolingCentres}
              showCentres={showCentres}
            />
            {coolingCentres && coolingCentres.features?.length > 0 && (
              <button
                onClick={() => setShowCentres((v) => !v)}
                className="absolute top-3 right-3 z-[1000] text-xs border rounded-full px-3 py-1.5 bg-panel/90 backdrop-blur transition-colors"
                style={{
                  borderColor: showCentres ? "#5dade2" : "#3D2E24",
                  color: showCentres ? "#5dade2" : "#A8917E",
                }}
              >
                {showCentres ? "✓ " : ""}Cooling centres ({coolingCentres.features.length})
              </button>
            )}
          </div>
          <div className="border-t border-line p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex gap-1">
                <TabButton active={tab === "alerts"} onClick={() => setTab("alerts")}>
                  Alerts ({alerts.length})
                </TabButton>
                <TabButton active={tab === "forecast"} onClick={() => setTab("forecast")}>
                  Forecast ({predictive.length})
                </TabButton>
                <TabButton active={tab === "ranking"} onClick={() => setTab("ranking")}>
                  Priority ranking
                </TabButton>
              </div>
              <Legend />
            </div>
            {tab === "alerts" && (
              <>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">
                  Priority actions for health authorities
                </h2>
                <AlertsPanel alerts={alerts} onSelect={setSelectedId} />
              </>
            )}
            {tab === "forecast" && (
              <>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">
                  Predicted heat — lead-time warnings
                </h2>
                <PredictiveAlertsPanel
                  alerts={predictive}
                  onSelect={setSelectedId}
                />
              </>
            )}
            {tab === "ranking" && (
              <>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-2">
                  Where to deploy resources first
                </h2>
                <RankingPanel
                  ranking={ranking}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              </>
            )}
          </div>
        </div>

        {/* Detail panel */}
        <aside className="border-t lg:border-t-0 lg:border-l border-line bg-panel">
          <TownPanel town={selectedTown} onClose={() => setSelectedId(null)} />
        </aside>
      </main>

      <footer className="border-t border-line px-6 py-2 text-[11px] text-muted">
        Data: Open-Meteo (weather) · PBS 2023 Census (population, area, density) ·
        OpenStreetMap (boundaries, approximate). Risk scores use an interpretable
        weighted model — see methodology. Not an official government advisory.
      </footer>
      </>
      )}
    </div>
  );
}

/**
 * Wordmark - a small logo mark echoing the product's two ideas: a watchful,
 * instrument-panel ring (rhyming with the RiskGauge signature element used
 * throughout the app) wrapped around a simple heat-shimmer glyph.
 */
function Wordmark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="13.5" stroke="#3D2E24" strokeWidth="2" />
      <path
        d="M16 2.5 A13.5 13.5 0 0 1 27.7 22.5"
        stroke="#C68A3D"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M8 20c1.5-2 2.5-3.5 2.5-5.2 0-1.4-.8-2.3-.8-3.8 0-1 .5-2 .5-2s1.8 1.6 1.8 3.6c0 1.3-.6 2-.6 3.2 0 1.6 1.2 2.4 1.2 4"
        stroke="#F3E9DC"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M15.5 21c1.2-1.6 2-2.8 2-4.2 0-1.1-.6-1.8-.6-3 0-.8.4-1.6.4-1.6s1.4 1.3 1.4 2.9c0 1-.5 1.6-.5 2.6 0 1.3.9 1.9.9 3.2"
        stroke="#F3E9DC"
        strokeWidth="1.3"
        strokeLinecap="round"
        fill="none"
        opacity="0.7"
      />
    </svg>
  );
}

function Metric({ label, value, color }) {
  return (
    <div className="rounded-xl border border-line bg-panel shadow-instrument p-3">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div
        className="font-mono text-2xl font-semibold tabular-nums"
        style={color ? { color } : { color: "#F3E9DC" }}
      >
        {value}
      </div>
    </div>
  );
}

function FreshnessBadge({ status }) {
  if (status.is_mock_weather) {
    return (
      <div className="text-moderate mt-0.5" title="Using mock/seed data, not live Open-Meteo">
        ● Mock data (offline demo)
      </div>
    );
  }
  const mins = status.weather_age_minutes;
  const label =
    mins == null
      ? "Live data"
      : mins < 60
      ? `Updated ${Math.round(mins)}m ago`
      : `Updated ${Math.round(mins / 60)}h ago`;
  const stale = mins != null && mins > 90; // auto-refresh runs hourly; >90m suggests it stalled
  return (
    <div
      className={stale ? "text-critical mt-0.5" : "text-low mt-0.5"}
      title="Live Open-Meteo data, auto-refreshed hourly"
    >
      ● {label} {stale ? "(auto-refresh may be stalled)" : ""}
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={
        "text-xs font-semibold px-3 py-1.5 rounded-full transition-colors " +
        (active
          ? "bg-raised text-ink border border-brand-dim"
          : "text-muted hover:text-ink")
      }
    >
      {children}
    </button>
  );
}

function Legend() {
  const items = [
    ["Low", BAND_COLOR.low],
    ["Moderate", BAND_COLOR.moderate],
    ["High", BAND_COLOR.high],
    ["Critical", BAND_COLOR.critical],
  ];
  return (
    <div className="flex gap-3">
      {items.map(([label, color]) => (
        <div key={label} className="flex items-center gap-1">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: color }}
          />
          <span className="text-[10px] text-muted">{label}</span>
        </div>
      ))}
    </div>
  );
}