import { Html, Head, Main, NextScript } from "next/document";

/**
 * Fonts are loaded via a plain <link> tag rather than next/font/google.
 *
 * WHY: next/font/google downloads font files at BUILD time, which means the
 * build itself fails if the build machine can't reach Google Fonts (this bit
 * us during development - see docs/CHANGELOG.md). Loading fonts via a runtime
 * <link> tag means the build never depends on network access at all; if a
 * browser can't reach Google Fonts, it just falls back to the system font
 * stack already configured in tailwind.config.js - a graceful degradation
 * instead of a broken deployment.
 *
 * FONT CHOICE: Space Grotesk (display) + IBM Plex Sans (body) + IBM Plex
 * Mono (all data figures - scores, temperatures, percentages, timestamps),
 * reinforcing the "instrument panel" identity - every number reads like a
 * precise instrument reading, not decorative type.
 */
export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}