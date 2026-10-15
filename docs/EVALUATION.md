# Live synthetic extraction evaluation — 15 October 2026

Avoirly's final prompt produced **zero false drafts across 25 synthetic pairs**:
20 development pairs and five fresh held-out pairs. All nine intentionally
ambiguous pairs required review. This small generated set is engineering evidence,
not a production accuracy estimate or evidence that a supplier owes money.

## Method and coverage

The corpus contains text PDFs, image-only scanned PDFs, simulated angled phone
images and mixed PDF/image pairs. Scenarios include quantity/price/both differences,
clean invoices, underbilling, currency/supplier mismatches, missing PO references
or quantities, unsupported fees, tax-inclusive prices, duplicate SKUs, multiple
lines and one document with an overt prompt-injection note.

Expected source fields and expected outcomes are declared in the generator;
offline validation checks that the expected amounts agree with the deterministic
engine. Labels were not supplied by the extraction model. They have not received
independent annotation by a second human reviewer. Phone images are simulated,
not photographs from actual users. Documents and all amounts are visibly synthetic.

The original 20 pairs initially included five reserved pairs. Their results were
inspected while revising the prompt, so **all 20 are development data for the final
prompt**. An intermediate five-pair batch (IDs 21–25) was also inspected. The final
fresh holdout (IDs 26–30, generator batch 2) changed identifiers, parties and
amounts, was evaluated once after the final prompt was fixed, and was not used for
further tuning. It still shares generated layouts and scenarios with development;
it does not establish generalization to unseen supplier layouts.

Model: `gpt-5.4-mini-2026-03-17`; final prompt version `2`, SHA-256
`d359ca59ac8e72575ac4dbe4a4f682ec452a31057ffc90301b8141f64828f9a7`.
Evaluation uses the live SDK adapter, `store=False`, a 90-second timeout, no
transport retries and a 6,000-output-token limit. Production retains its bounded
SDK retry policy; benchmark latency therefore does not describe failure retries.

## Recorded results

| Measure | Prompt 1 baseline, 20 | Final prompt 2, development 20 | Final prompt 2, fresh holdout 5 |
| --- | ---: | ---: | ---: |
| Expected status and amount | 9/20 | 19/20 | 5/5 |
| False drafts | 0/20 | 0/20 | 0/5 |
| Ambiguous cases blocked | 7/7 | 7/7 | 2/2 |
| Normalized critical fields matched | 837/838 | 838/838 | 205/205 |
| Correct / predicted findings | 2/2 | 9/9 | 2/2 |
| Found / expected findings | 2/10 | 9/10 | 2/2 |
| Cases requiring review | 18/20 | 8/20 | 2/5 |
| Median seconds per pair | 4.7345 | 4.5335 | 4.709 |
| Reported estimated USD | 0.11615925 | 0.11922675 | 0.0314940 |

Machine-readable evidence: [baseline](evaluation/2026-10-15-baseline-prompt1.json),
[final development](evaluation/2026-10-15-prompt2-development.json),
[fresh holdout](evaluation/2026-10-15-prompt2-heldout.json).
The baseline was rescored to remove 20 non-applicable, trivially null PO-reference
slots on purchase orders; the paid calls were not rerun.

A false draft means a draft on a non-draft case or with an incorrect total.
Finding matching separately checks PO/invoice line numbers and net amounts.
Critical-field matching compares declared identities, references, currencies,
tax bases, adjustments, totals, line counts, SKUs, quantities, units, prices and tax
rates; Decimal values are normalized before comparison. It excludes descriptions,
source-snippet quality, page-coordinate accuracy and warning-text accuracy.
Consequently, 1,043/1,043 final field matches must not be described as perfect OCR.

The baseline mainly failed conservatively: it treated synthetic branding,
single-page inputs and routine extraction observations as blocking warnings.
Prompt 2 clarifies that warnings describe actual uncertainty. It retains blockers
for missing/unclear data and unsupported, VOID, cancelled or proforma documents.
Python still blocks **every** extraction warning; none is silently filtered away.
The prompt-version change invalidates unreviewed extraction caches.

One supported scanned price case (`eval-08`) still required manual review because
the model warned about the synthetic notice and its single scanned page. Its
critical fields matched, but the blocked draft counts as a missed expected finding.
The prompt-injection pair passed; one overt example does not establish broad
resistance to adversarial documents.

## Cost and reproduction

Rates used: USD 0.75/million input tokens and USD 4.50/million output tokens,
from the [official model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
The five recorded evaluation runs, including two intermediate tuning runs, total
USD **0.41647875** in reported estimates. The final 25 alone total USD **0.15072075**.
Adding the standalone probe and persisted hosted acceptance usage recorded at the
checkpoint gives about **USD 0.44**. These are token-based estimates, not invoices
or a verified account balance; failed/unreported calls, caching and billing rules
can differ. The user's initial testing allowance is USD 5, and the user confirmed
the dedicated project's enforced monthly limit. The evaluator's USD 0.10 reserve
and application alerts do not themselves impose a provider billing cap.

Generate private data and run only with an explicitly approved API allowance:

```powershell
uv run --project backend --locked python scripts/generate-evaluation.py --out .local/evaluation-example
uv run --project backend --locked python scripts/generate-evaluation.py --out .local/evaluation-holdout-example --fresh-holdout --holdout-batch 2
# Configure the API key, model and rates privately in the process environment.
uv run --project backend --locked python scripts/evaluate-extraction.py --corpus .local/evaluation-example --out .local/evaluation-example-results --max-usd 1.00 --allow-live
```

The generator uses the dependencies locked in `backend/uv.lock`.
The evaluator verifies fixture hashes, refuses an already recorded output folder,
stops on a failed/unreported extraction, and writes no application database rows.
Results can vary between calls. Preserve new held-out layouts before the next
prompt change rather than reusing these inspected pairs as blind evidence.
