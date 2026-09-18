const BAND_COLOR = {
  low: "#6FBF73",
  moderate: "#E8B339",
  high: "#E0793A",
  critical: "#D34B4B",
};

export default function RankingPanel({ ranking, selectedId, onSelect }) {
  if (!ranking || ranking.length === 0) {
    return (
      <div className="p-4 text-sm text-muted border border-line rounded-xl bg-panel">
        No ranking available.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {ranking.map((t) => {
        const color = BAND_COLOR[t.risk_band?.level] || "#5A4534";
        const isSel = t.town_id === selectedId;
        return (
          <button
            key={t.town_id}
            onClick={() => onSelect && onSelect(t.town_id)}
            className={
              "w-full text-left rounded-xl border p-2.5 flex items-center gap-3 transition-colors shadow-instrument " +
              (isSel
                ? "border-brand bg-raised"
                : "border-line bg-panel hover:border-brand-dim")
            }
          >
            <span className="font-mono text-sm font-bold text-muted w-6 text-center">
              {t.priority}
            </span>
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ background: color }}
            />
            <span className="flex-1 text-sm font-medium text-ink truncate">
              {t.town_name}
            </span>
            <span className="text-xs text-muted font-mono">
              {Number(t.estimated_exposed_population).toLocaleString()}
            </span>
            <span
              className="font-mono text-sm font-bold w-10 text-right"
              style={{ color }}
            >
              {t.risk_score}
            </span>
          </button>
        );
      })}
      <div className="text-[10px] text-muted px-2 pt-1">
        Ranked by current heat risk · number = exposed population
      </div>
    </div>
  );
}