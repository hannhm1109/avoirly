#!/usr/bin/env bash
# Install timers and the alert hook; SMTP credentials are configured separately.
set -euo pipefail
umask 077
if test "$EUID" -ne 0; then printf '%s\n' 'Run this installer with sudo bash.' >&2; exit 1; fi
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if ! [[ "$source_dir" =~ ^/[A-Za-z0-9_./-]+$ ]]; then printf '%s\n' 'Use a deployment path without spaces or shell characters.' >&2; exit 1; fi
test -f "$source_dir/scripts/notify-operator.py"
temporary="$(mktemp -d)"
trap 'rm -f "$temporary/avoirly-ops" "$temporary/avoirly-backup.service" "$temporary/avoirly-monitor.service" "$temporary/avoirly-backup.timer" "$temporary/avoirly-monitor.timer" "$temporary/avoirly-alert@.service" "$temporary/avoirly-alert-test.service"; rmdir "$temporary"' EXIT
printf '#!/usr/bin/env bash\nexec bash %q "$@"\n' "$source_dir/deploy/self-hosted/operate.sh" > "$temporary/avoirly-ops"
install -m 0755 "$temporary/avoirly-ops" /usr/local/bin/avoirly-ops
install -d -m 0700 /etc/avoirly /var/lib/avoirly-alerts
for operation in backup monitor; do
  cat > "$temporary/avoirly-$operation.service" <<UNIT
[Unit]
Description=Avoirly $operation
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service
OnFailure=avoirly-alert@%n.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/avoirly-ops $operation
TimeoutStartSec=15min
PrivateTmp=true
NoNewPrivileges=true
UNIT
  install -m 0644 "$temporary/avoirly-$operation.service" "/etc/systemd/system/avoirly-$operation.service"
done
cat > "$temporary/avoirly-backup.timer" <<'UNIT'
[Unit]
Description=Daily encrypted Avoirly application backup
[Timer]
OnCalendar=*-*-* 02:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
cat > "$temporary/avoirly-monitor.timer" <<'UNIT'
[Unit]
Description=Avoirly monitor every five minutes
[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
for timer in backup monitor; do install -m 0644 "$temporary/avoirly-$timer.timer" "/etc/systemd/system/avoirly-$timer.timer"; done
for template in 'avoirly-alert@.service' 'avoirly-alert-test.service'; do
  if test "$template" = 'avoirly-alert@.service'; then args='%i'; else args='avoirly-monitor.service --test'; fi
  cat > "$temporary/$template" <<UNIT
[Unit]
Description=Avoirly operator email alert
After=network-online.target
Wants=network-online.target
ConditionPathExists=/etc/avoirly/alerts.env
[Service]
Type=oneshot
EnvironmentFile=/etc/avoirly/alerts.env
ExecStart=/usr/bin/python3 $source_dir/scripts/notify-operator.py $args
TimeoutStartSec=60
PrivateTmp=true
NoNewPrivileges=true
UNIT
  install -m 0644 "$temporary/$template" "/etc/systemd/system/$template"
done
systemd-analyze verify /etc/systemd/system/avoirly-backup.service /etc/systemd/system/avoirly-monitor.service /etc/systemd/system/avoirly-alert@.service /etc/systemd/system/avoirly-alert-test.service
systemctl daemon-reload
systemctl enable --now avoirly-backup.timer avoirly-monitor.timer
cat > /etc/systemd/system/avoirly-full-backup.service <<'UNIT'
[Unit]
Description=Avoirly encrypted full server recovery snapshot
After=network-online.target docker.service
Requires=docker.service
OnFailure=avoirly-alert@%n.service
[Service]
Type=oneshot
ExecStart=/usr/local/bin/avoirly-ops full-backup
ExecStopPost=/usr/local/bin/avoirly-ops resume-recovery
TimeoutStartSec=15min
PrivateTmp=true
NoNewPrivileges=true
UNIT
cat > /etc/systemd/system/avoirly-full-backup.timer <<'UNIT'
[Unit]
Description=Daily Avoirly full recovery snapshot
[Timer]
OnCalendar=*-*-* 03:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemd-analyze verify /etc/systemd/system/avoirly-full-backup.service
systemctl daemon-reload
systemctl enable --now avoirly-full-backup.timer
printf '%s\n' 'Timers and failure-alert hook installed. SMTP delivery still requires protected configuration and an authorized test.'
