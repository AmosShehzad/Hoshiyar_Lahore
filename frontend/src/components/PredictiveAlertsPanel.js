const LEVEL_STYLE = {
  critical: { color: "#D34B4B", label: "CRITICAL" },
  high: { color: "#E0793A", label: "HIGH" },
};

function leadLabel(hours) {
  if (hours <= 0) return "now";
  if (hours < 24) return `in ~${hours}h`;
  const days = Math.round(hours / 24);
  return `in ~${days}d`;
}

export default function PredictiveAlertsPanel({ alerts, onSelect }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="p-4 text-sm text-muted border border-line rounded-xl bg-panel">
        No tehsils forecast to cross into dangerous heat in the next 72 hours.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((a) => {
        const s = LEVEL_STYLE[a.level] || LEVEL_STYLE.high;
        return (
          <button
            key={a.town_id}
            onClick={() => onSelect && onSelect(a.town_id)}
            className="w-full text-left rounded-xl border border-line bg-panel p-3 hover:border-brand-dim transition-colors shadow-instrument"
          >
            <div className="flex items-center justify-between">
              <span
                className="text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wide"
                style={{ background: s.color, color: "#15100C" }}
              >
                {s.label}
              </span>
              <span className="text-xs font-mono font-semibold" style={{ color: s.color }}>
                {leadLabel(a.hours_until)}
              </span>
            </div>
            <div className="mt-2 text-sm font-medium text-ink">{a.town_name}</div>
            <div className="mt-1 text-xs text-muted leading-snug">
              {a.recommended_action}
            </div>
          </button>
        );
      })}
      <div className="text-[10px] text-muted px-2 pt-1">
        Lead time = hours until the tehsil is forecast to reach this risk level.
      </div>
    </div>
  );
}