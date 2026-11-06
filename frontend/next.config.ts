import type { NextConfig } from "next";

// The browser always talks to the web server's own origin (/api, /ws, /health); this server proxies those to the
// backend. So a phone on the LAN, a tablet or an HTTPS deployment reach the API through ONE address, the backend can
// stay on loopback, and there is no CORS or mixed-content problem. BACKEND_URL is where the backend listens as seen
// from this server (not from the browser). Rewrites are resolved at build time: set BACKEND_URL for `next build`
// (the Docker build passes it as a build argument).
const BACKEND = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  compress: false, // do not buffer streamed G-sus replies; a TLS reverse proxy in front compresses in production
  // `next dev` blocks cross-origin requests for its dev assets unless the origin is listed (phones on the LAN)
  allowedDevOrigins: (process.env.DEV_ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean),
  // proxied requests otherwise time out after 30 s — deep reasoning and STANDARD/DEEP research take longer (measured
  // 42–91 s and ~32 s), and the live event socket must stay open
  experimental: { proxyTimeout: 10 * 60 * 1000 },
  async headers() {
    // the service worker must be re-checked on every visit, or updates are never noticed
    return [{ source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }, { key: "Content-Type", value: "application/javascript; charset=utf-8" }] }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/ws/:path*", destination: `${BACKEND}/ws/:path*` },
      { source: "/health", destination: `${BACKEND}/health` },
    ];
  },
};

export default nextConfig;
