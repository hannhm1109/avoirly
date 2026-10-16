#!/usr/bin/env bash
# Use on the private host. Never print resolved Compose configuration.
set -euo pipefail
umask 077
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime_dir="${AVOIRLY_RUNTIME_DIR:-$(dirname "$source_dir")/runtime}"
test -f "$runtime_dir/.env"
test -f "$runtime_dir/docker-compose.yml"
compose=(docker compose --env-file "$runtime_dir/.env" -f "$runtime_dir/docker-compose.yml" -f "$source_dir/deploy/self-hosted/supabase-private.yaml" -f "$source_dir/deploy/self-hosted/compose.yaml")
case "${1:-}" in
  backup) exec "${compose[@]}" run --rm --no-deps avoirly-ops python -m recovery.backup_job ;;
  monitor)
    "${compose[@]}" run --rm --no-deps avoirly-ops python scripts/check-monitor.py
    if test -d "$(dirname "$source_dir")/recovery-exports"; then python3 "$source_dir/scripts/check-recovery-age.py" --directory "$(dirname "$source_dir")/recovery-exports"; fi
    ;;
  full-backup) exec bash "$source_dir/deploy/self-hosted/full-backup.sh" ;;
  resume-recovery) exec bash "$source_dir/deploy/self-hosted/resume-recovery.sh" ;;
  preflight) exec "${compose[@]}" exec -T avoirly-worker python -m recovery.preflight ;;
  status) exec "${compose[@]}" ps ;;
  stop-worker) exec "${compose[@]}" stop avoirly-worker ;;
  start-worker) exec "${compose[@]}" up -d --no-deps avoirly-worker ;;
  test-alert)
    if test ! -f /etc/avoirly/alerts.env; then printf '%s\n' 'SMTP alert credentials are not configured.' >&2; exit 1; fi
    exec systemctl start avoirly-alert-test.service
    ;;
  requeue-expired)
    if test -n "$("${compose[@]}" ps --status running -q avoirly-worker)"; then
      printf '%s\n' 'Stop the previous worker before recovering expired leases.' >&2
      exit 1
    fi
    exec "${compose[@]}" run --rm --no-deps avoirly-worker python -m recovery.worker --requeue-expired
    ;;
  *) printf '%s\n' 'Expected backup, full-backup, resume-recovery, monitor, preflight, status, stop-worker, start-worker, requeue-expired or test-alert.' >&2; exit 2 ;;
esac
