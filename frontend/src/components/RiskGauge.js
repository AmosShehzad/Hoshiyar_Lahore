/**
 * RiskGauge - the product's signature visual element.
 *
 * Renders the heat-risk score as an instrument-style radial dial rather than
 * a flat number, reinforcing the "meteorological instrument panel" identity.
 * Tick marks at 25/50/75 mark the low/moderate/high/critical band
 * boundaries, so the dial itself teaches the scale.
 */
export default function RiskGauge({
  score,
  color,
  size = 148,
  strokeWidth = 12,
  band,
  pulse = false,
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const dash = pct * circumference;
  const center = size / 2;

  // Tick marks at the band boundaries (25 / 50 / 75), drawn as short radial
  // lines just outside the track.
  const ticks = [25, 50, 75].map((t) => {
    const angle = (t / 100) * 360 - 90; // -90 so 0% starts at the top
    const rad = (angle * Math.PI) / 180;
    const inner = radius + strokeWidth / 2 + 2;
    const outer = inner + 5;
    return {
      x1: center + inner * Math.cos(rad),
      y1: center + inner * Math.sin(rad),
      x2: center + outer * Math.cos(rad),
      y2: center + outer * Math.sin(rad),
    };
  });

  return (
    <div
      className="relative inline-flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={t.x1}
            y1={t.y1}
            x2={t.x2}
            y2={t.y2}
            stroke="#5A4534"
            strokeWidth={2}
            strokeLinecap="round"
          />
        ))}
        <g transform={`rotate(-90 ${center} ${center})`}>
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="#3D2E24"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
            style={{
              transition: "stroke-dasharray 500ms cubic-bezier(0.4,0,0.2,1), stroke 300ms ease",
            }}
            className={pulse ? "animate-pulse-critical" : ""}
          />
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-mono font-semibold leading-none tabular-nums"
          style={{ fontSize: size * 0.26, color }}
        >
          {Math.round(score)}
        </span>
        <span className="text-[10px] text-muted uppercase tracking-wider mt-1">
          / 100
        </span>
        {band && (
          <span
            className="text-[10px] font-semibold uppercase tracking-wide mt-1 px-2 py-0.5 rounded-full"
            style={{ background: `${color}26`, color }}
          >
            {band}
          </span>
        )}
      </div>
    </div>
  );
}