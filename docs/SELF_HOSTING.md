# Avoirly on an operator-managed server

The current hosting budget is **$0**. Keep the existing two Supabase interview
projects running. The alternative is self-hosted Supabase and Avoirly containers
on an Oracle Always Free ARM VM. This is a deployment option, not completed
hosted-pilot acceptance. Live extraction still requires a separately authorized
model/API budget; do not insert a fake key or silently select a model.

## Current preparation

On 13 October 2026, SSH access to the user-created Casablanca VM was verified:
Ubuntu 24.04 Minimal ARM, 2 OCPUs, 12 GB configured memory, approximately 43 GB free
disk. Docker Engine and Compose were installed from Docker's official Ubuntu
repository. Docker logs use rotation. No paid resource or extraction call was
created by this preparation.

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
   Full server recovery also needs separately protected Supabase configuration
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

## Operations still required

Self-hosting replaces the provider's operating services with the operator's work:
security updates, pinned image upgrades, daily encrypted backups, an off-VM copy,
monitoring, tested restore and notification delivery. The `avoirly-ops` profile
supports `python -m recovery.backup_job` and `python scripts/check-monitor.py`;
it does not install a scheduler or notifications. These remain pilot gates.

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
