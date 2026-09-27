# Starts the standalone PostgreSQL runtime prepared in this workspace, without a Windows service.
$ErrorActionPreference = 'Stop'
$avoirlyRoot = Split-Path -Parent $PSScriptRoot
$pgControl = Join-Path $avoirlyRoot '.local/pgsql/bin/pg_ctl.exe'
$pgData = Join-Path $avoirlyRoot '.local/pgdata'
$pgLog = Join-Path $avoirlyRoot '.local/postgres.log'
if (-not (Test-Path -LiteralPath $pgControl)) {
    throw 'Standalone PostgreSQL is not present. Use docker compose up -d postgres and port 55432 instead.'
}
& $pgControl -D $pgData status *> $null
if ($LASTEXITCODE -eq 0) { Write-Output 'Local PostgreSQL is already running.'; return }
$pgLaunch = Start-Process -FilePath $pgControl -ArgumentList @('-D', ('"' + $pgData + '"'), '-l', ('"' + $pgLog + '"'), '-o', '"-p 55433 -h 127.0.0.1"', '-w', 'start') -WindowStyle Hidden -PassThru
# Wait only for pg_ctl, not the descendant server process tree.
if (-not $pgLaunch.WaitForExit(60000)) { throw 'PostgreSQL startup timed out; inspect .local/postgres.log.' }
if ($pgLaunch.ExitCode -ne 0) { throw 'PostgreSQL did not start; inspect .local/postgres.log.' }
Write-Output 'PostgreSQL is available on 127.0.0.1:55433.'
