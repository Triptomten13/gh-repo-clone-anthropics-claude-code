#!/usr/bin/env bash
# Check a running Demonkoncernen AB from the client's point of view (run it on a laptop, or with a LAN URL).
#   scripts/health.sh [WEB_URL]          default http://localhost:3000
#   DK_EMAIL=… DK_PASSWORD=… scripts/health.sh   also signs in and checks the AI status and the live event stream
# Exits non-zero if any check fails.
set -uo pipefail
WEB="${1:-http://localhost:3000}"; WEB="${WEB%/}"
ok=0; bad=0
check() { # name, command
  local out
  if out="$(eval "$2" 2>&1)"; then echo "✓ $1${out:+ — $out}"; ok=$((ok + 1)); else echo "✗ $1${out:+ — $out}"; bad=$((bad + 1)); fi
}
check "web app answers" "curl -fsS -o /dev/null -w '%{http_code} in %{time_total}s' --max-time 10 '$WEB/login'"
check "API reachable through the web server" "curl -fsS --max-time 10 '$WEB/health' | grep -q '\"ok\"' && echo /health ok"
check "auth service" "curl -fsS --max-time 10 '$WEB/api/auth/status' | head -c 120"
check "PWA manifest" "curl -fsS --max-time 10 '$WEB/manifest.webmanifest' | grep -q '\"name\"' && echo present"
if [ -n "${DK_EMAIL:-}" ] && [ -n "${DK_PASSWORD:-}" ]; then
  TOKEN="$(curl -fsS --max-time 15 -H 'Content-Type: application/json' -d "{\"email\":\"$DK_EMAIL\",\"password\":\"$DK_PASSWORD\"}" "$WEB/api/auth/login" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
  check "sign-in" "[ -n '$TOKEN' ] && echo token issued"
  check "AI status (models, offline mode)" "curl -fsS --max-time 15 -H 'Authorization: Bearer $TOKEN' '$WEB/api/ai/status' | head -c 160"
  # the stream never ends by design: curl's --max-time stops it (exit 28), so judge by what arrived
  check "live event stream" "{ curl -s -N --max-time 4 -H 'Authorization: Bearer $TOKEN' '$WEB/api/events/stream' || true; } | grep -q connected && echo connected"
else
  echo "• set DK_EMAIL and DK_PASSWORD to also check sign-in, AI status and the live event stream"
fi
echo "$ok passed, $bad failed"
[ "$bad" -eq 0 ]
