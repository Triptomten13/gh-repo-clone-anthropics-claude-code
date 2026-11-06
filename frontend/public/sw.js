/* Demonkoncernen AB service worker — an installable app shell, nothing more.
 *
 * Caches ONLY static, content-hashed assets (/_next/static, icons) and the offline page. It never caches or answers
 * /api, /health or the live event stream: AI, agents, the Archive and every figure come from the server, and the app
 * must not pretend they work offline. Navigations go to the network first; when the network is gone they fall back
 * to the last copy of that page shell (whose data calls then fail visibly) or to /offline.html.
 * Updates: a new version waits until the user accepts the "update available" notice (SKIP_WAITING message).
 */
const VERSION = "dk-v2";
const STATIC = `${VERSION}-static`;
const PAGES = `${VERSION}-pages`;
const PRECACHE = ["/offline.html", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => c.addAll(PRECACHE)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (!k.startsWith(VERSION)) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("message", (e) => {
  if (e.data === "SKIP_WAITING") self.skipWaiting();
});

const neverCache = (url) => url.pathname.startsWith("/api/") || url.pathname === "/health" || url.pathname.startsWith("/ws/");

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || neverCache(url)) return; // straight to the network

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    // content-hashed → immutable: cache first
    e.respondWith(caches.open(STATIC).then(async (c) => (await c.match(req)) || fetch(req).then((res) => {
      if (res.ok) c.put(req, res.clone());
      return res;
    })));
    return;
  }

  if (req.mode === "navigate") {
    e.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res.ok && res.headers.get("content-type")?.includes("text/html")) (await caches.open(PAGES)).put(req, res.clone());
        return res;
      } catch {
        return (await caches.match(req, { cacheName: PAGES })) || (await caches.match("/offline.html")) || Response.error();
      }
    })());
  }
});
