import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, Tooltip } from "react-leaflet";

// Colors match the backend risk_band() output.
const BAND_COLOR = {
  low: "#6FBF73",
  moderate: "#E8B339",
  high: "#E0793A",
  critical: "#D34B4B",
};

const CENTRE_STYLE = {
  hospital: { color: "#6FA8D6", label: "Hospital" },
  park: { color: "#7BC98E", label: "Park" },
  school: { color: "#C6A0D6", label: "Venue" },
};

function styleForFeature(feature) {
  const band = feature?.properties?.risk_band?.level || "low";
  return {
    color: "#15100C",
    weight: 1,
    fillColor: BAND_COLOR[band] || "#5A4534",
    fillOpacity: 0.68,
  };
}

export default function RiskMap({
  geojson,
  selectedId,
  onSelect,
  coolingCentres,
  showCentres,
}) {
  const geoRef = useRef(null);

  // Re-style when selection changes
  useEffect(() => {
    if (!geoRef.current) return;
    geoRef.current.eachLayer((layer) => {
      const id = layer.feature?.properties?.id;
      const base = styleForFeature(layer.feature);
      if (id === selectedId) {
        layer.setStyle({ ...base, weight: 3, color: "#F3E9DC", fillOpacity: 0.85 });
      } else {
        layer.setStyle(base);
      }
    });
  }, [selectedId, geojson]);

  function onEachFeature(feature, layer) {
    const p = feature.properties || {};
    const score = p.risk_score != null ? p.risk_score : "—";
    const band = p.risk_band?.label || "No data";
    layer.bindTooltip(
      `<div class="town-tooltip"><strong>${p.name}</strong><br/>` +
        `Risk: ${score} (${band})</div>`,
      { sticky: true, className: "" }
    );
    layer.on({
      click: () => onSelect && onSelect(p.id),
    });
  }

  return (
    <MapContainer
      center={[31.52, 74.36]}
      zoom={11}
      style={{ height: "100%", width: "100%" }}
      scrollWheelZoom={true}
      className="hoshiyar-map-dark"
    >
      {/*
        Real, unaltered OpenStreetMap tiles - genuine map imagery of Lahore
        and the surrounding area, with actual road/place names. A CSS filter
        (.hoshiyar-map-dark in globals.css) recolors the tiles to match the
        app's dark theme, WITHOUT changing the underlying map data - it's
        still a real map, just restyled the same way the rest of the UI is
        dark-themed. These tiles have never required an API key.
      */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {geojson && (
        <GeoJSON
          ref={geoRef}
          data={geojson}
          style={styleForFeature}
          onEachFeature={onEachFeature}
        />
      )}
      {showCentres &&
        coolingCentres &&
        coolingCentres.features?.map((f, i) => {
          const [lon, lat] = f.geometry.coordinates;
          const cat = f.properties.category || "hospital";
          const s = CENTRE_STYLE[cat] || CENTRE_STYLE.hospital;
          return (
            <CircleMarker
              key={i}
              center={[lat, lon]}
              radius={4}
              pathOptions={{
                color: "#0b131b",
                weight: 1,
                fillColor: s.color,
                fillOpacity: 0.9,
              }}
            >
              <Tooltip>
                <span style={{ fontSize: 12 }}>
                  <strong>{f.properties.name}</strong>
                  <br />
                  {s.label} · candidate cooling centre
                </span>
              </Tooltip>
            </CircleMarker>
          );
        })}
    </MapContainer>
  );
}