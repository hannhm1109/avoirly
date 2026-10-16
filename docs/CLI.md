# Avoirly CLI and reports

The CLI runs the document-comparison core independently of the web application.
It has no sign-in, durable job queue or owner-wide case history. Use the hosted
interface for authenticated cases, audited corrections and recovery tracking.
See the [main quick start](../README.md#quick-start) for installation.

## Run offline

```powershell
python -m uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/demo
```

Expected result: `CLAIM_DRAFTED`, with **200.00 MAD potential credit excluding tax**.
This path makes no provider call. It writes `report.json` and `claim_email.txt`.
Add `--language en` for an English draft. Files are written relative to the
repository root when the command is run from there.

## Process documents

The actual PDF and PNG sample files contain only synthetic business information.
Both sources are validated before either API call. To use extraction, set the
configuration in your shell; `.env.example` lists placeholders and is not loaded
automatically.

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "your-selected-compatible-model"
python -m uv run --project backend --locked python -m recovery.cli --po ./samples/po.pdf --invoice ./samples/invoice.png --language fr --out ./output/live-sample
```

Select a model supporting Chat Completions, vision, PDF inputs, and Structured
Outputs in your account. Avoirly deliberately has no default model. The deployed
snapshot was verified with real synthetic PDF/image calls on 15 October 2026; see
the [evaluation record](EVALUATION.md) for settings, costs and limitations.
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

The report itself **does contain document data**. Store it privately. Cloud-sync
folders can copy generated outputs according to your sync settings; the prepared
Windows workspace is under OneDrive.
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
python -m uv run --project backend --locked python -m recovery.cli --po ./my-po.pdf --invoice ./my-invoice.png --out ./output/case-1 --confirm-pair --actor "Hanane" --reason "Verified these documents refer to the same order"
```

That confirmation is tied to the extraction revision hash and bypasses only the
missing-reference issue. It cannot override conflicting references, identities,
unsupported charges, or any other validation rule.

The CLI has no owner-wide history database. To detect repeats across local cases,
pass prior reports explicitly (the flag can be repeated):

```powershell
python -m uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/another-case --previous-report ./output/demo/report.json
```

A repeated supplier/invoice number or source file hash blocks the new claim. Use
the original case instead. Reusing an output directory is a rerun of that case.
History not supplied to the CLI cannot be checked; mandatory owner-scoped duplicate
checks run in the hosted API. Original/corrected extraction versions and manual
line-pairing controls are available through the API and web interface. Do not
treat edited fixture JSON as an audited correction process for real documents.

The tool does not claim tax credits, offset across products, check cumulative
invoices, infer missing numbers, negotiate, or send email. Review the source and
draft yourself before using it outside Avoirly.
