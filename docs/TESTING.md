# Testing and verification

Avoirly keeps deterministic tests, live provider calls and hosted acceptance
evidence separate. Passing fixture tests is not presented as measured extraction
accuracy, and a green container build does not prove a deployed system works.

## Recorded implementation evidence

Recovery release `1c3d409cf171f6573aaa4875e49e99fe550ba001` passed
[GitHub Actions](https://github.com/hannhm1109/avoirly/actions/runs/38886923417):

| Check                       | Recorded result                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------ |
| Python with real PostgreSQL | 218 passed; one paid live test skipped                                               |
| Chromium workflows          | Seven passed against real API, worker and temporary database schema                  |
| Frontend                    | Production build passed                                                              |
| Containers                  | API, web and operations images built; operations PostgreSQL tools executed           |
| ARM deployment              | Images built and ran on the Oracle host                                              |
| Separate live acceptance    | Real hosted PDF/image extraction → source review → draft/edit/export passed          |
| Live evaluation             | 20 development + five fresh held-out pairs; [results and limitations](EVALUATION.md) |

Documentation-only commits do not change that tested implementation. The existing
Starlette test-client deprecation warning is recorded; it is not a failed test.
Operator hardening commit `886152f` also passed the complete
[CI run](https://github.com/hannhm1109/avoirly/actions/runs/38887866103), including
the same 218 Python tests and seven browser workflows.

## Install and run without PostgreSQL or paid calls

From the repository root:

```powershell
python -m pip install uv==0.12.19
python -m uv sync --project backend --locked
python -m uv run --project backend --locked ruff check backend/src backend/tests scripts
python -m uv run --project backend --locked pytest backend/tests -m 'not postgres and not live' -q
python -m uv run --project backend --locked python -m recovery.cli --fixture ./samples/pair.json --out ./output/test-demo
```

The fixture produces a 200.00 MAD draft without network access. Tests cover typed
contracts, arithmetic, tolerances, unsupported cases, source/file checks, mock SDK
responses, refusals, bounded retries, CLI history and atomic outputs. Confirm the
reported selected/skipped counts rather than calling a partial run the full suite.

## PostgreSQL integration and restore tests

Use a disposable test database. The suite creates random isolated schemas and a
temporary empty restore database; the test role needs `CREATEDB`. Do not point it
at a production database. `pg_dump` and `pg_restore` must match the server major
version; CI uses PostgreSQL 17 tools through disposable containers.

For the local Docker PostgreSQL service from [README.md](../README.md):

```powershell
docker compose up -d --wait postgres
$env:AVOIRLY_TEST_DATABASE_URL = 'postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55432/avoirly'
# Set AVOIRLY_PG_BIN to your installed PostgreSQL 17 bin directory if not on PATH.
# In the prepared Windows workspace only:
$env:AVOIRLY_PG_BIN = Join-Path $PWD '.local/pgsql/bin'
python -m uv run --project backend --locked pytest backend/tests -q
```

The `.local/pgsql` binaries are not committed. A new checkout needs its own matching
client tools. Without `AVOIRLY_TEST_DATABASE_URL`, database tests explicitly skip.
Do not treat a high skip count as a completed integration run.

Integration coverage includes migrations, real signed JWTs, owner isolation,
concurrent quotas, stale edits, idempotency, leases/recovery, extraction-cache
invalidation, private storage adapters, recovery ledgers, encrypted backup
authentication and restoration of documents/drafts/evidence. The local/CI provider
and storage test doubles are distinct from the recorded hosted checks.

## Browser tests

Keep `AVOIRLY_TEST_DATABASE_URL` and PostgreSQL tools configured in the shell, then:

```powershell
cd web
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm run test:e2e
```

The runner creates a separate API on port 8001, Next.js on 3001, a random
`avoirly_browser_<uuid>` schema and temporary file storage. Its extraction adapter
returns deliberately synthetic values, including uncertainty requiring correction.
Actual upload, API, worker, validation, database state, drafts, exports and tracking
are exercised. No paid model call or supplier message is made.

Tests cover upload/review/correction, saved drafts, reload/copy/download, mobile
layout, deletion, conflicts, foreign origins and manual recovery tracking.
Screenshots/traces stay in ignored `web/test-results/`. Graceful shutdown cleans
the temporary schema; forced termination can require operator cleanup.

## Paid live extraction and labeled evaluation

Configure `OPENAI_API_KEY` and `OPENAI_MODEL` privately in the test process and
approve a total allowance before enabling the live test:

```powershell
$env:AVOIRLY_LIVE = '1'
python -m uv run --project backend --locked pytest backend/tests/test_live.py -m live -q
```

Ordinary CI never sets this opt-in. The dedicated evaluation script additionally
requires `--allow-live` and an explicit per-run allowance. A reported-usage reserve
is not a billing guarantee. [EVALUATION.md](EVALUATION.md) records the exact model,
prompt hash, dataset splits, metrics, cost estimates and reproduction commands.
Do not retune on an inspected set and continue describing it as blind holdout data.

## Hosted checks and the current documentation pass

The hosted record includes real HTTPS/session/owner/file checks, complete manual
and live-model browser flows, controlled lease/network-failure recovery, private
deletion checks and isolated application restores. The operator confirmed Gmail
test receipt. Actual monitor/backup failures also delivered confirmed emails on
16 October. Full PostgreSQL/Auth/Storage/configuration restoration from the
Windows ciphertext passed in isolated containers; see
[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) for scope and limits.

During the initial 16 October documentation check, the offline fixture still produced the expected draft; all ten
hosted worker preflight gates and all six monitor checks passed. The backup and
monitor services reported success. Local Compose configuration parsed, but the
Windows Docker Desktop engine was not running, so this documentation pass did not
repeat local container/database/browser acceptance. No additional paid call or
test email was required for documentation changes.

The subsequent recovery implementation passed **218 Python tests** with real
PostgreSQL (one opt-in live test skipped), all **seven Chromium workflows**, Ruff,
PowerShell syntax parsing, TypeScript and a production web build. The additional
checks cover stale snapshot/copy metadata and the restricted privacy page.
Full recovery verified both Auth users, a known draft and ledger, three private
source/proof files, ownership and secure web sessions. No production cutover,
replacement server or public DNS failover was performed. The Windows task ran
successfully; its availability dependency is documented in the recovery runbook.

The dedicated support mailbox was verified on 16 October with both a received
test email and an actual monitor failure email. A backup-startup race caused the
latter: recovery now waits for the public API to answer before restarting the
monitor timer. Commit `f5415d1` passed the complete
[CI run](https://github.com/hannhm1109/avoirly/actions/runs/38927802090), including
the new operator shell syntax checks. The deployed full-backup and monitor units
then passed, with no monitor failure recorded during that backup window. The
Windows task also uses noninteractive SSH stdin to finish without a hidden
console wait. These are runtime/operator fixes; the application image remains
`1c3d409`.
