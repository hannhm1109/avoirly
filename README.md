# Avoirly

_Spot invoice discrepancies. Simplify supplier claims._

Avoirly turns a purchase order and supplier invoice into an evidence-backed
comparison and an editable French or English claim draft. It combines structured
document extraction with deterministic Python checks, human review and manual
credit tracking.

[Private demo](https://avoirly.84-8-218-133.sslip.io/connexion) ·
[Quick start](#quick-start) · [Architecture](docs/ARCHITECTURE.md) ·
[Demo walkthrough](docs/DEMO.md) · [Documentation](#documentation)

**Amounts are potential credit excluding tax.** A discrepancy does not prove that
a supplier owes a credit. Delivery, amendments and previously issued credits need
human verification. Avoirly does not send supplier emails or claim recovered money.

## What the application does

| Capability            | Behavior                                                                                            |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| Document intake       | One PO and one invoice, each PDF, PNG or JPEG, with validated file signatures and size limits       |
| Structured extraction | Separate typed PO/invoice extraction calls; preserves source snippets and page references           |
| Billing checks        | Deterministic quantity/price comparisons using Decimal; no double-counting or cross-product offsets |
| Human review          | Blocking issues, original documents, audited corrections and explicit pairing confirmation          |
| Claim drafts          | French or English subject/body, editable versions, copy and text download                           |
| Recovery tracking     | Manual external-send records, supplier notes, promised credits and evidence-backed partial credits  |
| Private access        | Invited accounts, signed sessions, API ownership checks and private document/proof storage          |
| Durable processing    | PostgreSQL-backed jobs, leases, bounded retries, revision guards and explicit crash recovery        |
| Operations            | Encrypted application/full-server backups, automatic off-VM copies, monitoring and Gmail alerts     |

Requested, promised and confirmed net amounts remain separate. Recorded credits
require human verification and supporting evidence; a credit note is not necessarily
a cash refund. Dashboard totals cover the displayed page and stay grouped by currency.

<details>
<summary>View the hosted interface with a synthetic 200 MAD example</summary>

![Avoirly source-linked comparison, editable claim draft and manual recovery tracking using synthetic data](docs/assets/hosted-synthetic-case.png)

Captured during the verified hosted browser flow. All business data and the account
shown are synthetic; the amount is potential net credit, not confirmed recovery.

</details>

## Current status

Phases **1–5 are implemented**: comparison core, API/worker, French web interface,
private-pilot infrastructure and manual recovery tracking. Phase 6—paid plans,
payments and entitlements—has not started.

The private demonstration runs on Oracle ARM with self-hosted Supabase and Caddy
HTTPS. It requires an operator-provided account; public sign-up is disabled.
The existing managed Supabase projects are unaffected. Hosting uses the selected
free-tier setup; OpenAI API usage is separately billed and requires an explicit budget.

Verified application evidence:

- [GitHub CI passed](https://github.com/hannhm1109/avoirly/actions/runs/38886923417)
  for recovery release `1c3d409`: **218 Python tests**, seven browser workflows,
  production web build and three
  container builds; the paid live test is intentionally skipped in ordinary CI.
  [Recovery hardening CI also passed](https://github.com/hannhm1109/avoirly/actions/runs/38927802090)
  for operator scripts at `f5415d1`.
- Separate hosted browser acceptance passed with real PDF/image extraction,
  source review, a 200.00 MAD draft, editing, export and mobile layout.
- Two-account isolation, private files, deletion, controlled worker recovery and
  isolated application-backup restores were verified.
- The operator confirmed receipt of the single Gmail SMTP test alert.
- On 16 October, controlled failures of the actual monitor and backup services
  each triggered an email; the operator confirmed receiving both. Normal jobs
  were restored and passed afterward.
- A full encrypted snapshot copied back from Windows restored PostgreSQL,
  Supabase Auth, private Storage and application configuration in isolated
  containers. Both account logins, owner isolation, three source/proof files,
  web sessions and a known draft/credit ledger passed. No production cutover
  or replacement-VM/DNS failover was performed.
- Recurring full snapshots and a Windows ciphertext-copy task complement the
  application backups. See [disaster recovery](docs/DISASTER_RECOVERY.md) for
  schedules, verification, retention and recovery limitations, and the
  [non-secret recovery evidence](docs/operations/2026-10-16-recovery.json).
- [Live evaluation](docs/EVALUATION.md): 20 development pairs plus five fresh
  held-out pairs; **zero false drafts**, all nine ambiguous cases blocked,
  expected status/amount on 24/25. One supported scan still required review.

These are small synthetic demonstrations, not production accuracy or reliability
claims. Access remains restricted to **two synthetic accounts**. Cases stay until
manually deleted; encrypted backups retain 14 days. The public privacy/support
contact is **avoirly.support@gmail.com**, verified on the live privacy page.
Operational alerts use that same address as both sender and recipient; the new
account authenticated and Gmail accepted its test alert. Provider data controls must still be confirmed
before real supplier documents. The Windows copy requires the PC, signed-in user
and network to be available; it is not an always-on cloud backup service.
See [pilot readiness](docs/PILOT_READY.md) and [pilot policy](docs/PILOT_POLICY.md).

## Architecture

The browser talks to a Next.js server-side gateway. FastAPI verifies ownership and
persists cases and jobs in PostgreSQL. A separate worker extracts documents,
validates fields, matches eligible lines and calculates discrepancies. Draft text
is generated from validated results by deterministic templates.

**The model extracts fields; Python decides eligibility and calculates amounts.**
An unresolved extraction warning blocks automatic drafting. Document text is
untrusted data and supplies no executable tools or instructions.

| Layer                 | Technology                                                   |
| --------------------- | ------------------------------------------------------------ |
| Interface             | Next.js, React, TypeScript, French workflow                  |
| API and domain core   | FastAPI, Pydantic, SQLAlchemy, Python Decimal                |
| Persistence           | PostgreSQL 17, Alembic migrations, durable job/lease records |
| Extraction            | Official OpenAI SDK with typed Structured Outputs            |
| Hosted identity/files | Supabase Auth and private Storage                            |
| Deployment            | Docker Compose, Oracle ARM, Caddy HTTPS, systemd jobs        |
| Verification          | pytest, real PostgreSQL integration tests, Playwright, Ruff  |

See [architecture and design decisions](docs/ARCHITECTURE.md) for trust boundaries,
job recovery, schema layout and backup scope.

## Quick start

Requirements: Python **3.12+** and Git. The verified environment used Python 3.14;
CI uses Python 3.14 and Node 24. The offline example needs neither PostgreSQL nor
an API key. Run commands from the repository root.

```powershell
git clone https://github.com/hannhm1109/avoirly.git
cd avoirly
python -m pip install uv==0.12.19
python -m uv sync --project backend --locked
python -m uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/demo
```

Expected output:

```text
Avoirly: CLAIM_DRAFTED
Potential credit excluding tax: 200.00 MAD
```

Inspect `output/demo/report.json` and `output/demo/claim_email.txt`. Add
`--language en` for English. Fixture mode never calls OpenAI. In this prepared
Windows workspace, `./backend/.venv/Scripts/python.exe` can replace
`python -m uv run --project backend --locked python` after dependencies are installed.

### Run the web app locally

The following PowerShell setup uses Docker **only for PostgreSQL**; API, worker
and web run locally. Start Docker Desktop first. Local mode is for one developer
on loopback and must not be exposed publicly. Node.js and npm are also required.

```powershell
docker compose up -d --wait postgres
$env:DATABASE_URL = 'postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55432/avoirly'
. ./scripts/local-env.ps1
python -m uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
```

Open three PowerShell terminals from the repository root:

```powershell
# Terminal 1: API
$env:DATABASE_URL = 'postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55432/avoirly'
. ./scripts/local-env.ps1
python -m uv run --project backend --locked avoirly-api
```

```powershell
# Terminal 2: worker; required even for a manually reviewed comparison
$env:DATABASE_URL = 'postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55432/avoirly'
. ./scripts/local-env.ps1
python -m uv run --project backend --locked avoirly-worker
```

```powershell
# Terminal 3: web
cd web
npm ci
npm run dev
```

Open **http://127.0.0.1:3000**; API docs are at
**http://127.0.0.1:8000/docs**. Stop processes with Ctrl+C and PostgreSQL with
`docker compose stop postgres`; stopping preserves its named volume.

Without a provider key, upload both sources and enter complete values through
**Vérifier les données** before saving and rerunning. Unknown or unsupported values
still require review. For automatic extraction, set `OPENAI_MODEL` on API and worker,
and `OPENAI_API_KEY` **only on the worker**, before starting them. Configure keys
privately; `.env.example` is a reference and is not automatically loaded.
The deployed snapshot and its evaluation settings are in [EVALUATION.md](docs/EVALUATION.md).

The prepared Windows standalone PostgreSQL alternative uses port **55433**, while
Docker uses **55432**. They are different databases. See [backend setup](docs/BACKEND.md)
for that alternative and [web setup](docs/WEB.md) for the interface workflow.

## Supported scope and limits

- Matching supplier, buyer, currency and PO reference; missing references require
  explicit human pairing confirmation. Conflicting references remain blocked.
- Positive quantities, tax-exclusive nonnegative prices, explicit tax rates,
  unique eligible lines and no unsupported adjustments.
- Exact normalized SKUs, then unique normalized descriptions when a SKU is missing.
  No fuzzy matching, pack conversions or silent unmatched-line removal.
- MAD, EUR, USD and GBP; Decimal calculations with half-up currency rounding and
  a 0.01 tolerance. No tax-credit calculation or cross-invoice reconciliation.
- At most 10 MiB per file, 10 PDF pages, 25 megapixels per image and 100 extracted
  product lines. Invalid, encrypted or unsupported files are rejected.
- Every unresolved extraction warning blocks a draft. Confirmation cannot bypass
  mismatches, unsupported charges or other validation failures.

Only synthetic data should be used until the hosted acceptance gates pass.
Never commit documents, reports, passwords, API keys or backup keys. Hosted
deletion revokes live access immediately and queues physical object cleanup;
retained encrypted backups have their own retention. The CLI writes private
plaintext reports and provides no account isolation. [CLI details](docs/CLI.md).

## Verification

```powershell
python -m uv run --project backend --locked ruff check backend/src backend/tests scripts
python -m uv run --project backend --locked pytest backend/tests -q
cd web
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm run test:e2e
```

Database and browser tests need a disposable PostgreSQL test database through
`AVOIRLY_TEST_DATABASE_URL`; restore tests also need matching PostgreSQL client
tools and a role with `CREATEDB`. Database tests skip explicitly if not configured.
See [TESTING.md](docs/TESTING.md) for exact prerequisites and interpretation.
CI browser tests use synthetic extraction fixtures; they do not make paid API calls.
Live extraction requires separate configuration and explicit opt-in.

## Documentation

| Guide                                          | Read it for                                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------ |
| [Demo walkthrough](docs/DEMO.md)               | A synthetic interview/demo flow and honest talking points                |
| [Architecture](docs/ARCHITECTURE.md)           | Components, trust boundaries, recovery and design decisions              |
| [CLI and reports](docs/CLI.md)                 | Live/fixture commands, JSON output, pairing and local duplicate history  |
| [Backend](docs/BACKEND.md)                     | Database setup, API routes, corrections, idempotency and worker recovery |
| [Web interface](docs/WEB.md)                   | Local interface setup and the French review workflow                     |
| [Recovery tracking](docs/RECOVERY_TRACKING.md) | Manual sent/promised/confirmed records, evidence and migration           |
| [Testing](docs/TESTING.md)                     | Offline, PostgreSQL, browser, CI and paid live checks                    |
| [Evaluation](docs/EVALUATION.md)               | Recorded live results, methodology, cost estimates and limitations       |
| [Self-hosting](docs/SELF_HOSTING.md)           | Current Oracle/Supabase deployment and protected configuration           |
| [Configuration checklist](docs/CONFIGURE.md)   | Hosted acceptance gates and managed-provider alternative                 |
| [Operations](docs/OPERATIONS.md)               | Monitoring, alerts, encrypted backups and isolated restores              |
| [Disaster recovery](docs/DISASTER_RECOVERY.md) | Full Auth/database/configuration recovery and automatic off-VM copies    |
| [Pilot policy](docs/PILOT_POLICY.md)           | Synthetic access, data locations, deletion and retention decisions       |
| [Pilot readiness](docs/PILOT_READY.md)         | Configured credentials and remaining work before real data               |
| [Progress](docs/PROGRESS.md)                   | Dated implementation and verification history                            |
| [Build specification](docs/SPEC.md)            | Reference text from the supplied project guide                           |

Source layout: `backend/src/recovery/` contains the domain core, API, worker and
database models; `backend/tests/` its tests; `web/` the interface and browser tests;
`scripts/` evaluation and operator helpers; `deploy/self-hosted/` the deployment
overlays; `samples/` visibly synthetic example documents. No public demo credentials
or secrets are included.
