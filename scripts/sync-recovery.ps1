# Pull ciphertext only. Run as the Windows operator; no secrets are command arguments.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$IdentityFile,
    [Parameter(Mandatory = $true)][string]$Destination,
    [string]$HostName = '84.8.218.133',
    [string]$UserName = 'ubuntu',
    [string]$SourceRoot = '/home/ubuntu/avoirly-infra'
)
$ErrorActionPreference = 'Stop'
if ($HostName -notmatch '^[A-Za-z0-9.-]+$' -or $UserName -notmatch '^[a-z_][a-z0-9_-]*$' -or
    $SourceRoot -notmatch '^/[A-Za-z0-9/_-]+$') { throw 'Invalid backup connection settings.' }
$avoirlyTarget = [IO.Path]::GetFullPath($Destination)
[IO.Directory]::CreateDirectory($avoirlyTarget) | Out-Null
if ((Get-Item -LiteralPath $avoirlyTarget).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'The backup directory must not be a junction or symbolic link.'
}
$avoirlyIdentity = (Resolve-Path -LiteralPath $IdentityFile).Path
$avoirlyConnection = $UserName + '@' + $HostName
$avoirlySSH = @('-i', $avoirlyIdentity, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15')
$avoirlyLock = $null
try {
    $avoirlyLock = [IO.File]::Open((Join-Path $avoirlyTarget 'sync.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    # These commands take no stdin; -n avoids waiting on a hidden task's console.
    $avoirlyNames = @(& ssh.exe -n @avoirlySSH $avoirlyConnection "find $SourceRoot/recovery-exports -maxdepth 1 -type f -name 'full-*.json'")
    if ($LASTEXITCODE -ne 0 -or $avoirlyNames.Count -eq 0) { throw 'No remote recovery backups available.' }
    $avoirlyCount = 0
    foreach ($avoirlyRemote in $avoirlyNames) {
        $avoirlyName = $avoirlyRemote.Trim().Split('/')[-1]
        if ($avoirlyName -notmatch '^full-\d{8}T\d{6}Z-[a-f0-9]{32}\.json$') { throw 'Invalid remote backup name.' }
        $avoirlyStem = $avoirlyName.Substring(0, $avoirlyName.Length - 5)
        $avoirlyReportPath = Join-Path $avoirlyTarget $avoirlyName
        $avoirlyDataPath = Join-Path $avoirlyTarget ($avoirlyStem + '.bin')
        foreach ($avoirlyExtension in @('json', 'bin')) {
            $avoirlyPath = Join-Path $avoirlyTarget ($avoirlyStem + '.' + $avoirlyExtension)
            if (-not (Test-Path -LiteralPath $avoirlyPath)) {
                $avoirlyPartial = $avoirlyPath + '.partial'
                & scp.exe @avoirlySSH ($avoirlyConnection + ':' + $SourceRoot + '/recovery-exports/' + $avoirlyStem + '.' + $avoirlyExtension) $avoirlyPartial
                if ($LASTEXITCODE -ne 0) { throw 'Encrypted backup transfer failed.' }
                Move-Item -LiteralPath $avoirlyPartial -Destination $avoirlyPath
            }
        }
        $avoirlyReport = Get-Content -LiteralPath $avoirlyReportPath -Raw | ConvertFrom-Json
        if ($avoirlyReport.sha256 -notmatch '^[a-f0-9]{64}$' -or -not $avoirlyReport.authenticated_round_trip -or
            (Get-FileHash -LiteralPath $avoirlyDataPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $avoirlyReport.sha256 -or
            (Get-Item -LiteralPath $avoirlyDataPath).Length -ne $avoirlyReport.bytes) {
            throw 'Encrypted backup verification failed; files preserved for investigation.'
        }
        $avoirlyCount++
    }
    & ssh.exe -n @avoirlySSH $avoirlyConnection "date -u +%FT%TZ > $SourceRoot/recovery-exports/last-offvm-confirmed"
    if ($LASTEXITCODE -ne 0) { throw 'Backup copied, but server acknowledgement failed.' }
    # Retention only after every available remote snapshot has verified successfully.
    $avoirlyCutoff = [DateTime]::UtcNow.AddDays(-14)
    foreach ($avoirlyFile in (Get-ChildItem -LiteralPath $avoirlyTarget -File)) {
        if ($avoirlyFile.Name -match '^full-(\d{8}T\d{6}Z)-[a-f0-9]{32}\.(bin|json)$') {
            $avoirlyCreated = [DateTime]::ParseExact($Matches[1], 'yyyyMMddTHHmmssZ', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal).ToUniversalTime()
            $avoirlyResolved = [IO.Path]::GetFullPath($avoirlyFile.FullName)
            if ($avoirlyCreated -lt $avoirlyCutoff -and $avoirlyResolved.StartsWith($avoirlyTarget.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $avoirlyResolved
            }
        }
    }
    # Historical operator-created application/configuration test archives migrate
    # here once. Their original UTC filename date controls expiration.
    $avoirlyLegacy = Join-Path $avoirlyTarget 'Legacy'
    if (Test-Path -LiteralPath $avoirlyLegacy) {
        if ((Get-Item -LiteralPath $avoirlyLegacy).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Invalid legacy backup directory.' }
        foreach ($avoirlyFile in (Get-ChildItem -LiteralPath $avoirlyLegacy -File)) {
            if ($avoirlyFile.Name -match '^(?:backup-(\d{8})T\d{6}Z-[a-f0-9]{32}|control-plane-(\d{8})(?:-smtp)?)\.bin$') {
                $avoirlyDate = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
                $avoirlyCreated = [DateTime]::ParseExact($avoirlyDate, 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal).ToUniversalTime()
                $avoirlyResolved = [IO.Path]::GetFullPath($avoirlyFile.FullName)
                if ($avoirlyCreated -lt $avoirlyCutoff -and $avoirlyResolved.StartsWith($avoirlyTarget.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $avoirlyResolved }
            }
        }
    }
    $avoirlyStatus = @{ succeeded = $true; checked_utc = [DateTime]::UtcNow.ToString('o'); verified_snapshots = $avoirlyCount }
    $avoirlyStatus | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $avoirlyTarget 'sync-status.json') -Encoding UTF8
    Write-Output 'Encrypted off-server recovery copies verified; server acknowledgement updated.'
} catch {
    @{ succeeded = $false; checked_utc = [DateTime]::UtcNow.ToString('o'); error_type = $_.Exception.GetType().Name } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $avoirlyTarget 'sync-status.json') -Encoding UTF8
    throw 'Off-server recovery sync failed. Inspect the protected status and connectivity; no decrypted data was written.'
} finally {
    if ($avoirlyLock) { $avoirlyLock.Dispose() }
}
