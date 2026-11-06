# Cross-platform: desktop, tablet, phone, installable

Status of Demonkoncernen AB on desktop and mobile, how it is tested, and what is known not to work. Evidence first:
every claim below names the test or measurement behind it. Browser **emulation is not a physical device** — the test
matrix says which is which.

## 1. Audit (2026-11-05, before changes)

**Stack.** Next.js 16.4 App Router (client components), React 19.3, Tailwind 4, lucide icons, recharts · FastAPI on
:8000 (SQLite dev / PostgreSQL prod) · live events over a WebSocket (`/ws/events`, JWT in the query string) · G-sus
chat streamed over `fetch` · bearer token in `localStorage` · multipart uploads · Docker Compose (web, api, db, backup),
Next `standalone` output · GitHub Actions CI (backend pytest + PostgreSQL smoke + pip-audit; frontend typecheck, build,
npm audit) · 173 backend tests, **no frontend tests** (only ad-hoc Playwright scripts).

**Automated scan** (Playwright/Chromium, 28 routes × 9 widths = 252 page loads, touch emulation ≤ 1024 px):
no console errors anywhere; viewport meta present; no horizontal overflow at 320–430 px.

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | Critical | The browser calls the API at a **build-time** URL that defaults to `http://localhost:8000`. On a phone, `localhost` is the phone: every API call, the live WebSocket, streamed chat and uploads fail off-host; behind HTTPS it would also be blocked as mixed content | `lib/api.ts:3`, `frontend/Dockerfile` `ARG NEXT_PUBLIC_API_URL`, `chamber/page.tsx:150`, `knowledge/page.tsx:149` |
| 2 | Critical | **No navigation below 768 px**: the sidebar is `hidden md:flex` and nothing replaces it | scan: 27/27 app routes have 0 visible nav links at 320/375/390/430 px |
| 3 | High | CORS allows only `http://localhost:3000` | `backend/app/config.py:24` |
| 4 | High | Horizontal overflow beside the 240 px sidebar | 7 routes at 768 px (`/daemon` +320 px, `/flare/personas` +286, `/research` +203, `/flare/sideways` +164, `/settings` +64, `/ai` +39, `/agents` +7), 3 at 1024, `/research` at 1280 |
| 5 | Medium | Inputs are 13 px: iOS Safari zooms the page on every focus | `globals.css:46` |
| 6 | Medium | Native `prompt()/alert()/confirm()` (8 uses, 4 files) — blocking, unstyled, awkward on touch; the emergency stop uses one | `shell.tsx:152`, `daemon/page.tsx`, `knowledge/page.tsx`, `users.tsx` |
| 7 | Medium | Touch targets: 79–82 of 566 controls are smaller than 24 × 24 px at phone widths (WCAG 2.2 AA 2.5.8); 422 are under 44 px | scan |
| 8 | Medium | Not installable: no manifest, icons, theme colour or service worker | no `public/`, no `manifest` |
| 9 | Low | No safe-area insets; `min-h-screen` = 100vh (mobile toolbars) | `shell.tsx:90`, `login/page.tsx:30` |
| 10 | Low | Focus style defined for inputs only (buttons/links fall back to the browser ring) | `globals.css:48` |
| 11 | Low | WebSocket token travels in the query string (browsers cannot set headers on WebSockets) — may appear in proxy access logs | `lib/api.ts` `wsUrl` |
| 12 | Info | No frontend tests; CI runs no browser tests | `package.json`, `.github/workflows/ci.yml` |

Not found: hover-only controls (no `group-hover` reveals), unsupported browser APIs, fixed-width page wrappers.
File inputs already use `accept` lists including images (phones offer the camera); the memory export is a Blob
download (supported by iOS Safari 13+).

**Decision on installation strategy** (details in DECISIONS D-021): the frontend is a web app and every feature is
an API call to the one backend, so a **PWA** gives install on Windows/macOS/Linux (Chrome/Edge), Android and iOS
(Add to Home Screen) without a second codebase. No Electron/Tauri wrapper and no native app: nothing in the feature
list needs native APIs, and a wrapper would add an update channel and an attack surface without a measured benefit.

## 2. What changed (and why)

| Area | Now | Evidence |
|---|---|---|
| API address | The browser calls its **own origin** (`/api`, `/health`); the web server proxies to the backend (`BACKEND_URL`). The backend stays on 127.0.0.1 — never exposed | `health.sh` from a non-loopback LAN address: all checks pass; the API port refuses LAN connections |
| Live events | `GET /api/events/stream` (text/event-stream over HTTP), token in the `Authorization` header, one shared connection per tab, pauses in background tabs, reconnects with backoff. `/ws/events` kept | WebSocket upgrades returned 502 through the Next proxy (`next start` and standalone); HTTP streaming verified incrementally (33 chunks as produced) |
| Auth on live channels | Both channels check user + token revocation (the WebSocket checked only the signature) | `test_revoked_token_gets_no_live_events` |
| Streams through proxies | `Cache-Control: no-store, no-transform` on every stream | with gzip on and no `no-transform`, a 44 s reply arrived in **one** piece; with it, incrementally (test + measurement) |
| Shutdown | uvicorn `--timeout-graceful-shutdown 5` | an open stream kept uvicorn alive > 20 s after SIGTERM; with the flag 5.5 s |
| Proxy timeout | 10 min (Next default 30 s would cut deep reasoning, measured 42–91 s) | `next.config.ts` |
| Navigation | < 1024 px: bottom tab bar (Overview, G-sus, Archive, Control, More) + searchable "All pages" drawer; ≥ 1024 px: sidebar, collapsible (remembered); Ctrl/⌘+K anywhere; skip link | phones had **no** navigation before (27/27 routes) |
| Dialogs | native `<dialog>` (focus kept inside, Esc, modal semantics), bottom sheet on phones; secrets in masked fields | replaced 8 `prompt/confirm/alert` |
| Touch & keyboard | 16 px inputs on touch (no iOS zoom), bigger controls on coarse pointers, tab bar hides while typing, safe-area insets, `100dvh`, visible focus rings, reduced motion | e2e "tab bar steps aside while typing"; axe |
| Layout | shrinkable grid tracks everywhere (`grid-cols-1`/`minmax(0,1fr)`), capped selects, wrapping titles | responsive matrix: 0 sideways scroll on 27 pages × 11 sizes |
| Installable | manifest, icons from the G-SUS sigil, service worker (static assets + offline page only — never API data), update notice | Chrome installability check: no errors; PWA tests |
| Performance | gzip on (streams exempt), no prefetch from the 27-link page list, no layout jump on the Archive | before/after below |
| Errors | unreachable server → clear message + banner; reads time out after 30 s; AI writes never time out client-side | unit tests |

**Installation strategy (D-021).** PWA, not Electron/Tauri and not a native app: every feature is an API call to the
one backend, so a wrapper would add an update channel and attack surface without a measured benefit. Native would be
needed only for background push on iOS or deep OS integration — nothing in the current feature list.

## 3. Run it

| Task | Command (`make help` lists all) | Without make |
|---|---|---|
| Install | `make install` | `pip install -r backend/requirements-dev.txt` · `cd frontend && npm ci` |
| Develop on this computer | `make dev` → http://localhost:3000 | terminal 1: `cd backend && uvicorn app.main:app --port 8000` · terminal 2: `cd frontend && npm run dev` |
| Phones/tablets on your Wi-Fi | `make dev-lan` (prints the address) | `cd frontend && DEV_ALLOWED_ORIGINS=<this computer's IP> npm run dev:lan` (+ the backend as above; the dev server refuses other origins otherwise) |
| Production build locally | `make prod` / `make prod-lan` | `cd frontend && npm run build && node .next/standalone/server.js` |
| Health | `make health` · `DK_EMAIL=… DK_PASSWORD=… scripts/health.sh http://<ip>:3000` | — |
| All tests | `make test` | `cd backend && python -m pytest` · `cd frontend && npx playwright test` |
| Parts | `make test-unit · test-e2e · test-responsive · test-a11y · test-pwa · test-perf · lint · typecheck · build` | `npm run test:unit` etc. in `frontend/` |

`scripts/dev.sh` checks dependencies and free ports, waits for the API and the web server to be healthy and for the
proxy to answer, and exits non-zero with the last log lines if either process dies. Logs: `.dev-logs/`.

## 4. Real devices on your network

1. On the computer: `make dev-lan` (or `make prod-lan` for the installable build). It prints
   `Phone / tablet: http://192.168.x.y:3000`. Only the web server listens on the network; the API stays on loopback.
2. Same Wi-Fi on the phone; open that address. If it does not load: the computer's firewall must allow TCP 3000
   (Windows: allow Node.js on *private* networks; macOS: allow incoming connections for `node`); guest Wi-Fi networks
   often isolate devices.
3. Sign in with your account. The session lives in that device's browser storage.
4. **AI check:** header shows the active local model; Chamber → Conversation streams a reply; Control → Ask "25% of
   480" answers without a model. `DK_EMAIL=… DK_PASSWORD=… scripts/health.sh http://192.168.x.y:3000` checks sign-in,
   AI status and the live stream from any computer.
5. **Uploads/downloads:** Archive → Documents → File (phones offer camera / photos / files); Archive → Memory →
   Export JSON downloads a file (iOS: saved to Files).
6. **Disconnect test:** stop the computer's Wi-Fi or `Ctrl-C` the server → the app shows "Cannot reach the
   Demonkoncernen server" and the live dot goes grey; restart → banner clears, live feed reconnects (automated in
   `tests/matrix/pwa.spec.ts`).
7. **Errors on the phone:** Android — `chrome://inspect` on the computer with USB debugging; iPhone — Safari ▸ Develop
   menu on a Mac with Web Inspector enabled on the phone. Server side: `.dev-logs/api.log`, `.dev-logs/web.log`.

**HTTPS on the LAN.** Over plain `http://192.168…` the app works, but browsers withhold service workers, install-as-
app and some device APIs (camera capture beyond file pick, clipboard write) from non-secure origins. Options:
`DK_SITE=localhost docker compose --profile https up` (Caddy local CA — install its root certificate on the phone),
a real domain with `DK_SITE=dk.example.com`, or a private overlay network that issues certificates (e.g. Tailscale).
Never expose the development server or the admin API to the public internet without TLS and authentication.

## 5. Test matrix (what was run, where)

All automated runs below are **Chromium emulation** in the development container (Linux). Emulation reproduces
viewport, touch, device pixel ratio and user agent — not Safari's or Firefox's engines, real GPUs, real keyboards,
notches, or mobile networks. **No physical device has been used yet.**

| Target | How | Status |
|---|---|---|
| Desktop 1440 (Chrome engine, Linux) | e2e workflows | **passed** (emulation) |
| iPad gen 7 (810×1080, touch) | e2e workflows, Chromium | **passed** (emulation) — real Safari: not run |
| iPhone 13 (390×844, touch) | e2e workflows, Chromium | **passed** (emulation) — real Safari: not run |
| Pixel 7 (412×915, touch) | e2e workflows, Chromium | **passed** (emulation) — real device: not run |
| 320, 375, 390, 430, 768, 1024, 1280, 1440, 1920 px + 844×390 + 1180×820 | responsive matrix, 27 pages each | **passed** — 0 sideways scroll, nav reachable, 0 console errors |
| WebKit (Safari engine), Firefox | CI job `e2e-webkit-firefox` | **not run yet** (browsers not installable here); informational until it passes |
| Windows / macOS desktop, Edge, real Safari, Android Firefox | manual | **not run** — checklist in §7 |

Run locally: `make test-frontend` (starts its own stack on ports 8100/3100 with a throw-away database).

## 6. Performance and accessibility (measured)

`npm run test:perf` — first visit (no service worker), Chromium, this machine. Phone = 390×844, 4× CPU slowdown,
150 ms RTT, 1.6 Mbit/s down.

| Page | Phone LCP before → after | Phone JS before → after | Desktop LCP after | CLS (all) |
|---|---|---|---|---|
| `/login` | 1 584 → **620 ms** | 510 → 155 KB | 108 ms | ≤ 0.005 |
| `/` (overview, charts) | 5 968 → **2 576 ms** | 1 074 → 323 KB | 436 ms | ≤ 0.002 |
| `/control` | 3 808 → **1 704 ms** | 1 033 → 309 KB | 216 ms | ≤ 0.009 |
| `/knowledge` | 3 852 → **1 828 ms** | 1 033 → 309 KB | 216 ms | 0.164 → **0.001** (phone) |
| `/chamber` | 3 816 → **1 752 ms** | 1 033 → 309 KB | 252 ms | 0.07 (phone, < 0.1) |

Interaction (INP estimate, opening the page drawer): desktop 144–216 ms; throttled phone ~380–460 ms ("needs
improvement" band) — down from ~1 400 ms after removing prefetch from the page list. Removing the backdrop blur was
measured and showed no difference (kept). Budgets enforced by the test: CLS ≤ 0.1, LCP ≤ 2.5 s desktop / ≤ 4 s phone.

Accessibility: axe-core (WCAG 2.0/2.1/2.2 A + AA rules) on 10 main pages, desktop and phone — **no serious or
critical violations** after fixes (unlabeled selects, a name/label mismatch, keyboard-unreachable scrolling tables).
Automated checks find only part of real issues: a screen-reader pass (VoiceOver, TalkBack, NVDA) is still to do.

## 7. Known limitations

* No physical-device or non-Chromium run yet (see matrix). Before relying on iOS: one pass in Safari on an iPhone and
  an iPad (navigation, upload from camera, Add to Home Screen, keyboard + tab bar, safe areas).
* Behind the web server's own proxy every client shares one IP for the API's per-IP rate limit and login lockout
  (account lockout is unaffected). With the `https` profile the API sees real client IPs. The Caddy profile has not
  been executed here.
* iOS: no install prompt (Share → Add to Home Screen); web push is not implemented.
* Offline: only the app shell and an honest offline page. AI, agents, the Archive and all figures need the server.
* No ESLint in the frontend: `make lint` = ruff + TypeScript strict. Unit tests use Playwright's runner (vitest's
  install crashed npm's resolver).

## 8. Production readiness checklist

- [ ] `APP_ENV=production`, long random `SECRET_KEY`, separate `CREDENTIALS_KEY`; PostgreSQL; `alembic upgrade head`
- [ ] TLS in front (`docker compose --profile https`, `DK_SITE=<your domain>`); API and web ports not published publicly
- [ ] `FORWARDED_ALLOW_IPS` trusts only the proxy; `API_RATE_PER_MIN` sized for your users
- [ ] Backups running and one restore tested (docs/BACKUP_RECOVERY.md)
- [ ] `make verify` and `make test` green on the release commit; CI green, incl. the WebKit/Firefox job
- [ ] `python scripts/independence_test.py` green on the target hardware (local models)
- [ ] One manual pass on a real iPhone, iPad and Android phone (§4, §7) and a screen reader
- [ ] `scripts/health.sh https://<site>` from a phone's network after deploy
