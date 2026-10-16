# Phase 4 — your configuration checklist

The current $0 hosting path is described in [SELF_HOSTING.md](SELF_HOSTING.md).
It keeps the user's existing Supabase projects available. The managed
Supabase/Render instructions below remain an alternative; they are not deployed.

The code and local tests can be completed without your accounts. A hosted pilot
is **not ready until the live gates below pass**. Deployment is operator-controlled;
the repository does not automatically create paid accounts. Configured SMTP sends
operational alerts only. Supplier email sending is not implemented.

The deployed path uses self-hosted Supabase Auth + PostgreSQL + private Storage
and Docker containers on Oracle. The alternative below uses Render web, API and
worker containers, plus scheduled backup and monitoring jobs. Check the
providers' current prices before creating resources. The initial region in the
Render template is Frankfurt; choose a compatible Supabase region and confirm
the data-location requirements for your intended pilot before uploading real files.

## 1. Supabase project

Create a dedicated managed Supabase project, using PostgreSQL 17 or an older
supported major (the backup container contains PostgreSQL 17 client tools).
Save the database password in your password manager.

- Disable public user signups and anonymous sign-in. This is an invitation-only pilot.
- Use an asymmetric JWT signing key (**ES256 or RS256**). Legacy HS256 user tokens
  are intentionally rejected. Set the access-token lifetime to 15 minutes.
- Create **two synthetic test users** using the dashboard's user administration.
  Create confirmed email/password accounts; arrange their credentials privately.
  The initial app implements password sign-in, not an email invitation/callback or
  password-reset flow. Dashboard account management is the operator's responsibility.
- Record both users' UUIDs for the pilot allowlist. User UUIDs are not API keys.
- Create private buckets `avoirly-documents` and `avoirly-backups`.
  `avoirly-documents`: maximum 10 MiB, MIME types `application/pdf`, `image/png`,
  `image/jpeg`. `avoirly-backups`: `application/octet-stream`, with a bucket and
  plan upload limit large enough for an encrypted complete backup.
- Do **not** add public/authenticated object policies granting bucket access.
  Downloads go through the owner-checked API. The server secret API key handles
  object access; it never enters browser code.
- Obtain the project HTTPS URL, **publishable** API key (`sb_publishable_...`),
  and a server **secret** API key (`sb_secret_...`).
- Obtain a direct or **session pooler** PostgreSQL connection. Do not use a
  transaction-pooler URL for migrations or snapshot backups. Convert its scheme to
  `postgresql+psycopg://` and include `?sslmode=require` (or stronger verification).
  Percent-encode special characters in credentials; preserve the pooler username.

Use a dedicated project/database. Migration `0002_phase4` enables default-deny
row-level security on every application table and revokes browser-role grants.
The API/worker connection must be the table owner or a reviewed privileged backend
role, because only the Python API implements user-level access to these tables.
Do not expose that database connection to the frontend.

## 2. Render services

Connect the GitHub repository and review [render.yaml](../render.yaml). It defines
three continuously running services plus two cron jobs; these can incur charges.
Automatic deployment on push is disabled. Reserve/confirm the API and web HTTPS
URLs, then supply them as origins (no trailing slash or path).

The Blueprint prompts for configuration. Deploy the API first: its explicit
pre-deploy command runs Alembic. Then start the worker and web service. If the
worker starts before the first migration completes, restart it after migration.
Set the Auth site URL in Supabase to the final web origin. Do not enable wildcard
redirects. No provider credentials are needed during Docker image builds.

| Variable                         | Set on                              | Value                                                |
| -------------------------------- | ----------------------------------- | ---------------------------------------------------- |
| `AVOIRLY_MODE`                   | API, worker, web, backup            | `hosted` (already in template/images)                |
| `DATABASE_URL`                   | API; inherited by worker/backup     | TLS PostgreSQL psycopg URL                           |
| `AVOIRLY_WEB_ORIGIN`             | API; inherited elsewhere            | Final `https://…` web origin                         |
| `AVOIRLY_API_ORIGIN`             | API; inherited elsewhere            | Final `https://…` API origin                         |
| `SUPABASE_URL`                   | API; inherited by worker/web/backup | `https://<project>.supabase.co`                      |
| `SUPABASE_SECRET_KEY`            | API; inherited by worker/backup     | Server secret API key                                |
| `SUPABASE_PUBLISHABLE_KEY`       | Web only                            | Publishable key                                      |
| `AVOIRLY_PILOT_OWNER_IDS`        | API; inherited by worker/backup     | Comma-separated invited UUIDs                        |
| `AVOIRLY_METRICS_TOKEN`          | API; inherited by operators         | Generated by Render                                  |
| `OPENAI_MODEL`                   | API; inherited by worker            | Explicit compatible model identifier                 |
| `OPENAI_API_KEY`                 | Worker only                         | Your project's OpenAI key                            |
| `AVOIRLY_INPUT_USD_PER_MILLION`  | Worker                              | Current selected-model input rate                    |
| `AVOIRLY_OUTPUT_USD_PER_MILLION` | Worker                              | Current selected-model output rate                   |
| `AVOIRLY_ALERT_USD_24H`          | Monitor                             | Your reported-usage alert threshold                  |
| `AVOIRLY_BACKUP_KEY`             | Backup only                         | Base64-encoded 32 random bytes; save an offline copy |
| `AVOIRLY_BACKUP_BUCKET`          | Backup                              | `avoirly-backups`                                    |
| `AVOIRLY_BACKUP_RETENTION_DAYS`  | Backup                              | `14` initially; confirm for the pilot                |

Generate the backup key locally with Python, save it in your password manager,
and enter it directly in Render's backup service settings:

```powershell
./backend/.venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Remove `AVOIRLY_LOCAL_OWNER_ID` from every hosted service.** Hosted startup
rejects a developer identity. Do not set any credential as `NEXT_PUBLIC_*`.
Enter secrets directly in provider settings; do not paste them into Git or chat.
Share only the project URL, final app URLs and configuration-completion status
when asking for help with the next step.

Default daily limits per user: 20 new cases, 40 analysis attempts, 60 successful
upload actions, 120 review saves and 120 manual tracking actions. UTC midnight resets the daily window. Case
deletion does not reset counters. One active analysis per owner and at most three
attempts per revision are enforced. Adjust identical `AVOIRLY_DAILY_*` values on
the API if needed; keep `AVOIRLY_MAX_ATTEMPTS` consistent on API and worker.

## 3. OpenAI and measured extraction

Choose a model supporting Chat Completions, Structured Outputs, PDF and image
inputs in your account. A model name is deliberately not selected automatically.
Verify current rates and set provider-side project spending controls in addition
to the application's quotas and alert. Reported-usage estimates are not invoices:
failed/unreported/discarded calls, cache discounts and other billing details can differ.

The Oracle deployment uses `gpt-5.4-mini-2026-03-17`, with configured rates of
USD 0.75/million input and USD 4.50/million output tokens. The user confirmed a
USD 5 enforced monthly project limit and authorized USD 5 total initial tests.
See [the recorded evaluation](EVALUATION.md); estimates do not certify account
balance or billing enforcement. For a new configuration, run the existing opt-in
live test with synthetic documents:

```powershell
$env:AVOIRLY_LIVE = '1'
# Configure OPENAI_API_KEY and OPENAI_MODEL privately in this shell first.
./backend/.venv/Scripts/python.exe -m pytest backend/tests/test_live.py -q
```

If the live test module's name changes, select the `live` marker instead. Run
`python -m recovery.preflight` in the configured worker environment. This checks
configuration/connectivity, private storage, signing keys, schema and worker
liveness; it does not replace a successful extraction or labeled evaluation.

## 4. Backups and alerts

- Enable Render failure notifications for both cron jobs and deployment failures.
  Confirm the notification recipient and test delivery yourself.
- The monitor runs every five minutes. It exits nonzero for missing worker
  heartbeat, expired leases, queued deletions, repeated failures, unpriced usage,
  or estimated reported spend above your selected threshold.
- The backup job runs daily at **02:00 UTC**. It copies source objects against a
  PostgreSQL snapshot, encrypts the complete archive with AES-256-GCM, uploads it
  to the private backup bucket and removes only its own expired archive names
  after a successful new upload. Missing objects make the backup fail, not succeed
  partially. A deletion racing the snapshot can require retrying the backup.
- Save the backup encryption key outside Render. Rotation requires retaining old
  keys for old archives. A lost key makes its encrypted backups unrecoverable.
- Keep an encrypted archive copy outside the Supabase project as well. A separate
  bucket in the same project does not protect against losing the whole project.
- Provider-managed database snapshots do not replace document-object backups.
  Confirm their retention separately; 14 days in the job does not change provider
  backup, log, or account retention settings.

Follow [OPERATIONS.md](OPERATIONS.md) to decrypt and restore a downloaded backup
into an isolated empty database. Record the date, schema, counts, source checksums
and draft verification. Never test restore by overwriting production.

## 5. Final private-pilot gates

Use synthetic data until these are all checked:

- [x] Container builds and deploys pass; current schema is `0003_phase5`.
- [x] Both invited users can sign in, refresh the page and sign out over HTTPS.
- [x] Session cookies are HttpOnly, Secure and SameSite=Lax; sessions are not cached.
- [x] User B cannot list/read/change/download user A's case, even using its URL.
- [x] An uninvited account and an expired/invalid token are rejected.
- [x] A complete real-browser upload → live extraction → review → draft/export works.
- [x] Worker restart/expired-lease recovery and failed extraction recovery are verified.
- [x] Private-bucket access and deletion (including delayed cleanup) are verified.
- [x] An encrypted scheduled backup is restored and verified in a separate environment.
- [x] SMTP configuration and shared failure-hook wiring verified; one test accepted by Gmail
      and receipt confirmed by the operator.
- [x] Actual monitoring/backup failure-alert delivery verified on 16 October;
      both emails received and normal jobs restored.
- [x] Full PostgreSQL/Auth/Storage/configuration restore from off-VM ciphertext
      verified on an internal network; recurring snapshot/copy tasks installed.
- [x] Synthetic pilot access, Oracle/Windows data locations, manual case deletion
      and 14-day backup retention recorded and reflected on the privacy page.
- [x] About 20 labeled synthetic/consented pairs are evaluated; report sample size,
      supported coverage, review rate, false drafts, latency and cost. Zero false
      drafts in this set is a gate, not a production-wide accuracy claim.
- [x] Public support/privacy contact avoirly.support@gmail.com supplied, configured
      and verified on the live page; alert recipient updated to that inbox.
- [ ] New support-account SMTP sender app password saved, installed and tested.
- [ ] Intended real participants' document authorization/provider data controls
      confirmed. Real-participant access remains closed.

Checked hosted gates were verified on 14–15 October 2026 against the self-hosted
Oracle deployment. [SELF_HOSTING.md](SELF_HOSTING.md) records the release, evidence
and restore limits; these checks do not describe a managed Supabase/Render deployment.
Real PDF/image extraction and the complete hosted browser flow passed on the
deployed release. An expired lease and a controlled SDK network failure recovered
through new attempts on isolated synthetic cases. The [evaluation](EVALUATION.md)
records 20 development pairs plus five fresh held-out pairs, with zero false
drafts, all nine ambiguous cases blocked and one supported scan requiring review.
[PILOT_READY.md](PILOT_READY.md) lists the remaining credential and operational work.

Only after all these gates pass is Phase 4's **hosted pilot acceptance** complete.
Phase 5 adds manual recovery tracking; see [RECOVERY_TRACKING.md](RECOVERY_TRACKING.md).
Actual email sending and Phase 6 subscriptions are separate later work.
