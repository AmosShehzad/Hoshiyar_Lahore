const LEVEL_STYLE = {
  critical: { color: "#D34B4B", label: "CRITICAL" },
  warning: { color: "#E0793A", label: "WARNING" },
  advisory: { color: "#E8B339", label: "ADVISORY" },
};

export default function AlertsPanel({ alerts, onSelect }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="p-4 text-sm text-muted border border-line rounded-xl bg-panel">
        No active heat alerts.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((a) => {
        const s = LEVEL_STYLE[a.level] || LEVEL_STYLE.advisory;
        const isCritical = a.level === "critical";
        return (
          <button
            key={a.town_id}
            onClick={() => onSelect && onSelect(a.town_id)}
            className="w-full text-left rounded-xl border border-line bg-panel p-3 hover:border-brand-dim transition-colors shadow-instrument"
          >
            <div className="flex items-center justify-between">
              <span
                className={
                  "text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wide " +
                  (isCritical ? "animate-pulse-critical" : "")
                }
                style={{ background: s.color, color: "#15100C" }}
              >
                {s.label}
              </span>
              <span className="text-xs text-muted font-mono">Score {a.risk_score}</span>
            </div>
            <div className="mt-2 text-sm font-medium text-ink">{a.town_name}</div>
            <div className="mt-1 text-xs text-muted leading-snug">
              {a.recommended_action}
            </div>
          </button>
        );
      })}
    </div>
  );
}