# Avoirly backend

The API and a separate polling worker share PostgreSQL. An API restart does not
lose cases or queued work. The worker saves each successful extraction and the
comparison before drafting, so retries can resume completed steps.

The backend supports explicit local development and Phase 4 hosted mode. Hosted
mode requires signed Supabase sessions, an invited-user allowlist, TLS database
access and private object storage. See [CONFIGURE.md](CONFIGURE.md) and
[OPERATIONS.md](OPERATIONS.md) for setup and outstanding pilot gates. The examples
below describe local mode. The API does not send supplier email; hosted operational
alerts use a separate protected SMTP configuration.

Phase 5 adds a manual ledger for externally sent claims, supplier notes, promises
and evidence-backed partial credits. See [RECOVERY_TRACKING.md](RECOVERY_TRACKING.md)
for its named endpoints, ownership/version guards and migration `0003_phase5`.

## Start on this computer

The prepared Windows setup uses standalone PostgreSQL on `127.0.0.1:55433`.
For a new checkout, Docker Compose provides PostgreSQL on `127.0.0.1:55432`,
with data in the `avoirly_pg` named volume. Start Docker Desktop before using it.
An early local Docker connection problem is historical; subsequent Linux CI and
the Oracle ARM deployment passed container checks. On 16 October the local Docker
engine was not running, so local container acceptance was not repeated.

Run these from the Avoirly folder in PowerShell:

```powershell
. ./scripts/local-env.ps1
./scripts/start-local-postgres.ps1
./backend/.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head
./backend/.venv/Scripts/python.exe -m recovery.api.app
```

API documentation is at **http://127.0.0.1:8000/docs**. Health is
`GET http://127.0.0.1:8000/api/v1/health`.

In a second PowerShell window, configure the model explicitly and start the worker:

```powershell
. ./scripts/local-env.ps1
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "your-selected-compatible-model"
./backend/.venv/Scripts/python.exe -m recovery.worker
```

The API also needs `OPENAI_MODEL` set **before it starts** to enqueue live analysis.
No default model is chosen. The model must support Chat Completions, vision, PDF
input and Structured Outputs. Separate real hosted extraction and labeled live
evaluation passed on 15 October; see [EVALUATION.md](EVALUATION.md). This does not
imply that an unconfigured local worker can make model calls.

Stop the API and worker with Ctrl+C. Stop the standalone database when finished:

```powershell
./.local/pgsql/bin/pg_ctl.exe -D ./.local/pgdata -m fast stop
```

## Set up on another computer

```powershell
python -m pip install uv==0.12.19
python -m uv sync --project backend --locked
docker compose up -d --wait postgres
$env:DATABASE_URL = "postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55432/avoirly"
. ./scripts/local-env.ps1
python -m uv run --project backend --locked alembic -c backend/alembic.ini upgrade head
python -m uv run --project backend --locked avoirly-api
```

The Compose password is for local development only. The standalone Windows runtime
is not committed or needed for Docker. Migration startup is explicit: the API never
creates or silently modifies tables.

## Standalone runtime

The earlier standalone PostgreSQL runtime and data remain in `.local/pgsql` and
`.local/pgdata`. No Windows service was installed. To use that separate database,
set its port explicitly before starting the API and worker:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55433/avoirly"
. ./scripts/local-env.ps1
./scripts/start-local-postgres.ps1
```

The standalone and Docker databases do not share data. The standalone database had
no cases when the Docker setup was attempted. Stop standalone PostgreSQL with:

```powershell
./.local/pgsql/bin/pg_ctl.exe -D ./.local/pgdata -m fast stop
```

## API workflow

All routes below use `/api/v1`. IDs are UUIDs. Amounts in JSON are decimal strings.
Every mutation after creation uses `expected_version`; reload after a 409 conflict.
Never send `owner_id`: it is resolved by the server's identity dependency.

| Method and route               | Request / response                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `POST /cases`                  | Create a `PENDING` case; returns ID, version and revision                                                  |
| `POST /cases/{id}/documents`   | Multipart `role=PO` or `INVOICE`, `expected_version`, `file`; returns new version                          |
| `POST /cases/{id}/analyze`     | JSON `expected_version`, optional `language=fr`; requires `Idempotency-Key`; returns 202 and job ID        |
| `GET /cases?limit=20&offset=0` | Owner-scoped page of cases; no mixed-currency aggregate                                                    |
| `GET /cases/{id}`              | Current documents, raw/corrected extraction, comparison, issues, draft and job history                     |
| `GET /cases/{id}/events`       | Paginated audit history                                                                                    |
| `GET /documents/{id}/content`  | Owner-checked private bytes; no public storage path                                                        |
| `PUT /cases/{id}/review`       | `expected_version`, complete `corrected` extraction pair, `reason`, optional `confirm_pair` and `mappings` |
| `PATCH /cases/{id}/draft`      | `expected_version`, `subject`, `body`; appends a draft version                                             |
| `POST /cases/{id}/retry`       | Same request shape as Analyze, distinct `Idempotency-Key`; only for `FAILED` cases                         |
| `POST /cases/{id}/close`       | `expected_version` and `close_reason`                                                                      |
| `DELETE /cases/{id}`           | JSON `expected_version`, `confirmed=true`; cancels work and revokes content access                         |

Example Analyze request:

```json
{ "expected_version": 3, "language": "fr" }
```

Use a new unique request key for a new action and the same key and body for its
network retries. Keys are stored for 24 hours, scoped to owner and route. A changed
body under the same key returns 409. A concurrent duplicate request returns the
existing job. A database partial unique index also prevents two active jobs for the
same case revision. One queued/running job per owner is enforced transactionally.

Errors have `code`, `message`, `details`, and `request_id`. Data needing review is a
successful processing result with `NEEDS_REVIEW`, no findings, no total, and no draft.
Technical failures set `FAILED` with a redacted code. The review endpoint allows an
incomplete business correction to be saved, but the worker reruns all validation
rules before producing any claim.

## Corrections, pairing and duplicate resolution

Corrections create a new input revision. Original extraction values remain intact;
corrected snapshots record the author and reason. The new revision has no current
comparison or draft until analysis completes. Old drafts remain in storage as
history and are never returned as the current exportable draft.

Pair confirmation records the exact extraction hash, author, reason, and revision.
It resolves only a missing PO reference. Optional mappings are an auditable assertion
of the deterministic line pairs; they cannot bypass SKU, uniqueness, description,
unit, or tax rules. Correct extraction keys first if a mapping fails.

Duplicate files are checked against the owner's document history. Re-uploading the
same file into the same role of the same case is harmless; another case or role
returns 409 and the existing case ID. Invoice identities are reserved by normalized
supplier name and, where available, tax ID plus invoice number. An identity already
used by another case blocks a new claim, including when that earlier case needs
review. Use the existing case or delete an erroneous duplicate; no override button
can quietly create a second claim. Reservations remain until the owning case is deleted.

## Interrupted workers and consistency

Jobs are claimed using row locks and `SKIP LOCKED`. Each running job has a fresh
lease token and input revision. A heartbeat extends the lease while extraction runs.
Every save checks current ownership, revision, token and lease expiry. A deleted
case or expired worker cannot commit later. Database time is used for lease checks.

After a stopped or crashed worker, let its lease expire, then explicitly requeue:

```powershell
. ./scripts/local-env.ps1
./backend/.venv/Scripts/python.exe -m recovery.worker --requeue-expired
./backend/.venv/Scripts/python.exe -m recovery.worker
```

The old attempt is retained as failed and a new attempt is created. An already
completed no-draft comparison is finalized directly. Extracted results are reused
only for matching hash/model/prompt/schema; explicitly audited human corrections
are tied to their source hash and current revision. A saved comparison can be reused
on retry of that same revision. `DISCREPANCY_FOUND` is committed before generating
the deterministic draft.

State changes use status/version/revision predicates and an audit insert in the
same transaction. APIs expose named actions, not an arbitrary status setter.
Closed cases are terminal; closing/exporting never means an email was sent or a
credit was recovered.

## Storage, deletion and local identity

Files have random internal keys under `AVOIRLY_STORAGE_ROOT`. Filenames never
become filesystem paths. File signatures, decodeability and all Phase 1 limits are
checked before storage is attached to a case. The full HTTP request body is bounded
before multipart parsing, including chunked uploads.

Deletion atomically removes case content, snapshots, confirmations, jobs, lease
tokens, idempotency responses and invoice reservations. A small durable deletion
outbox retains only random object keys until files are removed. The API attempts
cleanup immediately; the worker retries it. If storage is unavailable, content
access is still revoked immediately and physical cleanup is pending.

In local mode, the developer identity is a fixed server environment value. The API cannot
select it by header, body, or query parameter. The bundled API runner binds only
to loopback; requests from non-loopback clients and unapproved origins are refused.
Omitting an explicit mode prevents startup. Do not put local mode behind a public
proxy. Hosted mode instead requires full signed-session configuration and verifies
signed user JWTs; no developer identity override is accepted. Phase 4 tests use
real signatures to verify account isolation, with provider key discovery mocked.

Local files and PostgreSQL data persist until explicitly removed. Phase 4 adds
scheduled encrypted snapshots and isolated restore verification; see
[OPERATIONS.md](OPERATIONS.md). External backups and OneDrive copies remain outside
the deletion transaction. Confirm retention and hosted restore before real pilot data.

## Run the acceptance suite

```powershell
. ./scripts/local-env.ps1
$env:AVOIRLY_TEST_DATABASE_URL = $env:DATABASE_URL
$env:AVOIRLY_PG_BIN = Join-Path $PWD '.local/pgsql/bin'
./backend/.venv/Scripts/python.exe -m pytest backend/tests -q
./backend/.venv/Scripts/ruff.exe check backend scripts
```

Database tests create random temporary schemas, apply the real migration, and
drop those schemas afterwards. The restore test also creates and drops its own
random empty database, requiring a test role with CREATEDB and PostgreSQL client
tools matching the server major version. Existing application cases are not touched.
Without `AVOIRLY_TEST_DATABASE_URL`, PostgreSQL tests explicitly skip. Live OpenAI
tests still require the separate `AVOIRLY_LIVE=1` opt-in.
