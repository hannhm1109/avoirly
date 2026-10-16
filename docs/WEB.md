# Avoirly — local French web interface

Phase 3 adds the four Next.js screens to the existing Python API and durable
worker. Node.js 20.9+ is required; verification used Node 24.13.1 and npm 10.8.2.
Dependencies are pinned by `web/package-lock.json`.

Phase 4 adds French password sign-in, sign-out and privacy information. A
server-side API gateway forwards the session token to Python for owner checks;
HttpOnly/Secure cookies hold hosted sessions. No provider secret enters browser
code. Local mode still works without a Supabase account. For hosted configuration
and live acceptance checks, see [CONFIGURE.md](CONFIGURE.md).

Phase 5 adds **Suivi de la demande** beneath a saved draft/result, with manual
external-send declarations, supplier notes, promises, received partial-credit
proofs and audited corrections. Dashboard totals keep requested, promised and
confirmed net amounts separate by currency. See [RECOVERY_TRACKING.md](RECOVERY_TRACKING.md).

## Start locally

For a new checkout, follow the [README quick start](../README.md#run-the-web-app-locally)
to start Docker PostgreSQL on port 55432 and run migrations. The commands below
describe the prepared Windows standalone database on port 55433. These databases
do not share data; preserve the explicit `DATABASE_URL` from the chosen setup in
every API and worker shell.

For the prepared standalone workspace, start PostgreSQL once:

```powershell
./scripts/start-local-postgres.ps1
```

Run these in three terminals, starting from the repository root:

```powershell
# Terminal 1 — API
. ./scripts/local-env.ps1
./backend/.venv/Scripts/python.exe -m recovery.api.app
```

```powershell
# Terminal 2 — durable worker (required even for manual review)
. ./scripts/local-env.ps1
./backend/.venv/Scripts/python.exe -m recovery.worker
```

```powershell
# Terminal 3 — interface
cd web
npm ci
npm run dev
```

Open **http://127.0.0.1:3000**. Stop each process with Ctrl+C. The PostgreSQL
database and private uploads survive restarts. If a worker was interrupted during
processing, follow the explicit expired-lease recovery command in BACKEND.md.

Next.js proxies `/api/v1` to `http://127.0.0.1:8000`. Override only with another
loopback HTTP origin using `AVOIRLY_API_ORIGIN` (see `web/.env.example`). The API
can allow an additional local frontend origin with `AVOIRLY_WEB_ORIGIN`. Both
services bind to loopback; foreign Host/Origin headers are rejected. This remains
the local development configuration. Hosted mode has a separate signed-session
configuration described in [CONFIGURE.md](CONFIGURE.md).

## Complete a case

1. Open **Nouveau dossier** and select a purchase order and invoice. Formats:
   PDF, PNG, JPEG; 10 MiB each, 10 PDF pages, 25 megapixels per image.
2. **Analyser les documents** imports both files and queues processing. Partial
   imports remain accessible through the saved case if an upload fails.
3. Open **Vérifier les données** when a value is uncertain. Switch between the
   two documents, view the original and source page, edit fields and lines, and
   explain the correction. Confirm pairing explicitly if no PO reference exists.
4. **Enregistrer et relancer** preserves originals, creates an audited revision,
   invalidates earlier results, and reruns all validation and matching rules.
5. Review the quantities, unit prices, quantity/price components and potential
   credit excluding tax. Edit the subject and body, then save, copy or download.
   Changes are saved before export. Draft actions send no email and record no recovery.

Every unresolved warning continues to block drafting. Unsupported charges, tax
bases, mismatches and ambiguous lines cannot be bypassed by pairing confirmation.
Amount values stay decimal strings; aggregation and arithmetic happen in Python.
Dashboard totals cover the displayed page and remain grouped by currency.

Closure records a reason and prevents changes. Deletion requires an explicit
confirmation and uses the backend's durable private-file cleanup.

## Without an OpenAI key

Automatic extraction requires `OPENAI_API_KEY` and `OPENAI_MODEL` configured in
the worker environment. The API also needs `OPENAI_MODEL`. Keep the API key out
of the web environment and every `NEXT_PUBLIC_` variable.
The model must support the input formats and Structured Outputs.

Without configuration, import the files, open the saved case, then choose
**Vérifier les données** and enter values from the originals. Both complete
document snapshots must be saved through the audited review endpoint before a
model-free comparison can be queued. The worker does not call a provider on this
path. Unknown values still produce **À vérifier**, never fabricated results.

This extends the Phase 2 enqueue guard: a model is required when extraction is
needed, rather than for every comparison. The worker's existing validation,
duplicate checks, revisions and leases remain unchanged.

## Verification

```powershell
# From the repository root; disposable PostgreSQL test schemas only
. ./scripts/local-env.ps1
$env:AVOIRLY_TEST_DATABASE_URL = $env:DATABASE_URL
$env:AVOIRLY_PG_BIN = Join-Path $PWD '.local/pgsql/bin'
./backend/.venv/Scripts/python.exe -m pytest backend/tests -q
cd web
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm run test:e2e
```

The browser suite starts a separate API on 8001 and Next.js on 3001. It uses a
new random PostgreSQL schema and temporary storage. Only the extraction adapter
is replaced with synthetic labeled values; uploads, API, worker, validation,
corrections, arithmetic, persistence and exports are real. It deliberately
omits a quantity to require human review. No OpenAI call or real supplier data
is used. Graceful shutdown removes its schema; forced process termination may
leave an `avoirly_browser_<uuid>` test schema for operator cleanup.

Tests cover desktop/mobile empty states, upload, blocked review, correction,
draft creation/edit/reload, clipboard, download, deletion, stale edits, invalid
formats and foreign origins. Screenshots and failure traces stay in ignored
`web/test-results/`. Live model extraction remains a separate opt-in gate.

The cases screen feature-detects optional WebMCP and registers
`refresh_visible_cases`, a read-only refresh using the same API and visible
state. Invalid inputs are rejected and navigation unregisters the tool.
Native WebMCP execution was not verified: no supported browser context was
available. Ordinary browser operation does not depend on this optional feature.

The Oracle deployment has verified HTTPS authentication, private storage, isolation,
manual recovery tracking and a complete browser workflow using real PDF/image
extraction. The [live evaluation](EVALUATION.md) is separate from CI fixtures.
Alert delivery, full recovery preparation and participant configuration remain
pending; see [PILOT_READY.md](PILOT_READY.md). Local startup commands do not publish
the app.
