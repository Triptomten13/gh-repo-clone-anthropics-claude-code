#!/usr/bin/env bash
# Start Demonkoncernen AB: the API (FastAPI) and the web app (Next.js) together, with health checks.
#
#   scripts/dev.sh            this computer only            → http://localhost:3000
#   scripts/dev.sh --lan      also phones/tablets on the same network → http://<this computer's IP>:3000
#   scripts/dev.sh --prod     production build + standalone server (what Docker runs; use it to test the PWA)
#   scripts/dev.sh --lan --prod
#
# The browser only talks to the web server, which proxies /api and /health to the API; the API itself stays on
# 127.0.0.1 and is never exposed to the network. Ctrl-C stops both. If either process dies, the other is stopped and
# the script exits non-zero after printing that process's last log lines — a failure is never hidden.
# Env: API_PORT (8000), WEB_PORT (3000), DATABASE_URL (backend default: sqlite:///./rocky.db).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
HOST=127.0.0.1
MODE=dev
for a in "$@"; do
  case "$a" in
    --lan) HOST=0.0.0.0 ;;
    --prod) MODE=prod ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $a (see --help)" >&2; exit 2 ;;
  esac
done
LOG="$ROOT/.dev-logs"
mkdir -p "$LOG"
PY="${PYTHON:-python3}"

fail() { echo "✗ $*" >&2; exit 1; }
command -v "$PY" >/dev/null || fail "python3 not found"
command -v node >/dev/null || fail "node not found (Node.js 22 LTS)"
(cd "$ROOT/backend" && "$PY" -c "import fastapi, uvicorn, sqlalchemy" 2>/dev/null) ||
  fail "backend dependencies missing — run: make install   (or: pip install -r backend/requirements-dev.txt)"
[ -d "$ROOT/frontend/node_modules" ] || fail "frontend dependencies missing — run: make install   (or: cd frontend && npm ci)"
port_busy() { "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', $1))==0 else 1)"; }
port_busy "$API_PORT" && fail "port $API_PORT is already in use (another API running?) — stop it or set API_PORT"
port_busy "$WEB_PORT" && fail "port $WEB_PORT is already in use — stop it or set WEB_PORT"
LAN_IP="$("$PY" -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('192.0.2.1', 9)); print(s.getsockname()[0])" 2>/dev/null || true)"

API_PID=""; WEB_PID=""
cleanup() {
  trap - EXIT INT TERM
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null || true
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

died() { echo; echo "✗ $1 stopped (see $2). Last lines:" >&2; tail -n 25 "$2" >&2; exit 1; }
wait_for() { # url seconds pid name log
  local i=0
  until curl -fsS -o /dev/null --max-time 3 "$1" 2>/dev/null; do
    kill -0 "$3" 2>/dev/null || died "$4" "$5"
    i=$((i + 1)); [ "$i" -ge "$2" ] && { echo "✗ $4 did not answer $1 within $2 s" >&2; tail -n 25 "$5" >&2; exit 1; }
    sleep 1
  done
}

echo "▸ API   → 127.0.0.1:$API_PORT  (log: .dev-logs/api.log)"
RELOAD=""; [ "$MODE" = dev ] && RELOAD="--reload"
(cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --timeout-graceful-shutdown 5 $RELOAD) >"$LOG/api.log" 2>&1 &
API_PID=$!
wait_for "http://127.0.0.1:$API_PORT/health" 90 "$API_PID" "API" "$LOG/api.log"
echo "  ✓ API healthy"

export BACKEND_URL="http://127.0.0.1:$API_PORT" NEXT_TELEMETRY_DISABLED=1
if [ "$MODE" = prod ]; then
  echo "▸ web   production build (log: .dev-logs/build.log) …"
  (cd "$ROOT/frontend" && npx next build) >"$LOG/build.log" 2>&1 || { tail -n 30 "$LOG/build.log" >&2; fail "production build failed"; }
  S="$ROOT/frontend/.next/standalone"
  rm -rf "$S/.next/static" "$S/public" && cp -r "$ROOT/frontend/.next/static" "$S/.next/static"
  [ -d "$ROOT/frontend/public" ] && cp -r "$ROOT/frontend/public" "$S/public"
  (cd "$S" && PORT="$WEB_PORT" HOSTNAME="$HOST" exec node server.js) >"$LOG/web.log" 2>&1 &
else
  export DEV_ALLOWED_ORIGINS="${LAN_IP}"
  (cd "$ROOT/frontend" && exec npx next dev -p "$WEB_PORT" -H "$HOST") >"$LOG/web.log" 2>&1 &
fi
WEB_PID=$!
echo "▸ web   → $HOST:$WEB_PORT ($MODE)  (log: .dev-logs/web.log)"
wait_for "http://127.0.0.1:$WEB_PORT/login" 240 "$WEB_PID" "web" "$LOG/web.log"
curl -fsS --max-time 5 "http://127.0.0.1:$WEB_PORT/health" | grep -q '"ok"' || fail "web is up but its /health proxy to the API does not answer (BACKEND_URL=$BACKEND_URL)"
echo "  ✓ web healthy, proxy to the API works"
echo
echo "  Demonkoncernen AB is running"
echo "  This computer:  http://localhost:$WEB_PORT"
if [ "$HOST" = 0.0.0.0 ]; then
  echo "  Phone / tablet: http://${LAN_IP:-THIS-COMPUTER-IP}:$WEB_PORT   (same Wi-Fi; see docs/CROSS_PLATFORM.md §real devices)"
  echo "  Note: plain HTTP on a LAN address — install-as-app and offline caching need HTTPS (docs: HTTPS on the LAN)."
fi
echo "  Health:         scripts/health.sh http://localhost:$WEB_PORT"
echo "  Ctrl-C stops both."
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 1; done
kill -0 "$API_PID" 2>/dev/null || died "API" "$LOG/api.log"
died "web" "$LOG/web.log"
