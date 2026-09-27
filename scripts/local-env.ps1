# Dot-source from any directory: . ./scripts/local-env.ps1
# Developer identity only; these values must not be used for hosted deployment.
$avoirlyRoot = Split-Path -Parent $PSScriptRoot
$env:AVOIRLY_MODE = 'local'
$env:AVOIRLY_LOCAL_OWNER_ID = '11111111-1111-4111-8111-111111111111'
$env:AVOIRLY_STORAGE_ROOT = Join-Path $avoirlyRoot '.private'
$env:AVOIRLY_LEASE_SECONDS = '120'
if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = 'postgresql+psycopg://avoirly:local-avoirly-only@127.0.0.1:55433/avoirly'
}
# OPENAI_API_KEY and OPENAI_MODEL are intentionally left for the user to configure.
