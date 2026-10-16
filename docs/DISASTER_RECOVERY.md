# Full server recovery

This runbook covers the Oracle self-hosted deployment. Application-only backups
remain useful for individual database restores; they do not include Auth or
server secrets. Full recovery uses a separate encrypted snapshot.

## Snapshot contents and schedule

`avoirly-full-backup.timer` runs daily at **03:00 UTC**, after the application
backup at 02:00 UTC. It briefly stops web/API/worker, Auth, Storage and PostgreSQL
to copy a cleanly shut down cluster. Expect a short maintenance interruption,
typically tens of seconds on this small synthetic deployment. It resumes the
services before encrypting the bundle. A protected maintenance marker, exit trap
and systemd `ExecStopPost` attempt to resume services after failure. Monitor
scheduling pauses during the maintenance window.

The bundle includes:

- The entire PostgreSQL data directory, including Auth accounts, application
  tables, Storage metadata and database roles.
- The complete PostgreSQL custom configuration volume, including its pgsodium
  encryption key, plus the database TLS files.
- The Storage filesystem containing source files and credit evidence. Older
  application archives are excluded so nesting cannot extend their retention.
- Runtime environment, generated Supabase Compose configuration, gateway/signing
  configuration, deployment overlays, source commit, SMTP settings and systemd units.

The snapshot records the exact database and application image tags. It is a
physical PostgreSQL snapshot: restore with the same pinned database image and
compatible ARM architecture. This is not a cross-version database migration.
Git source and Docker images must remain available separately. Caddy's ACME
volume, OS packages, Oracle networking/IAM and the Windows SSH identity are not
included; rebuild those separately. Public certificates can be reissued after
the intended hostnames and DNS are restored.

The pinned Storage layout uses `stub/stub/avoirly-backups` for the excluded
application archive bucket. Recheck that layout on a Supabase upgrade. The full
restore clears only that bucket's historical object metadata in the isolated
restored database; source/proof objects and their metadata are preserved. A new
application backup repopulates the empty private backup bucket after cutover.

AES-256-GCM protects the complete archive. Publication requires an authenticated
decryption round trip. The manifest hashes every snapshot file. The plaintext
working directory is root-only and removed afterward. Reports contain checksums,
counts and image tags, never secret values. Keep the backup key independently in
a password manager: losing it makes the archives unusable. Rotation requires
retaining the original key for older archives.

## Automatic copy outside the server

The Windows task **Avoirly encrypted recovery sync** downloads ciphertext and
non-secret reports over SSH. It verifies both SHA-256 and byte length before
acknowledging success to the server. It does not decrypt backups on Windows.

The destination is `%LOCALAPPDATA%\Avoirly\Recovery`, outside OneDrive, with access
limited to the current Windows user. The private SSH copy and installed script
are in `%LOCALAPPDATA%\Avoirly\Operator`. Task triggers are daily **07:00 local
time**, sign-in, and every four hours. The operator must be logged in; the PC and
network must be available. Missed runs start when possible. This is an automated
off-VM copy, not an always-on independent cloud backup service. A compromised
operator account can still access or delete it; the copy is not immutable.

Install or update it from PowerShell, supplying the private key's path:

```powershell
./scripts/install-recovery-sync.ps1 -IdentityFile 'C:\path\to\oracle.key'
Start-ScheduledTask -TaskName 'Avoirly encrypted recovery sync'
Get-ScheduledTaskInfo -TaskName 'Avoirly encrypted recovery sync'
Get-Content "$env:LOCALAPPDATA\Avoirly\Recovery\sync-status.json"
```

The host monitor fails when the full snapshot reaches **30 hours** or the
successful copy acknowledgement reaches **36 hours**. Missing/invalid metadata
also fails. Its normal failure-email hook then notifies the private operator
address. A recent acknowledgement indicates verified transfers at that time,
not permanent availability of the Windows copy. Host monitoring cannot send an
alert if the whole VM or its network is down; an external availability monitor
is not installed.

Both server exports and Windows copies retain their own named full snapshots
for **14 days**, purging only after a successful new snapshot/copy. Application
archives have separate 14-day bucket retention. Persistent outages can delay
purging; inspect failures. Daily full snapshots imply up to roughly one day of
data loss, plus any off-server copy delay; this is an operating target, not an
RPO/RTO guarantee.

Historical operator-created application/configuration test ciphertext was moved
from the ignored workspace to `Recovery\Legacy`. The copy task expires those
known filenames using their original UTC dates after a successful sync. This
does not control any copies previously retained by OneDrive's own version or
recycle-bin policies. The scheduled recovery destination itself is outside
OneDrive.

Host commands from the private checkout:

```bash
sudo bash deploy/self-hosted/install-operations.sh
sudo systemctl start avoirly-full-backup.service
sudo /usr/local/bin/avoirly-ops monitor
sudo systemctl list-timers avoirly-full-backup.timer
sudo systemctl show avoirly-full-backup.service -p Result -p ExecMainStatus
```

## Isolated restoration drill

Use only trusted operator-created archives. Copy a verified Windows ciphertext
back to a protected host staging path. Supply the independently saved backup key
and the two synthetic account credentials through stdin to
`scripts/verify-server-recovery.py`; never put them in shell arguments or logs.
Its `--source` must be a checkout directly inside the operator infrastructure
root. The private JSON input contains `accounts` (email/password), `backup_key`,
`ops_image`, `canary_base64` (UTF-8 JSON case-detail encoded as base64), and
`source_sha256` for the known PO and invoice. The synthetic canary must exist in
the selected snapshot. Preserve its expected detail and source hashes privately
before taking that snapshot. Do not use real supplier data for this drill.

The helper authenticates/decrypts, checks the manifest, then starts a temporary
database, Auth, REST, Storage, gateway, API, web and TLS proxy on an **internal
Docker network with no host ports**. Original hostnames resolve only inside that
network. Outbound access is unavailable, and no extraction worker is started.
The temporary TLS certificate is for the drill only. SMTP configuration is
verified as a backed-up file; recovery does not send another email.

The probe verifies both restored password logins, JWT acceptance, a known draft
and financial ledger, source/proof hashes, private buckets, owner isolation,
unauthenticated rejection, and web login/gateway/logout with secure cookies.
Afterward it removes the temporary containers, network and decrypted files.
The non-secret report is `recovery-exports/restore-report.json`; failure logs
remain root-only and must never be pasted publicly. A failed check must be
investigated and rerun, not ignored.

## Replacing a lost server

An isolated restoration is not a production cutover. For an actual loss:

1. Preserve the latest verified ciphertext, original key, image tags and Git
   release. Establish the last known successful snapshot/copy time.
2. Provision a compatible clean host and private network. Restore firewall,
   Docker, SSH access and the protected infrastructure layout. Keep public app
   traffic closed. Never overwrite an existing live database as a drill.
3. Authenticate/decrypt to a protected directory. Restore the physical cluster,
   custom PostgreSQL volume and its ownership, TLS files, Storage filesystem and
   runtime/signing configuration using the original pinned database image.
   Remove the excluded application archive bucket's historical object metadata
   from the restored database, as the verification helper does, before Storage
   starts. Do not run that cleanup against a surviving live database.
4. Review restored credentials, host paths, origins and operator settings.
   Reinstall the tracked operations units. Keep jobs, mail and provider calls
   disabled while checking recovered state.
5. Run the isolated service probe and reconcile changes/deletions after the
   snapshot. Reapply deletions before reopening access; a historical restore
   must not silently reactivate deleted cases.
6. Restore or change DNS/origins intentionally, obtain public certificates,
   verify authentication, private downloads, ownership, preflight and monitoring,
   then reopen access. Reconfigure and verify the Windows copy task.

A new Oracle VM, DNS failover and production cutover have not been rehearsed.
The verified drill covers restoration of the backed-up services in isolated
containers on the existing host. Keep that distinction in readiness claims.
