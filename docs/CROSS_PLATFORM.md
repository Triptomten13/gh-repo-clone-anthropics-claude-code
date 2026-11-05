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
