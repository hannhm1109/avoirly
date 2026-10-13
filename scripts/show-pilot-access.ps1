# Run locally to view your synthetic pilot login, never paste the output into chat.
param([switch]$TestAccount, [switch]$BackupKey)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$avoirlyRoot = Split-Path -Parent $PSScriptRoot
$avoirlyStore = Join-Path $avoirlyRoot '.local/pilot-access.dpapi'
if (-not (Test-Path -LiteralPath $avoirlyStore -PathType Leaf)) {
    throw 'The encrypted pilot-access file has not been prepared on this computer.'
}
$avoirlyPlainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
    [System.IO.File]::ReadAllBytes($avoirlyStore),
    $null,
    [System.Security.Cryptography.DataProtectionScope]::CurrentUser
)
try {
    $avoirlyAccess = [System.Text.Encoding]::UTF8.GetString($avoirlyPlainBytes) | ConvertFrom-Json
    if ($BackupKey) {
        Write-Output $avoirlyAccess.backup_key
    } else {
        $avoirlyAccountIndex = if ($TestAccount) { 1 } else { 0 }
        $avoirlyAccount = $avoirlyAccess.accounts[$avoirlyAccountIndex]
        Write-Output ('Email: ' + $avoirlyAccount.email)
        Write-Output ('Password: ' + $avoirlyAccount.password)
    }
} finally {
    [Array]::Clear($avoirlyPlainBytes, 0, $avoirlyPlainBytes.Length)
    $avoirlyAccess = $null
}
