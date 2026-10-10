# Avoirly build progress

Brand: **Avoirly — Spot invoice discrepancies. Simplify supplier claims.**

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

No hosted configuration, pilot invitation, supplier message, payment provider or
subscription was created. Phase 4 hosted/live acceptance remains pending. Phase 6
requires observed usage, pricing/provider choices and separate authorization.
