import RiskGauge from "@/components/RiskGauge";
import ForecastTimeline from "@/components/ForecastTimeline";
import SituationReport from "@/components/SituationReport";
import WhatIfSlider from "@/components/WhatIfSlider";

const FACTOR_LABELS = {
  heat_index: "Feels-like temp",
  temperature: "Air temperature",
  population_density: "Population density",
  vegetation_deficit: "Low vegetation",
};

function Bar({ pct, color }) {
  return (
    <div className="h-2 w-full rounded-full bg-line overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${Math.min(100, pct)}%`, background: color }}
      />
    </div>
  );
}

export default function TownPanel({ town, onClose }) {
  if (!town) {
    return (
      <div className="p-6 text-muted text-sm flex flex-col items-center justify-center h-full text-center gap-2">
        <svg width="36" height="36" viewBox="0 0 32 32" fill="none" className="opacity-40">
          <circle cx="16" cy="16" r="12" stroke="currentColor" strokeWidth="2" />
          <circle cx="16" cy="16" r="3" fill="currentColor" />
        </svg>
        <p>Select a tehsil on the map to see its heat-risk profile.</p>
      </div>
    );
  }

  if (!town.has_weather) {
    return (
      <div className="p-5">
        <h2 className="font-display text-lg font-semibold text-ink">{town.name}</h2>
        <p className="mt-2 text-sm text-moderate">{town.message}</p>
      </div>
    );
  }

  const band = town.risk_band || {};
  const attr = town.attribution_pct || {};
  const isCritical = band.level === "critical";

  return (
    <div className="p-5 space-y-5 overflow-y-auto h-full">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-brand font-semibold">
            Tehsil heat-risk profile
          </div>
          <h2 className="font-display text-xl font-semibold text-ink mt-0.5">{town.name}</h2>
          {town.name_ur && (
            <div className="text-muted text-sm mt-0.5" dir="rtl">{town.name_ur}</div>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-muted hover:text-ink text-xs border border-line rounded-full px-3 py-1.5 hover:border-brand-dim transition-colors"
        >
          Close
        </button>
      </div>

      {/* Score - signature radial gauge */}
      <div className="rounded-xl border border-line bg-raised shadow-instrument p-5">
        <div className="flex items-center gap-4">
          <RiskGauge
            score={town.risk_score}
            color={band.color}
            band={band.label}
            size={116}
            strokeWidth={10}
            pulse={isCritical}
          />
          <div className="flex-1">
            <div className="text-[10px] text-muted uppercase tracking-wide">
              Overall heat risk
            </div>
            <p className="text-sm text-ink/90 leading-relaxed mt-1">
              {town.explanation}
            </p>
          </div>
        </div>
      </div>

      {/* Current conditions */}
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Air temp" value={`${town.temperature_c}°C`} />
        <Stat label="Feels like" value={`${town.heat_index_c}°C`} />
        <Stat label="Humidity" value={`${town.humidity_pct}%`} />
      </div>

      {/* Exposure */}
      <div className="rounded-xl border border-line bg-raised shadow-instrument p-4">
        <div className="text-[10px] text-muted uppercase tracking-wide">
          Estimated exposed population
        </div>
        <div className="font-mono text-2xl font-semibold text-ink tabular-nums">
          {Number(town.estimated_exposed_population).toLocaleString()}
        </div>
        <div className="text-xs text-muted mt-1">
          of {Number(town.population).toLocaleString()} residents
          {town.verified === false && " (population figure to be verified)"}
        </div>
      </div>

      {/* Historical comparison (Day 2) */}
      {town.historical && town.historical.anomaly_c != null && (
        <div className="rounded-xl border border-line bg-raised shadow-instrument p-4">
          <div className="text-[10px] text-muted uppercase tracking-wide mb-1">
            Compared to normal
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className="font-mono text-2xl font-semibold tabular-nums"
              style={{
                color: town.historical.anomaly_c > 0 ? "#E0793A" : "#6FBF73",
              }}
            >
              {town.historical.anomaly_c > 0 ? "+" : ""}
              {town.historical.anomaly_c}°C
            </span>
            <span className="text-xs text-muted">
              vs 10-yr average ({town.historical.normal_max_c}°C)
            </span>
          </div>
          <p className="text-xs text-muted mt-2 leading-relaxed">
            {town.historical.summary}
          </p>
        </div>
      )}

      {/* Attribution */}
      <div>
        <div className="text-[10px] text-muted uppercase tracking-wide mb-2">
          Why is this tehsil at risk?
        </div>
        <div className="space-y-3">
          {Object.entries(attr)
            .sort((a, b) => b[1] - a[1])
            .map(([k, pct]) => (
              <div key={k}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-ink/90">{FACTOR_LABELS[k] || k}</span>
                  <span className="text-muted font-mono">{pct}%</span>
                </div>
                <Bar pct={pct} color={band.color} />
              </div>
            ))}
        </div>
      </div>

      {/* What-if scenario simulator */}
      <WhatIfSlider town={town} />

      {/* 72-hour forecast timeline (Day 3) */}
      <div className="border-t border-line pt-4">
        <ForecastTimeline townId={town.id} />
      </div>

      {/* Operational situation report (copy-paste brief) */}
      <SituationReport townId={town.id} />
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-xl border border-line bg-raised shadow-instrument p-3">
      <div className="text-[10px] text-muted uppercase tracking-wide">
        {label}
      </div>
      <div className="font-mono text-lg font-semibold text-ink tabular-nums">{value}</div>
    </div>
  );
}