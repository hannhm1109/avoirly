# Phase 5 — manual claim and credit tracking

This implements the guide's later recovery-tracking extension. Hosted Phase 4
configuration is deployed; remaining pilot acceptance gates are tracked in
[PILOT_READY.md](PILOT_READY.md). No account,
subscription or sending service is required to use this feature locally.

## Migration proposal and implemented scope

`0003_phase5` preserves the existing cases, drafts, calculations and audit events.
It expands the case status constraint with `CLAIM_SENT`, `AWAITING_RESPONSE`,
`CREDIT_PROMISED`, and `CREDIT_CONFIRMED`, then creates:

- `recovery_entries`: the manual sent record, supplier notes, promises, and received
  credits. Amounts use NUMERIC(38,2); every entry has its case/revision, actor,
  occurrence date and UTC recording time. Sent entries retain the saved draft's
  text, version and comparison ID. Corrections retain the original and record
  who voided it, when, and why.
- `recovery_evidence`: validated private PDF/PNG/JPEG proofs with owner/case,
  random object key, hash, size and page count. No public download URL is exposed.

The new tables enable default-deny RLS and revoke browser-role grants. Named
actions check ownership, expected case version and the active comparison revision
inside one transaction. Manual records also use durable idempotency keys so a
transport retry cannot add the same financial entry twice. The ledger never calls
the extraction provider or sends a message.

## Use the French interface

1. Complete the comparison and source review, then edit and save the draft.
   Copy/download remains an export. It creates no sent record or confirmed credit.
2. Send the message using your own messaging service. In **Suivi de la demande**,
   enter the actual date, recipient and amount excluding tax. Declare that you
   sent the saved version externally. Unsaved draft edits block this action.
3. Optionally mark the claim as awaiting a response. Record supplier responses as
   dated notes. A note does not count as money.
4. Record a promised credit separately, with its reference, amount HT and optional
   due date. Each promise adds an amount; void an old promise before replacing it.
   Promises remain distinct from received credits, even after confirmation.
5. For each received partial credit, upload a private proof and open it. Check its
   invoice, supplier, credit reference, currency and amount excluding tax. Enter
   that amount/reference and explicitly declare receipt and verification.
6. The totals show **Demandé HT**, **Promis HT**, **Confirmé HT** and the remainder
   of the sent claim without confirmed credit. A partial credit retains its actual
   amount. `CREDIT_CONFIRMED` means at least one active evidence-backed credit;
   **fully credited** is a separate test that the confirmed sum equals the claim.

For example, a 200.00 MAD sent claim, a 100.00 MAD promise and a 75.25 MAD received
credit show those three separate totals, with 124.75 MAD still without confirmed
credit. A second received credit for 124.75 MAD brings confirmation to 200.00 MAD.
The promise is never added to the confirmed total. A received credit note does
not establish cash reimbursement or accounting settlement.

The dashboard groups totals by currency for the displayed page only. Closed cases
retain their tracking totals and history. Closing never creates an amount.

## Guards, corrections and limits

- Only a current saved discrepancy draft can be recorded as sent. The positive
  sent amount must not exceed its validated potential credit. All later monetary
  records use that same currency; cumulative promises and cumulative credits are
  separately capped at the sent amount. No tax calculation or rounding of extra
  input decimals occurs. Amounts are decimal strings, with at most two decimals.
- Use an ISO calendar date from the sent date through today's UTC date. A promised
  due date may be in the future, but cannot precede the promise.
- Once sending is recorded, source revisions and draft editing are frozen. The
  retained sent text remains readable in the history. This avoids changing the
  basis of an existing supplier claim.
- **Corriger cette entrée** voids an entry with a required reason. The amount,
  evidence and history remain readable; active totals and status are recalculated.
  Add a replacement entry afterward. To correct sending, first void its active
  promises and confirmed credits; voiding sending restores the draft state.
- Identical evidence hashes are unique per owner. A proof already attached to
  this case is reused; a proof belonging to another case is rejected. One active
  received credit per evidence file and normalized case credit reference prevents
  counting the same recorded proof/reference twice. This does not detect altered
  copies or independently verify what a supplier actually issued.
- The operator's account remains responsible for the accuracy of manual proof
  verification. Merely uploading a file never confirms credit. Evidence is not
  automatically extracted or sent to the model provider.
- Default daily limit: 120 tracking actions per owner (`AVOIRLY_DAILY_TRACKING`).
  Existing upload limits also apply. Each case has at most 50 proofs and 1,000
  ledger entries, including voided history. Proofs have the same 10 MiB, 10-page
  PDF, and image-size/parseability limits as original documents.
- Closed cases allow read/download/delete, with no new tracking mutations.
  Deletion cascades the ledger and queues source and proof objects for removal.
  Backups include proofs and retained snapshots; backup retention still applies.

## API

Every tracking POST requires a verified owner (or explicit local development
identity), `expected_version`, and an `Idempotency-Key` header. Successful repeated
requests with the same key and payload return the original result. A changed
payload with the same key conflicts. Keys survive for the lifetime of the case.

| Endpoint under `/api/v1` | Record/action |
| --- | --- |
| `POST /cases/{id}/tracking/sent` | Saved `draft_id`, date, recipient, amount/currency and `sent_outside_app: true` |
| `POST /cases/{id}/tracking/await` | Explicit awaiting-response transition |
| `POST /cases/{id}/tracking/note` | Date and supplier response note |
| `POST /cases/{id}/tracking/promise` | Date, net amount/currency, reference, note and optional due date |
| `POST /cases/{id}/tracking/credit` | Date, net amount/currency, reference, note, `evidence_id`, `received_and_verified: true` |
| `POST /cases/{id}/tracking/{entry}/void` | Reasoned correction retaining original history |
| `POST /cases/{id}/evidence` | Multipart file plus expected version; attaching proof increments version |
| `GET /evidence/{id}/content` | Private owner-checked proof preview/download |

Case detail adds `recovery` with ledger and proof metadata. Case lists add summary
totals and `recovery_by_currency`, never cross-currency sums. Evidence attachment
uses hash-based retry deduplication and never creates a confirmed-credit entry.

For migration, backup, historical restore and deletion procedures, see
[OPERATIONS.md](OPERATIONS.md). Verification results are recorded in
[PROGRESS.md](PROGRESS.md). Phase 6 payments and automated sending require separate
authorization and implementation.
