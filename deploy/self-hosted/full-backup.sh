#!/usr/bin/env bash
# Full pinned-cluster recovery snapshot. Briefly stop writers; always resume them.
set -euo pipefail
umask 077
test "$EUID" = 0
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
root="$(dirname "$source_dir")"
active_source="${AVOIRLY_ACTIVE_SOURCE_DIR:-$source_dir}"
runtime="${AVOIRLY_RUNTIME_DIR:-$root/runtime}"
exports="$root/recovery-exports"
exec 9>/run/lock/avoirly-full-backup.lock
flock -n 9 || { printf '%s\n' 'Another full backup is running.' >&2; exit 1; }
test -f "$runtime/.env"
test -d "$runtime/volumes/storage"
test -f /etc/avoirly/alerts.env
test ! -e /run/avoirly-recovery-paused
test ! -L "$root/recovery-work"
install -d -m 0700 "$root/recovery-work"
scratch="$(mktemp -d "$root/recovery-work/snapshot-XXXXXXXX")"
compose=(docker compose --env-file "$runtime/.env" -f "$runtime/docker-compose.yml" -f "$source_dir/deploy/self-hosted/supabase-private.yaml" -f "$source_dir/deploy/self-hosted/compose.yaml")
writers=(avoirly-web avoirly-api avoirly-worker auth storage db)
for service in "${writers[@]}"; do test -n "$("${compose[@]}" ps --status running -q "$service")"; done
paused=0
monitor_was_active=0
resume() {
  if test "$paused" = 1; then bash "$source_dir/deploy/self-hosted/resume-recovery.sh"; paused=0; fi
}
cleanup() {
  resume || true
  if test "$monitor_was_active" = 1; then systemctl start avoirly-monitor.timer; fi
  case "$scratch" in "$root/recovery-work"/snapshot-????????) rm -rf -- "$scratch" ;; *) return 1 ;; esac
}
trap cleanup EXIT
mkdir -m 700 "$scratch/snapshot" "$scratch/snapshot/runtime" "$scratch/snapshot/operations"
database_id="$("${compose[@]}" ps -q db)"
test -n "$database_id"
database_image="$(docker inspect --format '{{.Config.Image}}' "$database_id")"
data_dir="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}' "$database_id")"
test "$data_dir" = "$runtime/volumes/db/data"
release="$(docker inspect --format '{{.Config.Image}}' "$("${compose[@]}" ps -q avoirly-api)")"
docker cp "$database_id:/etc/postgresql-custom/pgsodium_root.key" "$scratch/snapshot/pgsodium_root.key"
docker cp "$database_id:/etc/postgresql-custom/." - | gzip > "$scratch/snapshot/postgresql-custom.tar.gz"
printf '%s\n' 'Briefly pausing application/Auth/Storage writers for a consistent recovery snapshot.'
if systemctl is-active --quiet avoirly-monitor.timer; then monitor_was_active=1; systemctl stop avoirly-monitor.timer; fi
if test "$monitor_was_active" = 1; then printf 'monitor\n' > /run/avoirly-recovery-paused; else printf 'none\n' > /run/avoirly-recovery-paused; fi
paused=1
"${compose[@]}" stop --timeout 30 "${writers[@]}"
test "$(docker inspect --format '{{.State.Running}}' "$database_id")" = false
test ! -f "$data_dir/postmaster.pid"
docker run --rm --network none --entrypoint pg_controldata -v "$data_dir:/verifydata:ro" "$database_image" /verifydata | grep -Eq 'Database cluster state:.*shut down$'
tar -C "$data_dir" -czf "$scratch/snapshot/postgres.data.tar.gz" .
tar -C "$runtime/volumes/storage" -czf "$scratch/snapshot/storage.tar.gz" .
cp -p "$runtime/.env" "$runtime/docker-compose.yml" "$scratch/snapshot/runtime/"
cp -a "$runtime/volumes/api" "$scratch/snapshot/runtime/api"
cp -a "$runtime/volumes/db/tls" "$scratch/snapshot/runtime/tls"
cp -p /etc/avoirly/alerts.env "$scratch/snapshot/operations/"
cp -a /etc/systemd/system/avoirly-*.service /etc/systemd/system/avoirly-*.timer "$scratch/snapshot/operations/"
git -C "$active_source" rev-parse HEAD > "$scratch/snapshot/source-commit.txt"
cp -a "$active_source/deploy/self-hosted" "$scratch/snapshot/deployment"
resume
"${compose[@]}" run --rm --no-deps --user 0:0 -e "AVOIRLY_DATABASE_IMAGE=$database_image" -e "AVOIRLY_RECOVERY_RELEASE=$release" -v "$scratch:/recovery" -v "$source_dir/scripts/seal-recovery.py:/operator.py:ro" avoirly-ops python /operator.py
install -d -m 0700 -o ubuntu -g ubuntu "$exports"
name="full-$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid | tr -d '-')"
install -m 0600 -o ubuntu -g ubuntu "$scratch/snapshot.bin" "$exports/$name.bin"
install -m 0600 -o ubuntu -g ubuntu "$scratch/report.json" "$exports/$name.json"
# Publish only after ciphertext and report are complete. Preserve older snapshots
# until a new successful snapshot exists; retention applies only to our own names.
printf '%s\n' "$name" > "$exports/latest.new"
chown ubuntu:ubuntu "$exports/latest.new"
chmod 600 "$exports/latest.new"
mv "$exports/latest.new" "$exports/latest"
find "$exports" -maxdepth 1 -type f -regextype posix-extended -regex '.*/full-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}\.(bin|json)' -mtime +13 -delete
printf '%s\n' 'Encrypted full recovery snapshot published; writers resumed.'
