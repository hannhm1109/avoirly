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

## Next phase

Phase 2's local persistence/restart/idempotency gate passes. Stopped before Phase 3
as the guide requires. Live extraction still needs a configured compatible model
and successful opt-in test; this is not a completed private pilot.

To continue: “Implement Build Phase 3 of Avoirly following docs/SPEC.md and docs/PROGRESS.md.”
Phase 3 adds the four French-language web screens against this API. Authentication,
hosted deployment, backup/restore verification, monitoring and pilot readiness remain
Phase 4.
