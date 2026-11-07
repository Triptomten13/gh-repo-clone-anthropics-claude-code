#!/usr/bin/env bash
# PreToolUse: block edits to secrets and to already-applied migrations (add a new migration instead).
f=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path",""))')
case "$f" in
  */.env|*/.env.*) [[ "$f" == *.env.example ]] || { echo "Blocked: never edit secret files ($f). Use .env.example for documentation." >&2; exit 2; } ;;
  */migrations/versions/*.py)
    if git -C "$(dirname "$f")" ls-files --error-unmatch "$f" >/dev/null 2>&1; then
      echo "Blocked: $f is a committed migration. Create a new revision with 'alembic revision --autogenerate'." >&2; exit 2
    fi ;;
esac
exit 0
