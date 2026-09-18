import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const BAND_COLOR = {
  low: "#6FBF73",
  moderate: "#E8B339",
  high: "#E0793A",
  critical: "#D34B4B",
};

function hourLabel(iso) {
  // iso like 2026-08-23T15:00
  const t = iso.slice(11, 16);
  return t;
}

function dayLabel(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "short" });
}

export default function ForecastTimeline({ townId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    if (!townId) return;
    setData(null);
    setError(null);
    api
      .forecast(townId)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [townId]);

  if (!townId) return null;
  if (error)
    return (
      <div className="text-xs text-muted">Forecast unavailable ({error}).</div>
    );
  if (!data)
    return <div className="text-xs text-muted">Loading forecast…</div>;
  if (!data.has_forecast)
    return <div className="text-xs text-muted">{data.message}</div>;

  const hourly = data.hourly;
  // Find day boundaries for labels (first hour of each date)
  const dayStarts = {};
  hourly.forEach((h, i) => {
    const day = h.time.slice(0, 10);
    if (!(day in dayStarts)) dayStarts[day] = i;
  });

  return (
    <div>
      <div className="text-xs text-muted uppercase tracking-wide mb-2">
        72-hour heat-risk forecast
      </div>

      {/* Daily peak summary */}
      <div className="flex gap-2 mb-3">
        {data.daily_peaks.map((d) => (
          <div
            key={d.date}
            className="flex-1 rounded-xl border border-line bg-raised shadow-instrument p-2 text-center"
          >
            <div className="text-[10px] text-muted">{dayLabel(d.peak_time)}</div>
            <div
              className="font-mono text-lg font-bold tabular-nums"
              style={{ color: d.band.color }}
            >
              {Math.round(d.peak_risk_score)}
            </div>
            <div className="text-[9px] text-muted">{d.band.label}</div>
          </div>
        ))}
      </div>

      {/* Hourly blocks */}
      <div className="flex gap-[2px] items-end h-16">
        {hourly.map((h, i) => {
          const heightPct = Math.max(8, h.risk_score);
          return (
            <div
              key={i}
              className="flex-1 rounded-sm cursor-pointer transition-opacity"
              style={{
                height: `${heightPct}%`,
                background: h.band.color,
                opacity: hover === null || hover === i ? 1 : 0.5,
              }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              title={`${h.time.slice(5, 16).replace("T", " ")} · ${Math.round(
                h.risk_score
              )} (${h.band.label}) · ${h.heat_index_c}°C feels-like`}
            />
          );
        })}
      </div>

      {/* Hover detail */}
      <div className="h-5 mt-1 text-[11px] text-muted">
        {hover !== null && hourly[hover] ? (
          <span>
            {hourly[hover].time.slice(5, 16).replace("T", " ")} · risk{" "}
            <span
              style={{ color: hourly[hover].band.color }}
              className="font-semibold"
            >
              {Math.round(hourly[hover].risk_score)} ({hourly[hover].band.label})
            </span>{" "}
            · feels {hourly[hover].heat_index_c}°C
          </span>
        ) : (
          <span>Hover a bar for hour-by-hour detail</span>
        )}
      </div>
    </div>
  );
}