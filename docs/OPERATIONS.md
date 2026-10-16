# Avoirly operations

This runbook covers the deployed Phase 4/5 application. It does not certify
acceptance for real supplier data. Complete
[CONFIGURE.md](CONFIGURE.md) before accepting real documents. Keep operator
credentials and all backup artifacts out of Git; `.private/` is ignored but may
still sync through OneDrive. Use an appropriately protected directory.

## Deploy and migrate

CI runs Python/PostgreSQL tests, a production web build, browser regressions and
three container builds. Require a successful run for the exact deployed commit.
The Render template disables automatic deployments. Record the commit and image
used for each release; deploy API/migration before worker and web.

1. Before a database change, stop uploads and workers, create and verify a complete
   backup using the currently deployed version, and save the previous image tag.
2. Run `alembic -c backend/alembic.ini upgrade head` with the backend database
   credential. The API checks the exact schema on startup; it never creates tables.
3. Start the API, worker and web. Check `/api/v1/health` and the protected metrics.
4. Run `python -m recovery.preflight` in the worker environment. It checks schema,
   private storage, signing-key availability, heartbeat and configuration without
   printing credentials. It does not perform a live model extraction.
5. Verify a synthetic case in the browser. Record any failed gate before expanding
   access. Never substitute a fake model result for a live acceptance result.

Migration `0002_phase4` enables RLS and removes browser-role table grants. Automatic
downgrade is deliberately unavailable. Roll back application code only if it is
compatible with the current schema; otherwise perform a reviewed isolated restore.

## Monitor and recover processing

On the self-hosted deployment, install/update the tracked scheduler and failure
hook from the private checkout:

```bash
sudo bash deploy/self-hosted/install-operations.sh
sudo /usr/local/bin/avoirly-ops preflight
sudo /usr/local/bin/avoirly-ops monitor
```

The installer creates daily 02:00 UTC backup and five-minute monitor timers.
Both services use the same conditional SMTP failure hook. SMTP is configured
on the current host; the single authorized test was accepted by Gmail SMTP on
15 October 2026, and the operator confirmed receipt. On a new host,
alert services are skipped until `/etc/avoirly/alerts.env` exists. A passing monitor
does not establish delivered notification evidence.

An operator must install a root-owned mode-0600 `/etc/avoirly/alerts.env` containing
`AVOIRLY_SMTP_USER`, `AVOIRLY_SMTP_PASSWORD` (a dedicated app password), and
`AVOIRLY_ALERT_EMAIL`. The current sender uses Gmail TLS SMTP on port 465.
Enter values through protected tooling, never a command line, public file or chat.
The Windows helper
in [PILOT_READY.md](PILOT_READY.md) only collects a secret locally; it does not
configure SMTP on the host.

After configuration, run `sudo /usr/local/bin/avoirly-ops test-alert` only with
authorization for that destination, then confirm delivery. One test to the
privately supplied operator address was authorized for this deployment;
that test was accepted by SMTP and the operator confirmed receipt. The test
service uses the same sender as failure hooks,
with static content and no document data, logs or credentials. Real failure
notifications are coalesced per service for one hour; a test does not suppress
real failure alerts. Unit wiring and mocked SMTP tests are verified, but actual
monitor/backup failure delivery remains an acceptance gate.

`GET /ops/metrics` requires `Authorization: Bearer <AVOIRLY_METRICS_TOKEN>`.
It exposes counts, worker liveness and reported token costs, never documents.
Do not put this token into URLs, browser code, screenshots or logs. The five-minute
monitor cron exits nonzero on unhealthy conditions; provider failure notifications
must be configured and tested by the operator.

- Missing heartbeat: check the worker deployment, database connectivity and settings.
  Restart the worker after resolving the cause. Do not manually mark jobs successful.
- Expired leases: after checking the old process has stopped, run
  `python -m recovery.worker --requeue-expired` in the worker environment. This
  explicit recovery command is capped at three attempts per revision. Resume the
  normal worker afterward. Review repeated failures before rerunning; owner quotas
  also limit new requests. The polling loop does not automatically requeue leases.
- Pending source deletions: restore storage connectivity and run the worker. The
  deletion outbox retries cleanup; a case stays deleted while files await cleanup.
- Extraction failure: inspect the redacted failure code, model configuration and
  provider status. Never log source text or raw provider errors to troubleshoot.
- Cost alerts: compare reported estimates with provider billing. Only successfully
  persisted extraction usage is recorded; retries, failed/discarded calls, caching
  and provider pricing rules can differ. This is an estimate and alert, not a billing
  ledger or hard provider spending cap. Configure provider budgets separately.

Daily quota counters retain owner UUIDs independently of case deletion, preventing
delete/recreate quota bypass. They contain no source content. Account removal and
operational-record retention require an operator-reviewed database action; there
is no automated account deletion/retention workflow in this pilot.

## Back up

The daily `python -m recovery.backup_job` job creates one consistent database and
document snapshot, encrypts it with AES-256-GCM, then uploads to the separate private
backup bucket. Retention runs only after a successful upload. Save the encryption
key separately and copy encrypted archives outside the Supabase project.

For a manual local snapshot after migration:

```powershell
. ./scripts/local-env.ps1
$env:AVOIRLY_PG_BIN = Join-Path $PWD '.local/pgsql/bin'
./backend/.venv/Scripts/python.exe -m recovery.backup create --out .private/manual-backup
```

Choose a new destination each time. This command creates an **unencrypted** snapshot;
keep it private and encrypt it before external storage. The scheduled job does that
automatically. A missing/deleted source causes backup failure rather than a partial
success. Retry after concurrent deletion settles.

The snapshot covers application tables and referenced document objects, including
manual recovery records, sent-draft snapshots and credit evidence. It does
not back up Supabase Auth accounts, provider configuration, signing keys or secrets.
Maintain those separately. A source upload interrupted before its database commit
can leave an unreferenced storage object; periodically reconcile old bucket objects
against `documents.storage_key`, `recovery_evidence.storage_key` and
`deletion_tasks.storage_key` while uploads are
paused. Review candidates before removal; no automatic orphan purge is implemented.

## Verify an encrypted restore

Use only trusted operator-created archives. Download one encrypted `.bin` backup
to a private directory and inject its original `AVOIRLY_BACKUP_KEY` privately.
Create an isolated **empty PostgreSQL database** with the supported major version.
Set `AVOIRLY_RESTORE_DATABASE_URL` to that database, never the active application.

```powershell
$env:AVOIRLY_PG_BIN = Join-Path $PWD '.local/pgsql/bin'
./backend/.venv/Scripts/python.exe -m recovery.backup_job --decrypt .private/backup.bin --out .private/verified.tar
./backend/.venv/Scripts/python.exe -c "import tarfile; t=tarfile.open('.private/verified.tar'); t.extractall('.private/restore-check', filter='data'); t.close()"
./backend/.venv/Scripts/python.exe -m recovery.backup verify --archive .private/restore-check/snapshot --storage .private/restore-check/documents
```

Use fresh paths for each drill. Decryption authenticates the complete ciphertext
before publishing the output archive. Verification checks dump/object checksums,
refuses a nonempty target, restores in a single database transaction and checks
record counts and source hashes. If it fails, preserve the failure evidence and
use a fresh empty target after investigation; do not bypass the refusal.

Record the date, deployed commit, schema, object/row counts and result. Separately
start the application against this isolated database/storage and confirm a known
draft, source preview and owner isolation. The automated synthetic test checks the
expected `200.00 MAD` draft after a real PostgreSQL dump/restore.

Production cutover is a separate reviewed operation: pause writes, reconcile any
post-snapshot changes and deletions, restore objects under their original keys to
a new private bucket, reapply access settings and verify users before switching
origins. Historical backups can contain deleted cases. Keep the deletion record
outside the restored snapshot and reapply it before reopening access. Restore is
never an excuse to silently reactivate deleted data.

## Retention and privacy

The initial encrypted-backup retention is 14 days; confirm it with participants.
Live case deletion removes active records and schedules file cleanup. Retained
backups age out on successful backup-job runs. Provider-managed backups and logs
have their own retention; document those separately. Source files and extraction
are sent to the configured model provider; confirm the provider's data controls.
Update the displayed privacy information with actual operator contact and agreed
retention before the real-data pilot. No legal-compliance certification is claimed.

## Phase 5 migration

Current schema: `0003_phase5`. Stop writes and run a complete snapshot using the
previously deployed Phase 4 code before upgrading. The new migration preserves
existing case statuses and content, expands allowed statuses and creates two
default-deny RLS tables. Deploy API, worker, web and backup job from the same release.
Never run the new snapshot creator against an unmigrated Phase 4 database.

The current restore verifier also accepts Phase 4 snapshots that have no recovery
tables. After checking a historical restore in isolation, explicitly upgrade its
schema before using Phase 5 code. Phase 5 downgrade refuses to discard evidence.
Financial tracking idempotency keys are retained for the case's lifetime; do not
remove them in a general expired-key cleanup. Case deletion removes them together
with the manual ledger and queues all credit evidence for physical removal.
