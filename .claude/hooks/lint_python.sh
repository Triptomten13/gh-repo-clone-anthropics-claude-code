#!/usr/bin/env bash
# PostToolUse: lint the Python file that was just edited; feed findings back to Claude (exit 2) so they get fixed immediately.
f=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path",""))')
case "$f" in
  *.py) cd "$(dirname "$0")/../../backend" 2>/dev/null || exit 0
        out=$(ruff check "$f" 2>&1) || { echo "$out" >&2; exit 2; } ;;
esac
exit 0
