// api.js - thin client for the HoshiyarLahore backend.
// Set NEXT_PUBLIC_API_BASE in .env.local to point at your deployed backend.
// Defaults to localhost for development.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json();
}

async function postJSON(path) {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  towns: () => getJSON("/api/towns"),
  town: (id) => getJSON(`/api/towns/${id}`),
  forecast: (id) => getJSON(`/api/towns/${id}/forecast`),
  sitrep: (id) => getJSON(`/api/towns/${id}/sitrep`),
  alerts: () => getJSON("/api/alerts"),
  predictiveAlerts: (threshold = "high") =>
    getJSON(`/api/predictive-alerts?threshold=${threshold}`),
  coolingCentres: () => getJSON("/api/cooling-centres"),
  overview: () => getJSON("/api/overview"),
  ranking: () => getJSON("/api/ranking"),
  status: () => getJSON("/api/status"),
  // Manually triggers a live weather fetch on the backend (runs the same
  // logic as refresh_weather.py). Can take several seconds - it waits for
  // Open-Meteo to actually respond for all 5 tehsils.
  refreshWeather: () => postJSON("/api/refresh"),
};

export { API_BASE };