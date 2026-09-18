import { useState } from "react";
import { api } from "@/lib/api";

/**
 * RefreshButton - manually triggers a live weather fetch on the backend
 * (POST /api/refresh, same logic as refresh_weather.py) and, on success,
 * asks the parent to refetch the dashboard so the UI reflects the new data.
 *
 * Deliberately manual rather than automatic: gives predictable, one-click
 * control for a demo ("watch it fetch live data right now") without the
 * unpredictability of every page load silently trying to hit a possibly
 * rate-limited API. See backend/app/scheduler.py's ensure_fresh_weather()
 * for the automatic request-triggered variant, which is built and tested
 * but not currently wired in - a good fit once the backend runs on a paid,
 * always-on tier.
 */
export default function RefreshButton({ onRefreshed }) {
  const [state, setState] = useState("idle"); // idle | loading | success | error
  const [message, setMessage] = useState("");

  async function handleClick() {
    setState("loading");
    setMessage("");
    try {
      const result = await api.refreshWeather();
      if (result.weather_last_error) {
        setState("error");
        const isRateLimited = result.weather_last_error.includes("429");
        setMessage(
          isRateLimited
            ? "Weather API is rate-limited right now — try again in a few minutes."
            : "Couldn't fetch live data — still showing existing data."
        );
      } else {
        setState("success");
        setMessage("Temperatures updated.");
        onRefreshed && onRefreshed();
      }
    } catch (e) {
      setState("error");
      setMessage("Could not reach the backend.");
    } finally {
      setTimeout(() => setState("idle"), 5000);
    }
  }

  const loading = state === "loading";

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleClick}
        disabled={loading}
        className="text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors disabled:cursor-not-allowed"
        style={{
          borderColor: loading ? "#3D2E24" : "#C68A3D",
          color: loading ? "#A8917E" : "#C68A3D",
        }}
      >
        {loading ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
            Fetching live data…
          </span>
        ) : (
          "↻ Refresh Temperatures"
        )}
      </button>
      {message && (
        <span
          className="text-[10px] max-w-[220px] text-right leading-snug"
          style={{ color: state === "error" ? "#D34B4B" : "#6FBF73" }}
        >
          {message}
        </span>
      )}
    </div>
  );
}