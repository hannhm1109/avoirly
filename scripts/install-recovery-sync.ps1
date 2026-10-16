# Install a current-user task. The computer must be on and the user logged in.
[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$IdentityFile)
$ErrorActionPreference = 'Stop'
$avoirlyBase = Join-Path $env:LOCALAPPDATA 'Avoirly'
$avoirlyOperator = Join-Path $avoirlyBase 'Operator'
$avoirlyDestination = Join-Path $avoirlyBase 'Recovery'
$avoirlySID = [Security.Principal.WindowsIdentity]::GetCurrent().User
foreach ($avoirlyDirectory in @($avoirlyBase, $avoirlyOperator, $avoirlyDestination)) {
    [IO.Directory]::CreateDirectory($avoirlyDirectory) | Out-Null
    if ((Get-Item -LiteralPath $avoirlyDirectory).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Use ordinary private directories, not junctions.' }
    $avoirlyACL = New-Object Security.AccessControl.DirectorySecurity
    $avoirlyACL.SetAccessRuleProtection($true, $false)
    $avoirlyRule = New-Object Security.AccessControl.FileSystemAccessRule($avoirlySID, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $avoirlyACL.AddAccessRule($avoirlyRule)
    Set-Acl -LiteralPath $avoirlyDirectory -AclObject $avoirlyACL
}
$avoirlyKey = Join-Path $avoirlyOperator 'oracle-pilot.key'
Copy-Item -LiteralPath (Resolve-Path -LiteralPath $IdentityFile).Path -Destination $avoirlyKey -Force
$avoirlyScript = Join-Path $avoirlyOperator 'sync-recovery.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'sync-recovery.ps1') -Destination $avoirlyScript -Force
foreach ($avoirlyPath in @($avoirlyKey, $avoirlyScript)) {
    $avoirlyACL = New-Object Security.AccessControl.FileSecurity
    $avoirlyACL.SetAccessRuleProtection($true, $false)
    $avoirlyACL.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($avoirlySID, 'FullControl', 'Allow')))
    Set-Acl -LiteralPath $avoirlyPath -AclObject $avoirlyACL
}
if (($avoirlyScript + $avoirlyKey + $avoirlyDestination) -match '["\r\n]') { throw 'Unsupported path characters.' }
$avoirlyArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $avoirlyScript + '" -IdentityFile "' + $avoirlyKey + '" -Destination "' + $avoirlyDestination + '"'
$avoirlyAction = New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $avoirlyArguments
$avoirlyTriggers = @(
    (New-ScheduledTaskTrigger -Daily -At '07:00'),
    (New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)),
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 4))
)
$avoirlyPrincipal = New-ScheduledTaskPrincipal -UserId $avoirlySID.Value -LogonType Interactive -RunLevel Limited
$avoirlySettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'Avoirly encrypted recovery sync' -Action $avoirlyAction -Trigger $avoirlyTriggers -Principal $avoirlyPrincipal -Settings $avoirlySettings -Description 'Pull and verify encrypted recovery backups from the Oracle server. Requires this user to be logged in and the computer/network available.' -Force | Out-Null
Write-Output 'Current-user encrypted recovery sync installed: daily 07:00 local, at sign-in, and every four hours while available.'
Write-Output 'Ciphertext is stored under LOCALAPPDATA\Avoirly\Recovery, outside the OneDrive workspace. No plaintext backup is downloaded.'
