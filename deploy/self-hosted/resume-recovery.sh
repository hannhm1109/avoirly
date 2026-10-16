#!/usr/bin/env bash
# Only resume when the backup itself left a protected maintenance marker.
set -euo pipefail
test "$EUID" = 0
marker=/run/avoirly-recovery-paused
test -f "$marker" || exit 0
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="${AVOIRLY_RUNTIME_DIR:-$(dirname "$source_dir")/runtime}"
compose=(docker compose --env-file "$runtime/.env" -f "$runtime/docker-compose.yml" -f "$source_dir/deploy/self-hosted/supabase-private.yaml" -f "$source_dir/deploy/self-hosted/compose.yaml")
"${compose[@]}" start db auth storage avoirly-api avoirly-worker avoirly-web
# Docker's started state precedes API readiness. Keep monitoring paused until
# the public API can answer, so planned maintenance does not produce a 502 alert.
deadline=$((SECONDS + 60))
until "${compose[@]}" exec -T avoirly-api python -c 'import httpx, os; httpx.get(os.environ["AVOIRLY_API_ORIGIN"] + "/api/v1/health", timeout=3).raise_for_status()' >/dev/null 2>&1; do
  if test "$SECONDS" -ge "$deadline"; then
    printf '%s\n' 'Application readiness did not return within the recovery grace period.' >&2
    exit 1
  fi
  sleep 2
done
if test "$(cat "$marker")" = monitor; then systemctl start avoirly-monitor.timer; fi
rm -f "$marker"
