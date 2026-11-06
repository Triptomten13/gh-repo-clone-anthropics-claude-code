#!/bin/sh
# Start the API (loopback only) and the web server (public port) in one container; both log to stdout. If either
# stops, the container stops with a non-zero code — a failure is never hidden behind a running process.
set -eu
: "${PORT:=3000}"
: "${DATABASE_URL:=sqlite:////app/data/rocky.db}"
export DATABASE_URL
if [ -z "${SECRET_KEY:-}" ]; then
  case "${DEMO_MODE:-}:$DATABASE_URL" in
    1:sqlite:////app/data/*|true:sqlite:////app/data/*)
      # a public demo on container-local storage: data and sessions are temporary anyway
      SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"; export SECRET_KEY
      echo "▸ DEMO_MODE with temporary storage: generated a SECRET_KEY for this container's lifetime" ;;
    *) echo "✗ SECRET_KEY is not set (required unless DEMO_MODE=1 with the container's temporary SQLite database)" >&2; exit 1 ;;
  esac
fi
case "${DEMO_MODE:-}" in 1|true) export APP_ENV="${APP_ENV:-production}" ;; esac

cd /app/backend
echo "▸ database migrations"
alembic upgrade head
echo "▸ API → 127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5 --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" &
API=$!
i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" 2>/dev/null; do
  kill -0 "$API" 2>/dev/null || { echo "✗ API stopped during start (its log is above)" >&2; exit 1; }
  i=$((i + 1)); [ "$i" -ge 120 ] && { echo "✗ API did not become healthy in 120 s (its log is above)" >&2; kill "$API"; exit 1; }
  sleep 1
done
echo "  ✓ API healthy"
cd /app/web
echo "▸ web → 0.0.0.0:$PORT"
HOSTNAME=0.0.0.0 PORT="$PORT" node server.js &
WEB=$!
trap 'kill "$API" "$WEB" 2>/dev/null || true' INT TERM
while kill -0 "$API" 2>/dev/null && kill -0 "$WEB" 2>/dev/null; do sleep 2; done
if ! kill -0 "$API" 2>/dev/null; then echo "✗ API stopped (its log is above)" >&2; else echo "✗ web server stopped (its log is above)" >&2; fi
kill "$API" "$WEB" 2>/dev/null || true
exit 1
