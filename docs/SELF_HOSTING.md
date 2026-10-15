# Avoirly on an operator-managed server

The current hosting budget is **$0**. Keep the existing two Supabase interview
projects running. The alternative is self-hosted Supabase and Avoirly containers
on an Oracle Always Free ARM VM. The synthetic demonstration is deployed; full
hosted-pilot acceptance remains incomplete. Live extraction is enabled under the
separately authorized USD 5 initial API-testing allowance; that is not a hosting
subscription. The remaining credential is the deferred alert SMTP app password.

## Deployed demonstration — verified 15 October 2026

The user-created Casablanca VM runs Ubuntu 24.04 Minimal ARM with 2 OCPUs and
12 GB configured memory. Docker Engine and Compose were installed from Docker's
official Ubuntu repository; container logs rotate. The deployed application
release is `5b0941f01e220893aaabd2d80c5730642836c7de`, with migration `0003_phase5`
in a separate `avoirly` schema. Its [GitHub checks](https://github.com/hannhm1109/avoirly/actions/runs/38716134516)
passed: 216 Python tests, one opt-in live test skipped, six browser workflows,
production web build and all three container builds. ARM images also built and
ran on the server. Next.js is 16.4.0 following the dependency security update.

- Web: **https://avoirly.84-8-218-133.sslip.io/connexion**
- API: `https://api.84-8-218-133.sslip.io`
- Auth/Storage: `https://auth.84-8-218-133.sslip.io`

Public HTTPS certificates and API health were verified. Two confirmed synthetic
accounts signed in, reloaded and signed out in real Chromium sessions. Cookies
are HttpOnly, Secure and SameSite=Lax. Cross-account case reads, source downloads
and mutations returned 404; a foreign-origin write returned 403. A private sample
PDF uploaded and downloaded successfully. Desktop/mobile captures were inspected,
with no horizontal overflow at 390 px. The synthetic case was then deleted;
its source became inaccessible and physical object removal was independently
verified through Storage listing. These initial authentication/storage checks did
not request extraction; live extraction was verified separately afterward.

Additional hosted checks rejected missing, expired, tampered, anonymous,
wrong-issuer/audience and uninvited signed tokens. A unique synthetic pair was
then reviewed manually in Chromium, producing the expected 200.00 MAD draft.
Draft save/reload/copy/export, promises, private partial-credit proofs and audited
correction passed. Queued work persisted across an actual worker stop/restart.
That manual test case was deleted; it made no provider call or supplier message.

After private key configuration, the actual hosted Chromium flow passed again on
the deployed release: unique PDF/image upload, live extraction, source review,
200.00 MAD draft, edit/save/reload/copy/download and mobile layout. Only the
synthetic test case was deleted. Prompt 2 and the pinned model were verified in
the running worker; all preflight gates pass. The key belongs only to the worker.
The user confirmed the enforced USD 5 project limit; configured token rates and
[evaluation evidence](EVALUATION.md) are recorded separately.

Controlled hosted drills also passed: an expired lease was requeued as a new
attempt after stopping the old worker, and an actual SDK connection failure
produced a persisted failure that recovered through retry with the normal worker.
The latter used a deliberately closed local proxy for the OpenAI client only; it
was not a real provider outage. Normal processing and monitoring are healthy.

Only Caddy publishes internet-facing ports 80/443. Supabase's gateway binds to
loopback; PostgreSQL, Studio and application container ports are private.
PostgreSQL TLS is enabled. The two existing managed Supabase projects were not
changed. Oracle billing/remaining account allowances were not audited; an
Always Free-eligible shape alone does not certify the account's complete bill.

The reviewed upstream Supabase source is pinned at
`6f36fe879bebb36bf6a95083af6205c524522933`. Its Docker stack uses PostgreSQL 17,
Envoy, and modern opaque API keys. Keep this checkout immutable; copy its `docker`
directory into a private runtime directory before generating configuration.
Upstream key-generation scripts print secrets: redirect all their output to a
protected server file, never chat or CI. Do not regenerate keys on an existing
installation without a reviewed rotation procedure.

## Configuration and release order

1. Confirm Oracle Always Free capacity/remaining allowances in the home region.
   Current official limits for an Always Free tenancy are 2 A1 OCPUs and 12 GB
   memory total, and 200 GB combined boot/block storage. Trial credits do not
   establish ongoing eligibility. Idle instances can be reclaimed.
2. In the VM's **actual subnet/security list**, allow stateful TCP ingress on
   ports 80 and 443 for HTTPS. Keep database, gateway, Studio and container ports
   private. Restrict SSH to the operator where practical; preserve existing SSH
   access before changing rules. Do not assume the separately created VCN is the
   one attached to the VM.
3. Use three hostnames pointing at the VM: web, API and Supabase Auth/Storage.
   An IP-based `sslip.io` hostname avoids purchasing a domain for a demonstration.
   This is third-party DNS, with no guarantee of availability or certificate
   capacity. A changed VM IP changes these origins and requires reconfiguration.
4. In the private Supabase runtime, copy `.env.example` to `.env`, set permissions
   to 0600, and generate new secrets using the pinned upstream
   `utils/generate-keys.sh --update-env` and `utils/add-new-auth-keys.sh --update-env`.
   The second script enables ES256/JWKS configuration in the runtime Compose file.
   Set `SUPABASE_PUBLIC_URL=https://<auth-host>` and
   `API_EXTERNAL_URL=https://<auth-host>/auth/v1`, `SITE_URL=https://<web-host>`,
   `JWT_EXPIRY=900`, `DISABLE_SIGNUP=true`, `ENABLE_ANONYMOUS_USERS=false` and
   `ENABLE_PHONE_SIGNUP=false`. Clear upstream Studio's sample OpenAI key.
5. Generate/save an offline copy of the Avoirly backup encryption key. Create two
   confirmed synthetic email/password users through the admin API or tunneled
   Studio, and record their UUIDs. Never use email invitations without separate
   authorization; admin creation with explicit email confirmation needs no email.
   Create private `avoirly-documents` (10 MiB, PDF/PNG/JPEG) and `avoirly-backups`
   buckets. Add no public/browser object access policies.
6. Add these Avoirly variables to the protected runtime configuration:
   `AVOIRLY_SOURCE_DIR` (absolute checkout path), `AVOIRLY_RELEASE` (tested commit),
   `AVOIRLY_WEB_HOST`, `AVOIRLY_API_HOST`, `AVOIRLY_AUTH_HOST`,
   `AVOIRLY_PILOT_OWNER_IDS`, `AVOIRLY_METRICS_TOKEN`, `AVOIRLY_BACKUP_KEY`.
   Set `SUPABASE_RUNTIME_DIR` and generate a private PostgreSQL TLS certificate
   pair at `volumes/db/tls/server.crt` and `server.key` in that directory. The key
   must be readable only by the container's postgres UID (100 in this pinned
   image), with mode 0600. The overlay explicitly enables PostgreSQL TLS; the
   upstream default is off. `sslmode=require` encrypts this connection but does
   not establish certificate authority/hostname verification. Configure
   `verify-full` with a trusted CA for stronger verification, and track expiry
   and certificate rotation.
   Leave `AVOIRLY_OPENAI_API_KEY` and `AVOIRLY_OPENAI_MODEL` empty at a $0 API
   budget. This does not provide live document analysis. The worker's OpenAI
   configuration is separate from Studio's `OPENAI_API_KEY`.
7. Use the upstream runtime Compose file as the base,
   `deploy/self-hosted/supabase-private.yaml` second, and
   `deploy/self-hosted/compose.yaml` third, with the runtime `.env`
   supplied via `--env-file`. Compose must support `!override`/`!reset`.
   Validate with `docker compose ... config --quiet`: rendered configuration
   contains credentials and must not be printed. The overlay binds the upstream
   gateway only to loopback and removes the pooler's published database ports.
8. Start only the needed Supabase services (`db auth rest storage imgproxy meta
   studio api-gw`) and `avoirly-proxy`; skip Realtime, Functions and the pooler.
   Build the application images, run migrations explicitly using `avoirly-api`
   with `--no-deps`, then start API, worker and web. Before the first migration,
   apply `deploy/self-hosted/application-schema.sql` through the private database
   administration connection. The overlay selects the `avoirly` schema first;
   application backups do not include Supabase's unrelated public/auth schemas.
   Full server recovery also needs protected Supabase configuration
   and Auth/account backups. Never start the application
   before its schema and private buckets exist. Verify PostgreSQL TLS rather than
   removing `sslmode=require`.
9. Verify valid public HTTPS, ES256 JWTs and exact issuer, private bucket access,
   signed sessions, two-account isolation, deletion, and ARM image builds. Run
   the hosted acceptance checklist in [CONFIGURE.md](CONFIGURE.md). A successful
   sign-in does not prove live extraction or backup/restore acceptance.

The application remains in `AVOIRLY_MODE=hosted`, with the explicit
`AVOIRLY_SUPABASE_DEPLOYMENT=self_hosted` selector accepting a custom HTTPS
Supabase origin. The default is still `managed`. Signed JWT checks, allowlists,
owner guards, RLS, private storage, secure cookies and TLS requirements are retained.
Legacy service-role/anon keys are not an authentication fallback.

## Installed operations and verified backups

On this server, `/usr/local/bin/avoirly-ops` runs the Compose operations container.
The private runtime is `/home/ubuntu/avoirly-infra/runtime`; its configuration and
generated signing keys are outside Git. Systemd timers run encrypted application
backups daily at **02:00 UTC** and monitoring every **five minutes**. Both services
reported success on 15 October, including the overnight scheduled backup. The
tracked timer installer and SMTP failure hook are installed; external alert
delivery remains unconfigured pending the deferred app password.

Operator commands after connecting with SSH:

```bash
sudo /usr/local/bin/avoirly-ops monitor
sudo /usr/local/bin/avoirly-ops backup
sudo systemctl list-timers avoirly-backup.timer avoirly-monitor.timer
sudo systemctl show avoirly-backup.service avoirly-monitor.service -p Id -p Result -p ExecMainStatus
sudo journalctl -u avoirly-backup.service -u avoirly-monitor.service --since today
```

The repository also provides `deploy/self-hosted/operate.sh`. Run it with `sudo
bash` from the private checkout for `monitor`, `backup`, `preflight`, `status`,
`stop-worker`, `start-worker` or `requeue-expired`. It infers the sibling `runtime`
directory; set `AVOIRLY_RUNTIME_DIR` for a different layout. It refuses lease
recovery while the worker is running. Preflight runs inside the worker, where
the provider key belongs. Never print resolved Compose configuration.

For a fresh deployment, install the tracked operations wrapper, timers and
conditional SMTP failure hook with `sudo bash deploy/self-hosted/install-operations.sh`
from the private checkout. The Compose profile alone does not install scheduling.
SMTP configuration and delivery verification are separate; see [OPERATIONS.md](OPERATIONS.md).
Logs remain private; do not publish configuration or credentials.

Two encrypted archives were downloaded, authenticated, decrypted and restored
into separate empty PostgreSQL 17 databases, without publishing database ports:

- A new snapshot contained **one synthetic case and one PDF**. Restored table
  counts and document checksums matched; it contained no extraction, draft or ledger.
- The actual **14 October 02:00 scheduled archive** restored successfully. It
  contained zero cases/documents and two usage counters at that earlier point.

Both temporary databases and decrypted files were removed after verification.
Encrypted copies and non-secret restore reports are in the ignored local folder
`.local/remote-backups/`; ciphertext checksums matched their server copies.
Application archives retain their own names for 14 days in the private backup
bucket. Deleting a live source does not erase already retained encrypted backups.

An initial encrypted full database/Auth/configuration bundle was also copied
off the VM on 14 October. Its encryption/decryption round trip was verified.
**Full Supabase/provider restoration was not tested**, and this initial bundle is
not on the daily application backup schedule. The application restore check
does not establish full server recovery. Refresh protected configuration/Auth
copies after changes and establish recurring off-VM copies before real use.
The configuration/Auth bundle was refreshed after OpenAI configuration and release
on 15 October, authenticated by an encryption round trip and copied off the VM
with a matching SHA-256 checksum. A fresh encrypted application archive was also
copied off the VM; it was not an additional full-provider restore test.

Monitoring currently checks worker heartbeat, leases, queued deletions, failures,
reported spending and pricing; all checks passed. It has **no external notification
delivery configured**. The installed failure hook waits for protected SMTP
configuration and a delivered test. Remaining gates include alert delivery, full
provider recovery/recurring off-VM copies and participant/data-location/retention
confirmation. Keep use synthetic until those
gates pass. Security updates, pinned service upgrades and certificate/key rotation
remain operator responsibilities. See [CONFIGURE.md](CONFIGURE.md).

Studio is intentionally not exposed through public HTTPS. Access the loopback
gateway through an SSH tunnel if dashboard administration is needed. Keep server
configuration, signing keys, backup keys, login passwords and SSH keys out of Git.

Synthetic pilot credentials and a copy of the Avoirly backup key are stored
locally in `.local/pilot-access.dpapi`, encrypted for this Windows user. Run
`./scripts/show-pilot-access.ps1` locally to view the primary login, add
`-TestAccount` for the isolation test account, or `-BackupKey` to save the key in
your password manager. Never paste the output into chat. The encrypted file is
not portable to a different Windows identity; keep an independent protected copy.

References: [Oracle allowances](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[Docker installation](https://docs.docker.com/engine/install/ubuntu/),
[Supabase self-hosting](https://supabase.com/docs/guides/self-hosting/docker),
[Caddy HTTPS](https://caddyserver.com/docs/automatic-https),
[IP-based DNS](https://sslip.io/).
