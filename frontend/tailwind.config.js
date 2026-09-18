/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Warm instrument-panel neutrals (charcoal-with-ember, not cold blue-slate)
        base: "#15100C",
        panel: "#1F1712",
        raised: "#2A1F18",
        line: "#3D2E24",
        ink: "#F3E9DC",
        muted: "#A8917E",
        // Brand chrome - deliberately muted/bronze so it never reads as risk data
        brand: "#C68A3D",
        "brand-dim": "#8C6530",
        // Risk bands - the ONLY fully-saturated colors in the UI, reserved for risk meaning
        low: "#6FBF73",
        moderate: "#E8B339",
        high: "#E0793A",
        critical: "#D34B4B",
      },
      fontFamily: {
        display: ["Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        instrument: "inset 0 1px 0 0 rgba(243,233,220,0.04), 0 1px 2px 0 rgba(0,0,0,0.4)",
      },
      keyframes: {
        "pulse-critical": {
          "0%, 100%": { opacity: 1 },
          "50%": { opacity: 0.55 },
        },
      },
      animation: {
        "pulse-critical": "pulse-critical 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};