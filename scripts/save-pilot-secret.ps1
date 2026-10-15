# Collect locally without showing or sending the secret; no network request is made.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][ValidateSet('OpenAI', 'GmailSMTP')][string]$Name)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$avoirlyRoot = Split-Path -Parent $PSScriptRoot
$avoirlyFolder = Join-Path $avoirlyRoot '.local'
$avoirlyFilename = if ($Name -eq 'OpenAI') { 'openai-key.dpapi' } else { 'gmail-smtp.dpapi' }
$avoirlyStore = Join-Path $avoirlyFolder $avoirlyFilename
$avoirlyPrompt = if ($Name -eq 'OpenAI') {
    'Paste your Avoirly project OpenAI API key (hidden)'
} else {
    'Paste your dedicated Gmail app password, not your main password (hidden)'
}
$avoirlySecret = Read-Host $avoirlyPrompt -AsSecureString
$avoirlyPointer = [IntPtr]::Zero
$avoirlyBytes = $null
$avoirlyPlain = $null
try {
    $avoirlyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($avoirlySecret)
    $avoirlyPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($avoirlyPointer).Trim()
    if ($Name -eq 'GmailSMTP') {
        $avoirlyPlain = $avoirlyPlain -replace '\s', ''
        if ($avoirlyPlain -notmatch '^[A-Za-z0-9]{16}$') {
            throw 'Expected a 16-character Gmail app password. Nothing was saved.'
        }
    } elseif ($avoirlyPlain.Length -lt 20 -or $avoirlyPlain.Length -gt 512 -or
        -not $avoirlyPlain.StartsWith('sk-') -or $avoirlyPlain -match '[\s\x00-\x1F]') {
        throw 'This does not look like an OpenAI secret API key. Nothing was saved.'
    }
    $avoirlyBytes = [Text.Encoding]::UTF8.GetBytes($avoirlyPlain)
    $avoirlyEncrypted = [Security.Cryptography.ProtectedData]::Protect(
        $avoirlyBytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [IO.Directory]::CreateDirectory($avoirlyFolder) | Out-Null
    [IO.File]::WriteAllBytes($avoirlyStore, $avoirlyEncrypted)
    Write-Output ($Name + ' secret saved encrypted for this Windows user in .local/' + $avoirlyFilename + '.')
    Write-Output 'No network request was made and the server configuration has not changed.'
    Write-Output 'Tell Codex that the secret is saved; never paste it into chat.'
} finally {
    if ($avoirlyBytes) { [Array]::Clear($avoirlyBytes, 0, $avoirlyBytes.Length) }
    if ($avoirlyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($avoirlyPointer)
    }
    $avoirlyPlain = $null
    if ($avoirlySecret) { $avoirlySecret.Dispose() }
}
