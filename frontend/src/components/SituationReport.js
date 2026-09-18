import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SituationReport({ townId }) {
  const [report, setReport] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!townId) return;
    setReport(null);
    setCopied(false);
    setError(null);
    api.sitrep(townId).then(setReport).catch((e) => setError(e.message));
  }, [townId]);

  function copy() {
    if (!report) return;
    navigator.clipboard?.writeText(report.body).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => setCopied(false)
    );
  }

  if (!townId) return null;
  if (error) return null; // fail quietly; the rest of the panel still works
  if (!report) return null;

  return (
    <div className="rounded-xl border border-line bg-raised shadow-instrument p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] text-brand uppercase tracking-wide font-semibold">
          Situation report
        </div>
        <button
          onClick={copy}
          className="text-xs border border-line rounded-full px-3 py-1 hover:border-brand-dim transition-colors text-muted hover:text-ink"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre className="text-xs text-ink whitespace-pre-wrap leading-relaxed font-mono">
        {report.body}
      </pre>
      <div className="mt-3 pt-3 border-t border-line">
        <div className="text-[10px] text-muted uppercase tracking-wide mb-1">
          SMS version
        </div>
        <p className="text-xs text-muted leading-snug font-mono">{report.sms_short}</p>
      </div>
    </div>
  );
}
