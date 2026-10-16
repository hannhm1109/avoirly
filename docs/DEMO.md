# Synthetic demonstration and interview walkthrough

Use only synthetic documents for this demonstration. The private hosted app is
at [Avoirly](https://avoirly.84-8-218-133.sslip.io/connexion); access is supplied by
the operator, and there are no public credentials. Local setup is in the
[README](../README.md#quick-start). This walkthrough does not authorize sending
supplier mail, recording real recovery or expanding API spending.

## Prepare

1. Check API/worker health before presenting. For the existing hosted server,
   use `sudo /usr/local/bin/avoirly-ops preflight` and `monitor` after SSH login.
2. In the prepared Windows workspace, run `./scripts/show-pilot-access.ps1` in
   your own terminal to view the synthetic login. Never record its output or
   include the password in slides/screenshots. This helper is not for public users.
3. Use `samples/po.pdf` and `samples/invoice.png`. They represent 20 units ordered
   at 100.00 MAD and 22 units invoiced at the same price: expected potential net
   credit **200.00 MAD**. These are examples, not customer documents.
4. If the same files/invoice already belong to an existing case, reopen that
   case. Duplicate blocking is expected behavior; do not delete another person's
   work or change identifiers just to hide the check.

For additional labeled scenarios, generate a new local synthetic corpus without
API calls:

```powershell
python -m uv run --project backend --locked python scripts/generate-evaluation.py --out .local/demo-corpus
```

The output directory must not already exist. Each `eval-XX` folder includes source
documents and `truth.json`; `manifest.json` records labels and expected amounts.
Generation is deterministic and does not guarantee new identities on every run.
Inspect the manifest before selecting files. Uploading and analyzing them through
the live app can incur API charges even though generating them does not.

## Present the workflow

| Step | Show                                           | Explain                                                                                   |
| ---- | ---------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 1    | **Nouveau dossier**, one PO and one invoice    | Input limits and file validation happen before extraction                                 |
| 2    | Analyze and persisted processing state         | A database job survives an API restart; a separate worker performs the work               |
| 3    | Source review and document pages               | Extraction is probabilistic; original evidence and human corrections remain visible       |
| 4    | Quantity/price comparison                      | Python Decimal computes the supported discrepancy; the model does not calculate the claim |
| 5    | 200.00 MAD potential net credit                | This is an amount to verify with the supplier, not confirmed recovery                     |
| 6    | Edit, save, reload, copy or download the draft | Drafts are versioned, and export sends no email                                           |
| 7    | Manual tracking with synthetic records         | Requested, promised and evidence-confirmed amounts are different concepts                 |
| 8    | A review-required or duplicate example         | The system blocks unsafe automation instead of inventing missing values                   |

For a no-API demonstration, enter both complete source snapshots through
**Vérifier les données** and save/rerun. State clearly that this path demonstrates
human review and deterministic comparison rather than automatic extraction.
The offline CLI fixture is another network-free option.

For recovery tracking, use only a clearly designated synthetic case and the
bundled synthetic credit notes. Label an external-send declaration as simulation;
it never sends a message. A received-credit entry requires proof, reference, date,
currency and explicit human verification. See [RECOVERY_TRACKING.md](RECOVERY_TRACKING.md)
for the exact guards and correction behavior.

## Describe the engineering honestly

- Structured extraction uses typed contracts; deterministic validation controls
  whether the data is eligible for a claim draft.
- Exact matching and Decimal avoid fuzzy line pairing and floating-point money
  calculations. Uncertainty raises review workload rather than silently passing.
- Versions, idempotency, database leases and guarded commits address duplicate
  requests, worker crashes and concurrent changes.
- Hosted authorization, private files and owner checks were exercised with two
  synthetic accounts; this is not a claim of formal security certification.
- CI verified 218 Python tests and seven browser workflows for the deployed
  implementation. Paid-model behavior was evaluated separately.
- Final evaluation used 20 development and five fresh held-out synthetic pairs:
  zero false drafts, 24/25 status-and-amount matches, all nine ambiguous cases
  blocked. One supported scan still required review. The small shared-layout set
  does not establish production accuracy. [Full results](EVALUATION.md).

There are no verified customers, recovered-money totals or paid subscriptions to
claim. Full service recovery from an off-VM ciphertext copy and actual monitor/
backup failure emails were verified on 16 October. Automated copying depends on
the operator's Windows PC being available. Public contact is deferred and
real-participant admission remains closed. Replacement-server/DNS cutover and
production availability are not established. [Current readiness](PILOT_READY.md).
