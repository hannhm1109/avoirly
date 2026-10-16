# Avoirly build progress

Brand: **Avoirly — Spot invoice discrepancies. Simplify supplier claims.**

Current checkpoint: the 15 October release, live evaluation and hosted acceptance
checks are recorded at the end of this file. Earlier sections are dated historical
checkpoints, including their then-pending configuration.

## Phase 1 implementation

Implemented the local CLI, exact extraction contracts, Decimal domain conversion,
source/file validation, deterministic matching and calculations, French/English
drafts, guarded synchronous workflow, report export, local history duplicate checks,
synthetic examples, and a resolved dependency lockfile. Source document text is
retained in SPEC.md; this progress file records implementation choices separately.

Verification on 26 September 2026, Windows, Python 3.14.3:

- Offline acceptance tests: **127 passed**.
- Live extraction test: **1 skipped**, intentionally opt-in.
- Synthetic fixture command: `CLAIM_DRAFTED`, **200.00 MAD potential credit excluding tax**.
- Default French email and JSON report generated in `output/demo/`; English example in `output/demo-en/`.
- Official SDK parsing and retry behavior checked using a mocked HTTP transport.
- Lockfile resolved and installed; code formatted and lint passed. Wheel and source distribution built successfully in `dist/`.

No API key or model was configured, so no live PDF or image extraction was tested.
The selected model's actual capability and account access remain unverified. The
Phase 1 offline gate passes; live verification remains pending configuration.

## Explicit implementation choices and limits

- Exact-SKU matches with changed descriptions require review. This conservative
  choice catches possible pack/model changes at the cost of more review cases.
- Every extraction warning blocks drafting until resolved; no ambiguity is ignored.
- Duplicate detection covers supplied `--previous-report` history and identical
  inputs. Phase 1 cannot discover all invoices for an owner without the Phase 2 database.
- Same output directory means rerun of one local case; other cases need distinct directories.
- Pair confirmations record actor, reason, and extraction revision hash. Audited
  corrections, manual mappings, durable state transactions and owner checks are Phase 2.
- No automatic model selection, email sending, tax-credit accounting, or recovery claims.

## Phase 2 implementation

Authorized after the Phase 1 handoff and implemented on 27 September 2026.

- FastAPI routes under `/api/v1` for cases, uploads, analysis, corrections, draft
  edits, retries, closure, deletion, document content, and audit events.
- PostgreSQL schema with 11 tables and a frozen Alembic migration. UUIDs, JSONB
  snapshots, NUMERIC amounts, unique constraints, and the active-job partial index.
- Private validated uploads, server-resolved local ownership, version conflicts,
  atomic state/audit changes, and immutable extraction/comparison/draft versions.
- Durable polling jobs, leases, heartbeats, explicit expired-job requeue, extraction
  checkpoints, and comparison persistence before drafting.
- Persistent owner/route idempotency keys; concurrent duplicate requests create
  one job. Changed payloads under the same key return 409.
- Owner-scoped duplicate file and invoice checks, including supplier tax ID aliases
  and earlier cases that still need review.
- Audited corrections and revision-bound pairing confirmations. Manual mappings
  must satisfy the same deterministic matching rules; they cannot bypass blockers.
- Revision changes or closure cancel active draft work. Deletion revokes access and
  removes content transactionally, then deletes source files through a durable outbox.

Verification on Windows, Python 3.14.3, real PostgreSQL 17:

- **153 tests passed**, comprising 127 core/adapter/CLI checks and 26 PostgreSQL
  backend checks. **1 live OpenAI test skipped** because credentials/model remain unset.
- Real migrations applied; Alembic's schema-drift check passed.
- Concurrent Analyze requests create one job; two workers cannot claim the same job.
- API recreation preserves cases and request keys. A separate worker process consumes
  the durable queue, and restarting it does not duplicate drafts.
- Interrupted extraction reuses only the successful checkpoint; draft-step failure
  resumes the saved comparison. Expired leases cannot commit and explicit requeue
  creates a new attempt.
- Corrections preserve originals and rerun validation. Concurrent correction or
  closure during drafting prevents the old draft from being saved.
- Owner isolation checked through the replaceable identity dependency. Production
  sign-in is not implemented or claimed.
- Deletion cancels active work; source deletion resumes after a simulated storage error.
- Unexpected API failures return redacted errors without emitting document text in server logs.
- Lint passed; package distributions built. Local health and API documentation endpoints
  responded successfully at `http://127.0.0.1:8000`.

Docker's engine was unavailable, so integration verification used the standalone
PostgreSQL Windows runtime in `.local/pgsql`, bound to loopback port 55433. The
Compose configuration uses port 55432. A later Docker attempt pulled the image and
started a healthy container, but database connections and Docker commands then
stalled. Docker-specific migration/test verification remains incomplete; it does
not replace the successful standalone PostgreSQL results above. The local default
remains standalone PostgreSQL. No hosted deployment was performed. A FastAPI/Starlette deprecation warning about the test
client's httpx adapter remains non-blocking; all tests passed.

See [BACKEND.md](BACKEND.md) for setup, endpoints, recovery, deletion and local-mode
limits. The existing Phase 1 CLI remains available unchanged in behavior.

## Phase 3 implementation

Authorized after the Phase 2 handoff and implemented on 27 September 2026.

- French Next.js/React/TypeScript interface: paginated cases, separate document
  uploads, source review with editable fields/lines, and results with editable drafts.
- Responsive desktop/mobile layouts, original PDF/image previews and source pages,
  explicit unknown values, blocking issues, pairing confirmation and correction reasons.
- Queued/processing states, reload-safe case persistence, retries, duplicate-case
  links, version-conflict errors, reasoned closure and confirmed deletion.
- Subject/body editing, versioned save before clipboard/download, no email sending.
- Supplier/invoice labels and Decimal totals supplied by the real API. Dashboard
  totals are page-scoped, separated by currency and exclude unresolved/closed cases.
- Same-origin API proxy restricted to loopback with Host/Origin checks; no provider
  key in the frontend and no third-party fonts or image requests.
- Dependency lockfile, reproducible Playwright test server and [WEB.md](WEB.md).

Necessary adjustment explained before implementation: the enqueue guard permits
comparison without a configured provider model only when **both current inputs
already contain audited human corrections** with matching source hashes. It never
substitutes made-up extraction values. All validation, duplicate checks, matching,
leases and draft guards still run. This makes the review interface usable without
an OpenAI key while keeping live extraction explicitly separate.

Verification on Windows, Node 24.13.1, Python 3.14.3, real PostgreSQL 17:

- **156 Python tests passed; 1 live OpenAI test skipped.** New coverage checks
  audited model-free comparison, exact currency-separated totals and local origins.
- **5 Chromium browser tests passed** against the real API and worker in a fresh
  disposable PostgreSQL schema. Only extraction uses synthetic fixture values.
- Full browser workflow: upload → missing quantity blocks draft → source review →
  correct to 22 → rerun → **200.00 MAD excluding tax** → edit/save → reload →
  copy/download → delete. No terminal intervention within this user journey.
- Unresolved values remain NEEDS_REVIEW with no draft or aggregate claim amount;
  stale edits cannot overwrite a concurrent version. Invalid formats and foreign
  origins are rejected. Desktop/mobile captures were inspected.
- TypeScript checking, optimized Next.js build and Python lint passed.

The optional read-only WebMCP case-refresh tool is feature-detected and unregisters
on navigation. Native execution remains unverified because no supported browser
context was available. This does not block normal UI usage.

Live extraction still needs an API key, explicitly selected compatible model and
successful opt-in test. Browser results do not establish model extraction quality.
The existing non-blocking Starlette test-client deprecation warning remains. The
Docker-specific limitation from Phase 2 remains unchanged.

## Phase 4 implementation and pending hosted acceptance

Authorized after Phase 3; code and local verification completed on 28 September 2026.
The user will configure provider accounts after the code handoff.

- Supabase asymmetric JWT verification, explicit invited-user allowlist and owner
  checks on every case operation. Hosted mode rejects developer identity fallback.
- French sign-in/sign-out, server-only auth cookies and same-origin API forwarding;
  origin/host checks, bounded requests and private responses.
- Private Supabase Storage adapter with temporary-file cleanup. RLS and revoked
  browser-role grants protect application tables from direct Data API access.
- Transactional daily quotas surviving case deletion, idempotent analysis requests
  and a three-attempt recovery cap per input revision.
- Worker heartbeat, protected non-content metrics, reported token/cost estimates
  and a scheduled monitor. Estimates are not a provider billing ledger or spend cap.
- Consistent PostgreSQL/document snapshots, checksums, isolated restore verification,
  AES-256-GCM encrypted scheduled backups and configurable archive retention.
- Non-root container definitions, Render deployment template and GitHub Actions
  checks. No paid service or deployment was created. Automatic deployment is off.
- [Configuration checklist](CONFIGURE.md) and [operations runbook](OPERATIONS.md)
  covering deployment, recovery, deletion, retention, backups and pilot gates.

Verification with real local PostgreSQL 17, Python 3.14 and Node 24:

- **174 Python tests passed; 1 live extraction test skipped.** Tests include real
  signed JWTs, two-owner isolation, concurrent quotas, retry caps, private storage
  adapter behavior and successful database/source/draft restoration.
- Backup tests authenticate ciphertext, reject tampering/wrong keys/overwrite,
  decrypt a scheduled archive and verify retention never runs after failed upload.
- **5 Chromium browser tests passed** through the new server-side API gateway,
  real API/worker and PostgreSQL, with synthetic extraction fixtures.
- Production Next.js build, TypeScript and Python lint passed.

GitHub Actions also passed on Linux for implementation commit `9e27483`:
[verified run](https://github.com/hannhm1109/avoirly/actions/runs/36428310118).
Both jobs succeeded: Python/PostgreSQL and browser tests, production web build,
all three Docker image builds, and PostgreSQL-tool execution in the operations
image. The local Docker engine remains unavailable; remote container verification
now passes. Container builds do not establish hosted runtime acceptance.

Still pending: real Supabase/Render configuration and deployment, actual hosted
cookie sign-in and two-account browser checks, live model extraction, provider alerts,
scheduled encrypted restore and the approximately 20-pair labeled evaluation set.
Mocked provider calls and local signatures are not hosted acceptance evidence.

Phase 4's implementation is ready for configuration. Its **hosted pilot acceptance
is not complete** until the checklist passes. Phase 5 was subsequently authorized
and is described below; email sending remains out of scope.

## Phase 5 — manual recovery tracking

Authorized 9 October 2026; implemented and locally verified 10 October 2026.
The migration proposal and usage/API details are in
[RECOVERY_TRACKING.md](RECOVERY_TRACKING.md).

- Migration `0003_phase5` preserves existing cases and expands the guarded status
  enum. New manual ledger and private proof tables use default-deny RLS and revoked
  browser-role grants. There is no arbitrary status or financial-total setter.
- French interface records externally sent saved drafts, supplier responses,
  promised amounts and evidence-backed partial credits. Sent records retain the
  exact saved draft/version and comparison; sources freeze during active tracking.
- Requested, promised and confirmed amounts remain separate Decimal strings.
  Confirmation requires a proof, date, reference, currency and explicit human
  receipt/verification. Full-credit coverage is separate from partial-credit status.
- Case/version/owner guards, case-lifetime request idempotency, daily quotas,
  exact-reference/evidence duplicate guards and cumulative sent-claim caps.
- Corrections retain original amounts, proofs, actor/time and reason; totals and
  status are recalculated from active entries. Closing preserves history; deletion
  removes the ledger and queues all proof objects for physical cleanup.
- Backups now include credit evidence and sent snapshots. The restore verifier
  also accepts genuine Phase 4 archives lacking the new tables. Local application
  data was backed up with the previous snapshot creator before migration.
- Dashboard totals are page-scoped and grouped by currency. Summary reads avoid
  loading private ledger notes and sent-text snapshots. Synthetic credit fixtures
  and their generator are bundled for reproducible checks.

Verification: **198 Python tests passed; one opt-in live extraction test skipped**.
Tests use real PostgreSQL, signed JWTs for both owners, concurrent requests,
legacy-schema upgrade/archive verification and real credit-proof/ledger restore.
**Six Chromium browser tests passed** against the real API and worker. The new flow
covers saved-draft send declaration, a 100.00 MAD promise, 75.25 + 124.75 MAD partial
credits, reload, audited correction, currency totals and deletion. Desktop/mobile
captures were inspected, and the mobile page has no horizontal overflow.
Production Next.js build, TypeScript and Python lint passed. The known non-blocking
Starlette test-client deprecation warning remains.

GitHub Actions passed for implementation commit `564e9f5`:
[verified run](https://github.com/hannhm1109/avoirly/actions/runs/38057908496).
Both Linux jobs succeeded, covering Python/PostgreSQL tests, production web build,
the six browser workflows, all three Docker image builds and PostgreSQL client-tool
execution in the operations image. Subsequent documentation-only commits do not
change the tested implementation.

At the Phase 5 implementation checkpoint, no hosted configuration, pilot
invitation, supplier message, payment provider or subscription had been created.
Subsequent self-hosted deployment is recorded below. Phase 4 hosted/live
acceptance remains pending. Phase 6
requires observed usage, pricing/provider choices and separate authorization.

## Self-hosted demonstration — 14 October 2026

The user authorized a $0 hosting path while retaining their two managed Supabase
projects. Avoirly and a pinned self-hosted Supabase stack now run on the user's
Oracle Casablanca ARM VM. HTTPS web, API and Auth/Storage origins are available;
database and internal services remain private. PostgreSQL TLS and application
migration `0003_phase5` were verified. The running application release is
`3a482f62cd0540cf454cb6cc1d429b6943ecf5c3`.

The self-hosted option retains asymmetric JWT verification, the pilot allowlist,
secure server-side sessions, API owner guards, RLS and private object storage.
Additional tests cover explicit custom-origin configuration and real ES256 JWTs.
Next.js was updated to 16.4.0 after dependency auditing. A tracking form bug was
fixed: after processing completes, a newly mounted sent-claim form initializes
its amount from the ready draft. A regression browser check reproduces the
processing-to-draft transition. Container copies now preserve ownership for
non-root runtime users even when the source checkout has private permissions.

[GitHub verification for the deployed release](https://github.com/hannhm1109/avoirly/actions/runs/38391344263)
passed both jobs: **210 Python tests, one live test skipped, six browser workflows**,
production build and all three container builds. ARM builds and runtime startup
also succeeded on the VM.

Actual hosted Chromium checks verified two-account login/reload/logout, cookie
flags, cross-owner read/download/mutation rejection, foreign-origin write rejection,
private PDF upload/download, and desktop/mobile layout. The synthetic test case
was deleted and its physical Storage object removal verified. No model call ran.

Daily 02:00 UTC encrypted application backups and five-minute monitor timers are
installed. Overnight and manual jobs succeeded. Two archives restored into empty
isolated PostgreSQL databases: one with a case/source and verified checksums, and
the actual scheduled archive with no cases/sources. Temporary databases/plaintext
were removed. Encrypted archives and restore reports were copied off the VM.
An initial encrypted database/Auth/configuration bundle was also copied off-VM;
only its encryption round trip was tested, not full Supabase restoration.

Pilot credentials and the backup key remain private, with a Windows-user-bound
encrypted local copy. No invitations or supplier messages were sent, and no
payment provider or subscription was created. There is no configured OpenAI key
or model. Full hosted acceptance still needs live extraction/evaluation, hosted
failure recovery, external alert delivery, recurring protected off-VM/provider
backups and participant/retention confirmation. The current billing account was
not audited. [SELF_HOSTING.md](SELF_HOSTING.md) records access and operations.

Further readiness audit on 14 October: the deployed API rejected missing,
expired, tampered, wrong-issuer/audience, anonymous and uninvited signed test
tokens, while the invited control succeeded. Worker preflight passed every
infrastructure gate and reported the missing provider key/model explicitly.
A complete hosted manual browser workflow passed with unique synthetic documents:
review, 200.00 MAD potential net credit, draft save/reload/copy/export, promises,
private proof-backed partial credits and audited correction. Queued work survived
an actual worker stop/restart. Only cases created by these tests were deleted.

Added a private local credential collector and a reusable server operations
helper. The collector's Windows-user encryption round trips, normalized app
password input, absence of secret output and invalid-key non-overwrite behavior
were verified with synthetic credentials. Shell syntax and hosted monitor through
the operations helper passed. The user authorized up to US$5 in initial API tests
and one Gmail SMTP test alert; neither was performed because credentials and an
enforced provider limit are still pending. The actual recipient stays outside
public documentation. [PILOT_READY.md](PILOT_READY.md) records the next steps.

## Live extraction and recovery — 15 October 2026

The user privately saved the dedicated OpenAI project key and confirmed its
enforced USD 5 monthly project limit, within the authorized USD 5 total initial
test allowance. The key is installed only in the worker. The explicit snapshot
is `gpt-5.4-mini-2026-03-17`, with configured rates of USD 0.75/million input and
USD 4.50/million output tokens. No credits were purchased by Codex; actual account
balance and invoices were not audited.

Application release `5b0941f01e220893aaabd2d80c5730642836c7de` is deployed.
[GitHub CI](https://github.com/hannhm1109/avoirly/actions/runs/38716134516)
passed **216 Python tests, one opt-in live test skipped, six Chromium workflows**,
production web build and all three container builds. Local Python tests and lint
also passed; ARM images built and run on the Oracle server. The schema remains
`0003_phase5`. All ten worker preflight checks and all monitor checks pass.

Separate hosted Chromium acceptance on this release used real model calls:
unique PDF/image upload → extraction → source review → 200.00 MAD potential net
credit → draft edit/save/reload/copy/download, plus mobile layout and deletion.
The tested credentials and documents were synthetic. Existing user cases were
preserved; only each test's own case was deleted. No supplier message was sent.

Controlled hosted recovery checks passed. An expired running lease was recovered
after stopping the normal worker, closing the first attempt and succeeding on a
new attempt. A separate real SDK connection fault through a closed local proxy
produced `NETWORK_ERROR` and persisted failure; the public retry path then
completed through the normal worker. This was a controlled network fault, not a
real OpenAI outage. The worker and monitor are healthy after both drills.

[Live evaluation](EVALUATION.md) records the baseline, prompt revision, intermediate
tuning and final results. Prompt 2 retains genuine uncertainty/unsupported-document
blockers and invalidates unreviewed caches; Python does not filter model warnings.
The final 20 development plus five fresh held-out pairs produced zero false drafts,
blocked all nine ambiguous pairs and matched expected status/amount on 24/25.
One supported scan still required manual review. Normalized critical-field matches
were 1,043/1,043, which is not a general OCR or production accuracy claim.
Reported estimates across evaluation, probe and persisted hosted acceptance were
approximately USD 0.44 at this checkpoint; failed/unreported calls and billing can
differ. New live calls remain subject to the original total allowance.

The tracked operations installer now provides timers, a guarded lease-recovery
wrapper and conditional SMTP failure notifications. Mocked alert tests pass.
Gmail credentials remain deferred, so no alert email or delivery test has occurred.
A fresh encrypted application archive and a refreshed database/Auth/configuration
bundle were copied off the VM with matching SHA-256 checksums. The latter includes
the new private configuration and passed encryption authentication/round-trip
verification; full Supabase restoration is still untested.

Before accepting real supplier documents: complete alert delivery, recurring
off-VM copies/full provider recovery, and participant/operator/privacy/retention
configuration. [PILOT_READY.md](PILOT_READY.md) is the concise remaining-work record.
Phases 1–5 are implemented; Phase 6 paid plans/payments/onboarding has not started.

SMTP configuration checkpoint later on 15 October: the user saved the dedicated
Gmail app password through the hidden local helper. It was transferred privately
to a root-owned mode-0600 server environment file, outside Git. Both monitor and
backup units reference the shared failure handler. Exactly one authorized test
was sent through the installed systemd test service; Gmail SMTP accepted it and
the private journal recorded success. The operator confirmed receiving the test
email; an actual scheduled-job failure notification was not induced. The
monitor remained healthy. The refreshed configuration/Auth backup now includes
SMTP configuration and installed operation units, passed encryption authentication
and was copied off-VM with a matching ciphertext SHA-256. No supplier mail was sent.

## Documentation and deployment check ? 16 October 2026

Recorded the completed Gmail SMTP configuration and the operator-confirmed test
receipt. No additional email was sent. The deployment passed all ten worker
preflight gates and all six monitor checks; backup and monitor services reported
success. This was a health/configuration check, not another full browser or
provider-recovery test.

Reworked the README around the complete application rather than its early CLI
phase: capabilities, current verified state, architecture, offline and web quick
starts, supported scope, testing and a documentation index. Added dedicated
architecture, CLI/report, testing and synthetic interview/demo guides. Updated
backend/web setup to distinguish Docker port 55432 from the prepared standalone
port 55433 and removed stale claims that no hosted extraction had been verified.

The documented offline fixture ran successfully through the installed backend
interpreter, producing the expected 200.00 MAD draft. Local Compose configuration
parsed, but Docker Desktop's Linux engine was unavailable, and uv was not installed
on the system Python PATH/module environment. The new-checkout instructions
explicitly install uv before use. No fresh local Docker integration/browser run
or paid model call was claimed for this documentation pass. Existing CI and
hosted evidence remain tied to application commit `5b0941f`.

Remaining real-data gates are unchanged: actual failed-job email delivery,
recurring independent backups/full Supabase recovery, and participant/privacy/
retention configuration. Phase 6 remains unstarted.

Documentation verification: local links/heading anchors and code-fence balance
passed across README and all 14 Markdown guides; live-result summary denominators,
the successful offline fixture and the copied synthetic screenshot were checked.
New documentation was checked for secret patterns and the private operator address.
The screenshot was inspected and contains synthetic data only. Markdown formatting
passed. This update changes documentation only; it does not rebuild the tested
application images or send another email.
