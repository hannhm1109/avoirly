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
if test "$(cat "$marker")" = monitor; then systemctl start avoirly-monitor.timer; fi
rm -f "$marker"
