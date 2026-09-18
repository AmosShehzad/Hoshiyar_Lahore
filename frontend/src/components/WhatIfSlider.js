import { useMemo, useState } from "react";
import RiskGauge from "@/components/RiskGauge";
import { calculateHeatRisk, FACTOR_LABELS } from "@/lib/riskEngine";

/**
 * WhatIfSlider - drag temperature/humidity and watch the risk score, gauge,
 * and attribution update live. Population density and vegetation deficit
 * stay fixed (they're properties of the tehsil, not the weather) so this
 * isolates exactly what a forecast change would do to risk.
 *
 * Computed entirely client-side (see lib/riskEngine.js) so it updates
 * instantly on every drag - no server round trip.
 */
export default function WhatIfSlider({ town }) {
  const currentTemp = town?.temperature_c ?? 40;
  const currentHumidity = town?.humidity_pct ?? 30;

  const [temp, setTemp] = useState(currentTemp);
  const [humidity, setHumidity] = useState(currentHumidity);

  const result = useMemo(
    () =>
      calculateHeatRisk({
        temperatureC: temp,
        humidityPct: humidity,
        populationDensity: town?.population_density ?? 0,
        vegetationDeficit: town?.vegetation_deficit ?? 0,
      }),
    [temp, humidity, town?.population_density, town?.vegetation_deficit]
  );

  const isDefault =
    Math.abs(temp - currentTemp) < 0.05 && Math.abs(humidity - currentHumidity) < 0.05;

  function reset() {
    setTemp(currentTemp);
    setHumidity(currentHumidity);
  }

  const explanation = useMemo(() => {
    const ranked = Object.entries(result.attributionPct)
      .sort((a, b) => b[1] - a[1])
      .filter(([, pct]) => pct > 0)
      .slice(0, 3)
      .map(([k, pct]) => `${FACTOR_LABELS[k]} (${Math.round(pct)}%)`);
    return (
      `At ${temp.toFixed(0)}°C and ${humidity.toFixed(0)}% humidity, ${town?.name || "this tehsil"} ` +
      `would score ${result.score.toFixed(0)}/100 (${result.band.label}). ` +
      `Main drivers: ${ranked.join(", ")}.`
    );
  }, [result, temp, humidity, town?.name]);

  return (
    <div className="rounded-xl border border-line bg-panel shadow-instrument p-4">
      <div className="flex items-center justify-between mb-1">
        <div>
          <div className="text-xs text-brand uppercase tracking-wide font-semibold">
            Scenario simulator
          </div>
          <h3 className="font-display text-base font-semibold text-ink">
            What if?
          </h3>
        </div>
        {!isDefault && (
          <button
            onClick={reset}
            className="text-[11px] border border-line rounded-full px-3 py-1 text-muted hover:text-ink hover:border-brand-dim transition-colors"
          >
            ↺ Reset to current
          </button>
        )}
      </div>
      <p className="text-xs text-muted mb-4 leading-relaxed">
        Drag the sliders to explore a scenario - population density and
        vegetation stay fixed to this tehsil, only weather changes.
      </p>

      <div className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-5 items-center">
        {/* Sliders column */}
        <div className="space-y-5">
          <SliderRow
            label="Air temperature"
            value={temp}
            min={20}
            max={55}
            step={0.5}
            unit="°C"
            onChange={setTemp}
          />
          <SliderRow
            label="Humidity"
            value={humidity}
            min={0}
            max={100}
            step={1}
            unit="%"
            onChange={setHumidity}
          />

          <div>
            <div className="text-[10px] text-muted uppercase tracking-wide mb-2">
              What would drive the score
            </div>
            <div className="space-y-2">
              {Object.entries(result.attributionPct)
                .sort((a, b) => b[1] - a[1])
                .map(([k, pct]) => (
                  <div key={k}>
                    <div className="flex justify-between text-[11px] mb-1">
                      <span className="text-muted">{FACTOR_LABELS[k]}</span>
                      <span className="font-mono text-ink">{pct.toFixed(0)}%</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-line overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-300"
                        style={{
                          width: `${Math.min(100, pct)}%`,
                          background: result.band.color,
                        }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>

        {/* Live gauge */}
        <div className="flex flex-col items-center gap-2">
          <RiskGauge
            score={result.score}
            color={result.band.color}
            band={result.band.label}
            size={120}
            strokeWidth={10}
          />
          <div className="text-[11px] text-muted font-mono">
            feels {result.heatIndexC.toFixed(0)}°C
          </div>
        </div>
      </div>

      <p className="text-xs text-ink/90 mt-4 pt-4 border-t border-line leading-relaxed">
        {explanation}
      </p>
      <p className="text-[10px] text-muted mt-2">
        Estimate calculated in your browser for exploration - live monitoring
        always uses the server's current data.
      </p>
    </div>
  );
}

function SliderRow({ label, value, min, max, step, unit, onChange }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="text-xs text-muted">{label}</span>
        <span className="font-mono text-sm text-ink font-semibold tabular-nums">
          {value.toFixed(step < 1 ? 1 : 0)}
          {unit}
        </span>
      </div>
      <input
        type="range"
        className="hoshiyar-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={label}
      />
    </div>
  );
}
