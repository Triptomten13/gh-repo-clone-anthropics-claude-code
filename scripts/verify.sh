#!/usr/bin/env bash
# Full local verification: lint, backend tests, frontend type check and production build.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
echo "== ruff";  (cd "$root/backend" && ruff check .)
echo "== pytest"; (cd "$root/backend" && python -m pytest -q)
echo "== tsc";   (cd "$root/frontend" && npx tsc --noEmit)
echo "== build"; (cd "$root/frontend" && NEXT_TELEMETRY_DISABLED=1 npx next build >/tmp/next-build.log 2>&1 && grep -E "✓ Generating|Compiled" /tmp/next-build.log || { tail -30 /tmp/next-build.log; exit 1; })
echo "ALL CHECKS PASSED"
