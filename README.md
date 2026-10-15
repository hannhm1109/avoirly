# Avoirly

*Spot invoice discrepancies. Simplify supplier claims.*

Avoirly compares one purchase order with one supplier invoice, explains potential
billing differences with source evidence, and prepares a French or English email
for your review. The amount is **Potential credit excluding tax**, not confirmed
recovery. Documents alone cannot establish delivery, amendments, or whether a credit
is owed.

## Build status

Build Phases 1–3 are implemented. Phase 4 adds hosted authentication, private
document storage, quotas, encrypted backups, monitoring and deployment templates
to the Python API, durable worker and French Next.js interface. Phase 4's code is
verified locally and in GitHub Actions. A self-hosted demonstration now runs over
HTTPS on the Oracle ARM server, with signed login, private uploads, two-account
isolation and encrypted backup restores verified. Full hosted pilot acceptance
still requires operator alert delivery, full recovery preparation and participant
configuration. Live PDF/image extraction, failure recovery and a labeled synthetic
evaluation now pass. No supplier email sending is implemented.

Phase 5 adds manual sent-claim records, supplier notes, promised credits and
evidence-backed partial credits with separate net totals and audited corrections.
See [the recovery tracking guide](docs/RECOVERY_TRACKING.md).

Next: finish the live gates in the [configuration checklist](docs/CONFIGURE.md), then the
[operations runbook](docs/OPERATIONS.md). [Progress](docs/PROGRESS.md) separates
completed verification from pending hosted gates.

For the current $0 hosting budget, see the [deployed self-hosting guide](docs/SELF_HOSTING.md).
The private demonstration is at **https://avoirly.84-8-218-133.sslip.io/connexion**.
Automatic extraction is enabled with the explicitly selected
`gpt-5.4-mini-2026-03-17` snapshot. Hosted PDF/image upload → live extraction →
source review → draft/edit/export and manual recovery tracking are verified.
The [live evaluation](docs/EVALUATION.md) records 20 development pairs and five
fresh held-out pairs, with zero false drafts and one conservative review miss.
[Finish pilot readiness](docs/PILOT_READY.md) lists the remaining credential,
private-entry command and operational acceptance work.

Start with the [web setup guide](docs/WEB.md) to use the application at
**http://127.0.0.1:3000**, or run the offline CLI example below. The
[backend guide](docs/BACKEND.md), [progress](docs/PROGRESS.md) and
[source specification](docs/SPEC.md) explain the architecture and remaining gates.

## Run the example now

From this project folder on Windows, the prepared environment can run:

```powershell
.\backend\.venv\Scripts\python.exe -m recovery.cli --fixture .\samples\pair.json --out .\output\demo
```

Expected result:

```text
Avoirly: CLAIM_DRAFTED
Potential credit excluding tax: 200.00 MAD
```

Open `output/demo/report.json` to inspect the extracted values, validation, source
snippets, findings, and final status. Open `output/demo/claim_email.txt` to review
the French email. Add `--language en` for English. Fixture mode never calls OpenAI.

## Reproducible installation

Requires Python 3.12 or newer. The completed checks used Python 3.14.3 on Windows.
The resolved dependencies are in `backend/uv.lock`.

```powershell
python -m pip install uv
uv sync --project backend --locked
uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/demo
uv run --project backend --locked pytest backend/tests -q
```

The installed console command `avoirly` also works in the project environment.
On macOS/Linux the environment interpreter is `backend/.venv/bin/python`.

## Process documents

The actual PDF and PNG sample files contain only synthetic business information.
Both sources are validated before either API call. To use extraction, set the
configuration in your shell; `.env.example` lists placeholders and is not loaded
automatically.

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "your-selected-compatible-model"
uv run --project backend --locked python -m recovery.cli --po ./samples/po.pdf --invoice ./samples/invoice.png --language fr --out ./output/live-sample
```

Select a model supporting Chat Completions, vision, PDF inputs, and Structured
Outputs in your account. Avoirly deliberately has no default model. The deployed
snapshot was verified with real synthetic PDF/image calls on 15 October 2026; see
the [evaluation record](docs/EVALUATION.md) for settings, costs and limitations.
Confirm capabilities and access again when changing models.

Each document is sent separately through the official OpenAI SDK using
`client.chat.completions.parse`, its own Pydantic response format, and `store=False`.
The SDK uses a 90-second timeout and at most two retries (three transport attempts)
per extraction; there is no outer retry loop. Document contents never supply tools,
links to fetch, or instructions to execute. The request shapes were checked against
the official [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[file inputs](https://developers.openai.com/api/docs/guides/file-inputs), and
[image inputs](https://developers.openai.com/api/docs/guides/images-vision) documentation.

Files must be PDF, PNG, or JPEG with matching signatures and extensions. Limits are
10 MiB per file, 10 PDF pages, 25 megapixels per image, and 100 extracted product
lines. Encrypted PDFs, multi-frame images, invalid files, and incomplete output
are not accepted as clean comparisons. No silent truncation occurs.

## Understand the report

- `extraction`: original structured fields, including printed source snippets.
- `validated_pair`: converted Decimal values and normalized units, only if valid.
- `comparison`: outcome, findings, components, currency, and potential net amount.
- `review_issues`: blocking reasons; any blocker removes all findings and the total.
- `claim_draft`: generated subject and body only for a completed discrepancy case.
- `documents` and `extraction_metadata`: file hashes, page counts, model, versions,
  request IDs, token usage, and latency; these metadata do not contain source text.
- `events` and `confirmations`: local workflow history and recorded pairing confirmation.

The report itself **does contain document data**. Store it privately. This workspace
is under OneDrive and may sync generated outputs according to your OneDrive settings.
The CLI does not offer account isolation or encryption. The hosted API provides
owner isolation, private object storage and encrypted application backups.

`report.json` is replaced atomically. `claim_email.txt` is written only for
`CLAIM_DRAFTED`; an obsolete draft file is removed on a no-draft rerun. Each file
replacement is atomic, but the two files are not a database transaction. Do not run
two processes into the same output directory; a lock prevents this. Following a
crash, remove `.avoirly.lock` only after verifying no runner is using that directory.

Exit codes: `0` = completed comparison/draft, `2` = review required, `1` = technical
failure. Invalid CLI arguments use argparse's standard exit code `2` with usage help.

## Review and supported checks

Supported cases have matching supplier, buyer, currency and PO reference, positive
quantities, tax-exclusive nonnegative prices, explicit tax rates, unique lines,
and no adjustments. MAD, EUR, USD and GBP are supported. Arithmetic uses Decimal
precision 48, half-up currency rounding, and the guide's 0.01 tolerance. Excess
quantity and price components are not double-counted. One product's favorable
price does not reduce another product's finding.

Matching uses exact normalized SKUs, then unique normalized descriptions only when
at least one SKU is missing. Punctuation and leading zeros remain significant in
SKUs. Units use a small explicit alias map; no pack or unit conversions occur.
As a conservative first-phase choice, a changed description on a matching SKU
requires review too, because it may conceal a pack-size or model change. This may
increase review frequency. All extraction warnings block automatic drafts until
the ambiguity has been resolved. No model confidence score is used.

When the invoice has no PO reference, record a human pairing confirmation:

```powershell
uv run --project backend --locked python -m recovery.cli --po ./my-po.pdf --invoice ./my-invoice.png --out ./output/case-1 --confirm-pair --actor "Hanane" --reason "Verified these documents refer to the same order"
```

That confirmation is tied to the extraction revision hash and bypasses only the
missing-reference issue. It cannot override conflicting references, identities,
unsupported charges, or any other validation rule.

Phase 1 has no owner-wide history database. To detect repeats across local cases,
pass prior reports explicitly (the flag can be repeated):

```powershell
uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/another-case --previous-report ./output/demo/report.json
```

A repeated supplier/invoice number or source file hash blocks the new claim. Use
the original case instead. Reusing an output directory is a rerun of that case.
History not supplied to the CLI cannot be checked; mandatory owner-scoped duplicate
checks belong to Phase 2. Original/corrected extraction version storage and manual
line-pairing controls also belong to Phase 2. Do not treat edited fixture JSON as
an audited correction process for real documents.

The tool does not claim tax credits, offset across products, check cumulative
invoices, infer missing numbers, negotiate, or send email. Review the source and
draft yourself before using it outside Avoirly.

## Tests and live verification

```powershell
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend scripts
```

The offline suite covers the guide's calculation examples, tolerances, invalid
numbers, identity checks, matching ambiguity, pack/unit conflicts, source evidence,
file validation, SDK response shapes, retry limits, refusal handling, local duplicate
checks, guarded workflow events, atomic writes, and stale draft cleanup.

The opt-in live test sends only the bundled synthetic PDF and PNG. It is skipped
unless explicitly enabled:

```powershell
$env:AVOIRLY_LIVE = "1"
uv run --project backend --locked pytest backend/tests/test_live.py -m live -q
```

This opt-in test does not run in ordinary CI. Separate real hosted browser
acceptance and the [labeled live evaluation](docs/EVALUATION.md) passed on
15 October 2026; CI fixtures are not presented as live-model evidence.

## Project files

| Location | Purpose |
| --- | --- |
| `backend/src/recovery/models.py` | Extraction and validated data contracts |
| `backend/src/recovery/extraction.py` | File validation and bounded OpenAI adapter |
| `backend/src/recovery/validation.py` | Supported-case and arithmetic checks |
| `backend/src/recovery/matching.py` | Unique deterministic line matching |
| `backend/src/recovery/comparison.py` | Pure Decimal discrepancy calculations |
| `backend/src/recovery/claims.py` | French and English draft templates |
| `backend/src/recovery/workflow.py` | Legal state map and synchronous workflow |
| `backend/src/recovery/cli.py` | Command, reports, and file output |
| `backend/tests/` | Offline acceptance suite and opt-in live check |
| `samples/` | Synthetic extraction JSON, PO PDF and invoice PNG |
| `scripts/generate_samples.py` | Rebuild the synthetic source documents |
| `docs/SPEC.md` | Text of the supplied build guide |
| `docs/PROGRESS.md` | Completed phase, checks and remaining gates |
