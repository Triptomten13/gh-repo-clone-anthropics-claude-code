import type { NextConfig } from "next";

// The browser always talks to the web server's own origin (/api, /ws, /health); this server proxies those to the
// backend. So a phone on the LAN, a tablet or an HTTPS deployment reach the API through ONE address, the backend can
// stay on loopback, and there is no CORS or mixed-content problem. BACKEND_URL is where the backend listens as seen
// from this server (not from the browser). Rewrites are resolved at build time: set BACKEND_URL for `next build`
// (the Docker build passes it as a build argument).
const BACKEND = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// Content-Security-Policy for the web pages (the API sets its own, stricter one). Everything comes from this origin:
// no third-party scripts, styles, fonts, frames or connections, so injected markup cannot load code from elsewhere or
// send data to another origin with fetch/XHR/WebSocket/beacons/images. Inline scripts stay allowed because Next.js
// streams page data in inline <script> tags; replacing that with per-request nonces would make every page dynamic.
// So this narrows what an XSS bug could do — it does not replace output escaping (React) and the
// no-dangerouslySetInnerHTML rule. `next dev` additionally needs eval (fast refresh).
const DEV = process.env.NODE_ENV === "development";
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${DEV ? " ws: wss:" : ""}`,
  "worker-src 'self'",
  "manifest-src 'self'",
  "media-src 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");
const PAGE_SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  compress: true, // gzip: first-visit JavaScript ~1.2 MB → ~0.35 MB (streamed G-sus replies verified unbuffered through the proxy)
  // `next dev` blocks cross-origin requests for its dev assets unless the origin is listed (phones on the LAN)
  allowedDevOrigins: (process.env.DEV_ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean),
  // proxied requests otherwise time out after 30 s — deep reasoning and STANDARD/DEEP research take longer (measured
  // 42–91 s and ~32 s), and the live event socket must stay open
  experimental: { proxyTimeout: 10 * 60 * 1000 },
  async headers() {
    // the service worker must be re-checked on every visit, or updates are never noticed
    return [
      // pages and static files — not the proxied API, which sends its own headers
      { source: "/:path((?!api/|ws/|health$|ready$).*)", headers: PAGE_SECURITY_HEADERS },
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache, no-store, must-revalidate" }, { key: "Content-Type", value: "application/javascript; charset=utf-8" }] },
    ];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/ws/:path*", destination: `${BACKEND}/ws/:path*` },
      { source: "/health", destination: `${BACKEND}/health` },
      { source: "/ready", destination: `${BACKEND}/ready` }, // readiness for load balancers: database + schema
    ];
  },
};

export default nextConfig;
